from collections import Counter
import datetime
from itertools import combinations
import json
import logging
from operator import itemgetter
import os
from PIL import Image, ImageGrab
from retrace import retry
import time

from engine.engine import Engine, EngineError
from es.es import ES
from mc.mc import MonteCarlo
from scraper.sites.base import SiteException, NoDealerButtonError, PocketError, ThinkingPlayerError, BalancesError, BoardError
from scraper.sites.pokerstars.site import PokerStars
from scraper.sites.partypoker.site import PartyPoker
from scraper.sites.zynga.site import Zynga


logger = logging.getLogger(__name__)


class Scraper:
    """Runs a scraper for a site. Will use the site to do the scraping, and with the data
    calculate what action needs to be taken and pass that into the engine and MC"""

    PATH_DEBUG = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'debug')
    ACTIONS_MAP = {
        'f': 'fold',
        'k': 'check',
        'c': 'call',
        'b': 'bet',
        'r': 'raise',
        'a': 'allin',
    }

    def __init__(self, site_name, seats, debug=False, replay=False, observe=False):
        self.debug = debug
        logger.debug('Debug {}'.format(self.debug))
        self.observe = observe
        logger.debug('Observing {}'.format(self.observe))
        self.replay = replay
        logger.debug('Replay {}'.format(self.replay))
        if replay:
            self.load_files()

        if site_name == 'ps':
            self.site = PokerStars(seats, debug)
        elif site_name == 'pp':
            self.site = PartyPoker(seats, debug)
        elif site_name == 'zg':
            self.site = Zynga(seats, debug)
        else:
            raise NotImplementedError('{} is not implemented'.format(site_info))

        self.img = None

        # starting balance zero for ante on init
        self.players = {
            s: {
                'name': 'joe',
                'balance': 0,
                'status': 1,
            }
            for s in range(1, seats + 1)
        }
        # do not add engine & mc
        self.btn = None
        # not currently in a game
        self.waiting_for_new_game = True
        # button moved
        self.button_moved = False
        # board moved to help finish phase
        self.board_moved = False

    def load_files(self):
        """Replays through images saved during debug run"""
        self.files = []
        for entry in os.scandir(self.PATH_DEBUG):
            if not entry.is_file() or entry.name.startswith('.'):
                logger.debug('skipping file {}'.format(entry.name))
                continue
            self.files.append(entry.path)
        logger.info('loading {} files'.format(len(self.files)))

    def take_screen(self):
        """Get screen image
        Takes screen shot or load file if replaying
        """
        logger.info('taking screen shot')
        while True:
            if not self.replay:
                img = ImageGrab.grab()
                if self.debug:
                    img_file = os.path.join(self.PATH_DEBUG, '{}.png'.format(datetime.datetime.utcnow()))
                    img.save(img_file)
                    logger.debug('file saved locally to {}'.format(img_file))
            else:
                img_path = self.files.pop(0)
                logger.debug('loading file: {}'.format(img_path))
                img = Image.open(img_path)

            if not self.observe:
                img_full = img.convert('L')

                try:
                    self.img = self.site.parse_top_left_corner(img_full)
                except SiteException as e:
                    logger.error(e)
                    if self.debug:
                        input('$ really no tlc?')
                        img_full.show()
                        input('$')
                    time.sleep(1)
                    continue

                try:
                    btn = self.site.parse_dealer(self.img)
                except NoDealerButtonError as e:
                    logger.error(e)
                    # if self.debug:
                    #     input('$ really no btn?')
                    time.sleep(0.6)
                    continue
                else:
                    if not self.btn:
                        logger.debug('button initialised at {} on joining table'.format(btn))
                        self.btn = btn
                    elif btn != self.btn:
                        self.button_moved = True
                        self.btn_next = btn
                        logger.debug('button moved to {}!'.format(btn))

                try:
                    self.check_board()
                except BoardError as e:
                    logger.error(e)
                    if self.debug:
                        input('$ what is this board error?')
                    continue

            # always break (only continue when tlc & btn found)
            break

    def check_board(self):
        """Check board and handles exception raised if card not identified. Card animation
        could be covering the cards. Instead of retrying rather return existing board"""
        if not hasattr(self, 'engine'):
            logger.info('Not checking board when no engine present')
            return

        if len(self.engine.board) >= 5:
            logger.info('Board already identified as {}'.format(self.engine.board))
            return

        logger.info('checking board...')
        board = self.site.parse_board(self.img)

        if not self.button_moved and not self.waiting_for_new_game and len(board) < len(self.engine.board):
            raise BoardError('Board cannot be removed without button moving')

        if len(board) > len(self.engine.board):
            logger.debug('The board changed with {}'.format(set(board) - set(self.engine.board)))
            self.engine.board = board
            self.board_moved = True
            input('$ board really changed?')

        logger.debug('board: {}'.format(self.engine.board))

    def run(self):
        """Run application"""
        while True:
            self.take_screen()

            if self.observe:
                continue

            # we are ready for a new game
            if self.waiting_for_new_game:
                logger.debug('waiting for a new game...')
                if self.button_moved:
                    logger.debug('button moved and waiting for new game: create new game')
                    self.start_new_game()
                else:
                    logger.info('just waiting for new game to start...')
                    time.sleep(1)
                    continue
            # else game in progress
            else:
                logger.debug('still playing same game')
                if self.button_moved:
                    logger.debug('button moved! we need to finish up what engine is')
                    self.finish_it()
                elif self.engine.phase in [self.engine.PHASE_GG, self.engine.PHASE_SHOWDOWN]:
                    logger.info('Game comleted but waiting for button move')
                    time.sleep(0.3)
                    if self.debug:
                        input('$ check hands if lucky:')
                        for s, d in self.engine.data.items():
                            if 'in' in d['status']:
                                self.site.parse_pocket_region(self.img, s)
                else:
                    logger.debug('button not moved, just continue loop')
                    self.wait_player_action()
                    logger.info('loop finished')

    def run_mc(self, timeout):
        """Runs MC analysis till timeout. This catches error where the amounts
        have varied too much from the current board by making the closes action"""
        logger.info('Running MC analysis')
        try:
            self.mc.run(timeout)
        except EngineError as e:
            logger.error(e)
            if self.debug:
                input('$ MC tree state bad')
            self.mc.init_tree()
            self.mc.run(timeout)

    def wait_player_action(self):
        """Think a little. Always think at least 1 second after every player
        actioned.
        First detect if the phase haven't moved on by checking board cards
        Secondly detect if current player isn't still thinking"""
        self.run_mc(1)

        # todo check if gg in expected
        # todo then scan for foe pockets and exit

        # check actions till phase has caught up
        # board will not trigger (as cards cleanedup) as we will have button_moved flag
        # this works when card dealt and players still need to act
        # this fails when normally finished last action, then when turn comes the whole phase is
        #   considered board phase...
        # check if phase from number of cards on board is what current player expected phase is
        if self.board_moved:
            input('$ board phase started')
            # this works only if 'board_moved' (looking to catch up if card added to board)
            logger.debug('board moved: engine phase: {}'.format(self.engine.phase))
            logger.debug('board moved: board map: {}'.format(self.engine.BOARD_MAP[len(self.engine.board)]))
            while self.engine.phase != self.engine.BOARD_MAP[len(self.engine.board)]:
                # if second last person folded, or others allin
                if self.engine.phase in [self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG]:
                    logger.info('exiting board phase as engine is now in {}'.format(self.engine.phase))
                    return
                self.check_player_action()
                self.run_mc(1)
                logger.debug('board moved: engine phase: {}'.format(self.engine.phase))
                logger.debug('board moved: board map: {}'.format(self.engine.BOARD_MAP[len(self.engine.board)]))
            self.board_moved = False
            self.check_names()
            input('$ board phase done')

        # an allin would end here
        if self.engine.phase == self.engine.PHASE_SHOWDOWN:
            logger.debug('Game in phase showdown, not checking players')
            time.sleep(1)
            return

        # as long as someone else is thinking, run analysis
        logger.info('Checking parsing player...')
        try:
            current_s = self.site.parse_thinking_player(self.img)
            logger.debug('Current thinking player is {}'.format(current_s))
        except ThinkingPlayerError as e:
            logger.error(e)
            if self.debug:
                input('$ check hands if lucky:')
                for s, d in self.engine.data.items():
                    if 'in' in d['status']:
                        self.site.parse_pocket_region(self.img, s)
        else:

            # if player is still thinking, then so can we
            if current_s == self.engine.q[0][0]:
                logger.debug('player to act {} is still thinking, so can we...'.format(current_s))
                self.run_mc(2)

            # player (in engine) to act is not the one thinking on screen
            # whilst it is not the expected player to act use the same current img to catch up
            else:
                while current_s != self.engine.q[0][0]:
                    logger.debug('taking action for {} as he is not thinking on screen'.format(self.engine.q[0][0]))
                    try:
                        self.check_player_action()
                    except BalancesError as e:
                        logger.warn(e)
                        return
                    self.run_mc(0.1)

    def check_player_action(self):
        """Check the player action, we are certain he is not thinking, thus he finished
        his turn
        Based on expected moves we can infer what he did

        Balance would change for: call, bet, raise, allin
        and not for: fold, check
        Fold is most common and easy to detect pocket cards
        Check (if so) is easy if balance did not change
        Otherwise balance has changed: balance and contrib change should match, just
            send bet to engine, it'll correct the action
        """
        s = self.engine.q[0][0]
        phase = self.engine.phase
        logger.info('check player {} action'.format(s))

        if 'fold' not in self.expected:
            logger.warn('End of game should not be here: {}'.format(self.expected))
            return

        # has pocket
        pocket = self.check_player_pocket(s)
        if not pocket:
            logger.debug('Player has folded')
            cmd = ['f']

        # balance changed
        else:
            balances_scr = self.check_player_balance(s)
            balance_diff = self.players[s]['balance'] - balances_scr[s]
            logger.debug('balance diff = {} (bal {} - scr {})'.format(
                balance_diff, self.players[s]['balance'], balances_scr[s]))
            if balance_diff < 0:
                raise BalancesError('Player {} already received {} winnings!'.format(s, balance_diff))

            contribs_scr = self.site.parse_contribs(self.img, s).get(s, 0)
            contrib_diff = contribs_scr - self.engine.data[s]['contrib']
            logger.debug('contrib diff= {} (scr {} - trib {})'.format(
                contrib_diff, contribs_scr, self.engine.data[s]['contrib']))

            # adjust contrib for blinds
            # eg1: had p7 15sb facing 90, thus diff/amt = 75
            # might be only when the board changed, and contrib no longer there
            if phase == self.engine.PHASE_PREFLOP and not self.board_moved:
                d = self.engine.data[s]
                if d['is_SB']:
                    balance_diff -= self.engine.sb_amt
                    logger.debug('SB {} deducted from balance_diff: {}'.format(self.engine.sb_amt, balance_diff))
                if d['is_BB']:
                    balance_diff -= self.engine.bb_amt
                    logger.debug('BB {} deducted from balance_diff: {}'.format(self.engine.bb_amt, balance_diff))

            # check
            if not balance_diff and not contrib_diff:
                logger.debug('No change in balance')
                if 'check' not in self.expected:
                    raise ValueError('No balance change on player but he cannot check')
                cmd = ['k']

            # chips moved
            else:
                # certain when both changes are equal (normally during phase)
                if balance_diff == contrib_diff:
                    logger.debug('amt = balance_diff')
                    amt = balance_diff
                # when table has gathered money
                elif not contribs_scr:
                    logger.debug('amt = balance_diff + contrib_diff')
                    amt = balance_diff + contrib_diff
                # assume balance change is what was the bet
                else:
                    logger.debug('amt = balance_diff')
                    amt = balance_diff
                cmd = ['b', amt]

        # do action, rotate, and get next actions
        logger.debug('parsed action {}'.format(cmd))
        action = self.engine.do(cmd)
        action_name = self.ACTIONS_MAP[action[0]]
        logger.info('Player {} did {} {}'.format(s, action_name, action))
        input('$ check player action')

        # cut tree based on action
        # do not have to cut tree when button moved
        if not self.button_moved:
            child_nodes = self.mc.tree.children(self.mc.tree.root)
            logger.debug('{} child nodes on tree {}'.format(len(child_nodes), self.mc.tree.root))
            # logger.info('nodes:\n{}'.format(json.dumps([n.tag for n in child_nodes], indent=4, default=str)))
            action_nodes = [n for n in child_nodes if n.data['action'].startswith(action_name)]
            # create new
            if not action_nodes:
                logger.warn('action {} not found in nodes {}'.format(
                    action_name,
                    [n.data['action'] for n in child_nodes]
                ))
                self.mc.init_tree()
                logger.debug('tree recreated')
            # subtree
            else:
                # direct
                if len(action_nodes) == 1:
                    node = action_nodes[0]
                    self.mc.tree = self.mc.tree.subtree(node.identifier)
                    logger.debug('Tree branched from single node {}'.format(node.tag))
                    logger.debug('tree branched from single node {}'.format(node.data))
                # proximity
                else:
                    nodes_diffs = {abs(n.data['amount'] - action[1]): n for n in action_nodes}
                    node = nodes_diffs[min(nodes_diffs.keys())]
                    self.mc.tree = self.mc.tree.subtree(node.identifier)
                    logger.debug('tree recreated from closest node {}'.format(node.tag))
                    logger.debug('tree recreated from closest node {}'.format(node.data))
                    # increment traversed level
                    self.mc.traversed_ceiling += 1
                if not node.tag.endswith('_{}_{}'.format(s, phase)):
                    raise ValueError('Finished player {} in {} not in subtree tag {}'.format(s, phase, node.tag))

        logger.debug('get next actions')
        self.expected = self.engine.available_actions()

    def check_player_pocket(self, s):
        """Check if player has back side of pocket, otherwise check what his cards are"""
        # check for back side
        if self.site.parse_pocket_back(self.img, s):
            logger.info('Player {} has pocket back'.format(s))
            pocket = ['__', '__']
        # check if showing cards
        else:
            pocket = self.site.parse_pocket_cards(self.img, s)
            # player is showing cards
            if pocket:
                self.engine.data[s]['hand'] = pocket
            # folded
            else:
                pocket = []
        logger.info('Player {} has pocket {}'.format(s, pocket))
        return pocket

    def check_player_balance(self, s):
        """Due to text appearing, double confirm empty or errors"""
        logger.info('Getting balance for player {}'.format(s))
        try:
            balances = self.site.parse_balances(self.img, s)
        except BalancesError as e:
            logger.info(e)
            balances = {s: 0}
        return balances

    def start_new_game(self):
        """Dealer button moved. Create new game.
        Get players that are still IN (not necessary to check pockets. The balances will return 0
            or empty if player left/out)
        Get small blind and big blind.
        Create new engine
        Create new MC
        Not waiting for a new game anymore.
        """
        # for joining table first time only
        if not self.btn:
            logger.info('init btn at {}'.format(self.btn_next))
            self.btn = self.btn_next
            return

        logger.info('btn moved: creating new game')
        self.btn = self.btn_next

        balances = self.check_balances()
        if 'pot' not in balances:
            logger.warn('New game did not really start')
            time.sleep(0.3)
            return

        self.check_names()
        contribs = self.site.parse_contribs(self.img)
        ante = self.check_ante(contribs)
        sb, bb = self.check_blinds(contribs)
        self.pre_start(balances, contribs, ante)

        logger.debug('creating engine...')
        self.engine = Engine(self.site.NAME, self.btn, self.players, sb, bb, ante)
        self.expected = self.engine.available_actions()
        logger.debug('seat {} available actions: {}'.format(
            self.engine.q[0][0],
            self.expected
        ))

        logger.debug('creating MC...')
        self.mc = MonteCarlo(engine=self.engine, hero=self.site.HERO)

        logger.info('new game created!')
        self.waiting_for_new_game = False
        self.button_moved = False
        self.board_moved = False

    def check_names(self):
        """Get name hashes and set it to players"""
        names = self.site.parse_names(self.img)
        for s, name in names.items():
            self.players[s]['name'] = name
        logger.info('checked player names')

    def check_balances(self):
        """Check balances of players for new game. Balances of players without a balance
        will not be returned, thus loop over seats and set status to out
        Also check for ante and set amount
        """
        balances = self.site.parse_balances(self.img)
        for s, balance in balances.items():
            if s == 'pot':
                continue
            self.players[s]['balance'] = balance
            # skip ante check for init
            if hasattr(self, 'engine'):
                balance_diff = self.players[s]['balance'] - balance
                if balance_diff:
                    logger.warn('player {} balance {} out by {}'.format(s, balance, balance_diff))
        logger.info('Player balances retrieved')
        return balances

    def check_ante(self, contribs):
        """Check ante from contrib total before gathering/matched"""
        ante = 0
        if 'total' in contribs:
            vs = sum([p['balance'] > 0 for p in self.players.values()])
            ante = contribs['total'] / vs
            logger.debug('Ante {} from total {} and vs {}'.format(ante, contribs['total'], vs))
            if not ante.is_integer():
                logger.warn('Ante {} is not integer'.format(ante))
        ante = int(round(ante))
        logger.info('Ante: {}'.format(ante))
        return ante

    def check_blinds(self, contribs):
        """SB and BB from ante structure"""
        for sb, bb in combinations(sorted(contribs.values()), 2):
            if sb * 2 == bb:
                logger.info('Blinds found: SB {} and BB {}'.format(sb, bb))
                return sb, bb
            logger.warn('Smallest SB {} is not 1:2 to BB {}'.format(sb, bb))
        return sb, bb

    def pre_start(self, balances, contribs, ante):
        """Add contribs back to balances for when engine take action it will subtract it
            again from matched/contrib.
        The status of players can be set if they have any balance/contrib"""
        for s in range(1, self.site.seats + 1):
            balance = balances.get(s, 0)
            contrib = contribs.get(s, 0)
            status = 1 if balance + contrib + ante > ante else 0
            self.players[s]['status'] = status
            if status:
                if contrib:
                    self.players[s]['balance'] += contrib
                    logger.debug('player {} contrib {} added back to balance {}'.format(
                        s, contrib, balance))
                if ante:
                    self.players[s]['balance'] += ante
                    logger.debug('player {} ante {} added back to balance {}'.format(
                        s, ante, balance))

        logger.info('pre start done')
        if self.debug:
            input('$ check balances/contribs/ante')
        
    def finish_it(self):
        """Finish the game. Calculate the winner and winnings
         * set board
         * finish players moves by checking balance only (check/fold)
         * till gg state,

        A player can fold, then there is only 1 player left allin, then the engine
            will finish the game (empty actions) and allocate the funds
        """
        logger.info('finish the game')
        if self.debug:
            input('$ finishing started')

        # todo img already of new round
        # todo but somewhere hands should be scraped

        # if we do not have a winner then estimate winner from balances
        if not self.engine.winner:
            balances = {}
            for s, d in self.engine.data.items():
                if 'in' not in d['status']:
                    continue
                # todo fix check_player_balance to use here
                try:
                    balances.update(self.site.parse_balances(self.img, s))
                except BalancesError as e:
                    logger.error(e)
                    balances[s] = 0
            logger.debug('current balances = {}'.format(balances))

            balances_diffs = {
                s: cb - self.players[s]['balance']
                for s, cb in balances.items()
            }
            logger.debug('balance diffs: {}'.format(balances_diffs))

            # get highest gain and set that as the winner
            # todo handle draws and split pots
            winner = max(balances_diffs.items(), key=itemgetter(1))[0]
            logger.debug('Winner is player {}'.format(winner))

            # contribs from screen (to add ante and blinds back)
            contribs_scr = self.site.parse_contribs(self.img)
            logger.debug('contribs from screen: {}'.format(contribs_scr))

            # have to try to get actions taken for betting or calling for correct stats
            while self.expected and 'gg' not in self.expected:
                s = self.engine.q[0][0]

                # e g player had contrib 30, facing 60, and folded. next was 30 SB and 4 ante
                # total diff = -64
                # with contrib removed = -34
                # has to be more than short 34 >= 30 (that's true, but)
                # check if equal and if not check if equal start blind diff
                contribs = {s: d['contrib'] for s, d in self.engine.data.items()}
                contrib_short = max(contribs.values()) - contribs[s]
                logger.debug('player {} contrib {} and short = {}'.format(s, contribs[s], contrib_short))

                diff = balances_diffs[s]
                lost_money = False
                # player gained money (cannot be zero as ante had to be deducted)
                if diff <= 0:

                    # add contrib back (engine will deduct when gathering)
                    diff = diff + contribs[s]
                    logger.debug('added contrib {} back to player {} = diff {}'.format(contribs[s], s, diff))

                    # scr could be where player receives money,
                    # button always moved, so it is certain that antes and blinds are on the screen
                    if diff:
                        # add ante back if total
                        # todo deduct correct ante amount from next game (even if calling method, then player may be out)
                        diff += self.engine.ante
                        logger.debug('added ante {} back to player {} = diff {}'.format(self.engine.ante, s, diff))

                        # if player has contrib on screen then deduct it
                        # no need to calculate it is definitely next game SB/BB/b
                        diff += contribs_scr.get(s, 0)
                        logger.debug('added scr {} back to player {} = diff {}'.format(contribs_scr.get(s, 0), s, diff))

                    # if player still have lost money, then he really lost money
                    if diff < 0:
                        lost_money = True
                        # diff should now be equal to short
                        if -diff != contrib_short:
                            logger.warn('Expected player {} diff {} to be equal to short {}'.format(s, diff, contrib_short))

                logger.debug('Player {} lost {}: {}'.format(s, diff, lost_money))

                # faced the aggro -> call
                if contrib_short and lost_money:
                    cmd = ['c']
                # scared from aggro -> fold
                elif contrib_short and not lost_money:
                    # winner called and won, but losers folded
                    if s == winner:
                        cmd = ['c']
                    else:
                        cmd = ['f']
                # made a bet but lost
                elif not contrib_short and lost_money:
                    if s == winner:
                        raise BalancesError('Winner cannot make bet and lose')
                    cmd = ['b', -diff]
                # no bet/call but no money lost either -> check
                elif not contrib_short and not lost_money:
                    cmd = ['k']
                    # if just the two left and they did not see the river, he folded
                    # for some fucking stupid dumb reason
                    if s != winner and len(self.engine.board) < 5 and self.engine.rivals == 2:
                        cmd = ['f']
                        logger.info('Changed check to fold for loser')
                else:
                    raise BalancesError('What did player {} do?'.format(s))

                action = self.engine.do(cmd)
                action_name = self.ACTIONS_MAP[action[0]]
                logger.info('Player {} did {} {}'.format(s, action_name, action))
                if self.debug:
                    input('$ check player action')

                self.expected = self.engine.available_actions()

            # from while loop: 'gg' in expected or empty
            if self.expected:
                cmd = ['gg', winner]
                logger.debug('final gg cmd = {}'.format(cmd))
                self.engine.do(cmd)

        self.waiting_for_new_game = True
        ES.save_game(self.players, self.engine.data, self.engine.site_name, self.engine.vs)
        logger.info('Game over! Player {} won!'.format(self.engine.winner))
        input('$ check gg')

    def cards(self):
        """Generate cards for a site"""
        self.site.generate_cards()


    def chips(self):
        """Generate cards for a site"""
        self.site.generate_chips()

