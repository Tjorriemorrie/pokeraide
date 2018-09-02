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
from scraper.sites.base import SiteException, NoDealerButtonError, PocketError, ThinkingPlayerError, BalancesError, \
    BoardError, PlayerActionError, GamePhaseError, BalanceNotFound
from scraper.sites.coinpoker.site import CoinPoker
from scraper.sites.pokerstars.site import PokerStars
from scraper.sites.partypoker.site import PartyPoker
from scraper.sites.zynga.site import Zynga
from view import View


logger = logging.getLogger(__name__)


class Scraper(View):
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
        elif site_name == 'cp':
            self.site = CoinPoker(seats, debug)
        else:
            raise NotImplementedError('{} is not implemented'.format(site_name))

        self.img = None

        # starting balance zero for ante on init
        self.players = {
            s: {
                'name': 'joe',
                'balance': 290000,
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

        # if tlc/button cannot be found, drop existing game after 5 seconds
        self.drop_game_start = None

        # on each player's turn, update balances
        self.last_thinking_seat = None

        # orphan call from previous first require thinking
        self.last_thinking_phase = None

    def load_files(self):
        """Replays through images saved during debug run"""
        files = []
        for entry in os.scandir(self.PATH_DEBUG):
            if not entry.is_file() or entry.name.startswith('.'):
                logger.debug('skipping file {}'.format(entry.name))
                continue
            files.append(entry.path)
        logger.info(f'loading {len(files)} files')
        self.files = sorted(files)

    def take_screen(self):
        """Get screen image
        Takes screen shot or load file if replaying
        Stats: 9.58%
        """
        logger.info('taking screen shot')
        while True:
            if not self.replay:
                # 3840 x 2400 mac retina
                # pokerstars
                # img = ImageGrab.grab((1920, 600, 3840, 2400))
                # coinpoker
                img = ImageGrab.grab((1760, 700, 3840, 2300))
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
                    if self.drop_game_start:
                        self.drop_game_start = None
                        logger.info('Continuing existing game')
                except SiteException as e:
                    logger.info(e)
                    if not self.waiting_for_new_game:
                        if not self.drop_game_start:
                            self.drop_game_start = time.time()
                            logger.warning('Drop game beginning...')
                        elif time.time() - self.drop_game_start > 5:
                            self.waiting_for_new_game = True
                            self.button_moved = False
                            logger.error('Game state aborted!')
                    if self.debug:
                        input('$ really no tlc?')
                        img_full.show()
                        input('$')
                    time.sleep(1)
                    continue

                try:
                    btn = self.site.parse_dealer(self.img)
                except NoDealerButtonError as e:
                    logger.warning(e)
                    time.sleep(0.6)
                    break
                else:
                    if not self.btn:
                        logger.debug('button initialised at {} on joining table'.format(btn))
                        self.btn = btn
                    elif btn != self.btn:
                        self.button_moved = True
                        self.btn_next = btn
                        logger.debug(f'button moved to {btn}!')

                self.check_board()

                # DONE
                # if self.debug:
                #     input('$ check hands if lucky:')
                #     for s, d in self.engine.data.items():
                #         if 'in' in d['status']:
                #             self.site.parse_pocket_region(self.img, s)

            # always break (only continue when tlc & button found)
            break

    def check_board(self):
        """Check board and handles exception raised if card not identified. Card animation
        could be covering the cards. Instead of retrying rather return existing board"""
        if not hasattr(self, 'engine'):
            logger.info('Not checking board when no engine present')
            return

        if len(self.engine.board) >= 5:
            logger.info(f'Board already identified as {self.engine.board}')
            return

        logger.info('checking board...')
        board = self.site.parse_board(self.img)

        # works like this on CP
        # if not self.button_moved and not self.waiting_for_new_game and len(board) < len(self.engine.board):
        #     raise BoardError('Board cannot be removed without button moving')

        if len(board) > len(self.engine.board):
            logger.debug(f'The board changed with {set(board) - set(self.engine.board)}')
            self.engine.board = board
            self.board_moved = True

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
                elif self.engine.phase == self.engine.PHASE_SHOWDOWN:
                    if len(self.engine.board) != 5:
                        logger.info(f'Still drawing on board {self.engine.board}')
                    else:
                        self.check_showdown_winner()
                    time.sleep(1)
                elif self.engine.phase == self.engine.PHASE_GG:
                    pot, total = self.site.parse_pot_and_total(self.img)
                    if not pot and not total:
                        logger.info(f'Game completed and pot allocated')
                        self.finish_it()
                    else:
                        logger.info('Game completed but waiting for button move')
                        time.sleep(0.5)
                else:
                    logger.debug('button not moved, just continue loop')
                    self.wait_player_action()
                    logger.info('loop finished')

    def run_mc(self, timeout):
        """Runs MC analysis till timeout. This catches error where the amounts
        have varied too much from the current board by making the closes action"""
        logger.info('Running MC analysis')

        if self.debug:
            timeout = 0.1

        if 'in' not in self.engine.data[self.site.HERO]['status']:
            time.sleep(0.2)
        else:
            try:
                self.mc.run(timeout)
            except EngineError as e:
                logger.error(e)
                if self.debug:
                    input('$ MC tree state bad')
                self.mc.init_tree()
                self.mc.run(timeout)
        self.print()

    def wait_player_action(self):
        """Think a little. Always think at least 1 second after every player
        actioned.
        First detect if the phase haven't moved on by checking board cards
        Secondly detect if current player isn't still thinking"""
        self.run_mc(0.2)

        # todo check if gg in expected
        # todo then scan for foe pockets and exit

        # check actions till phase has caught up
        # board will not trigger (as cards cleanedup) as we will have button_moved flag
        # this works when card dealt and players still need to act
        # this fails when normally finished last action, then when turn comes the whole phase is
        #   considered board phase...
        # check if phase from number of cards on board is what current player expected phase is
        if self.board_moved:
            # this works only if 'board_moved' (looking to catch up if card added to board)
            mapped_board = self.engine.BOARD_MAP[len(self.engine.board)]
            while self.engine.phase != mapped_board:
                logger.debug(f'board at: {mapped_board} and engine at {self.engine.phase}')
                # if second last person folded, or others allin
                if self.engine.phase in [self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG]:
                    logger.info(f'Engine caught up to {mapped_board}, but gg & sd handled separately')
                    return
                self.check_player_action()
                self.run_mc(0.3)
            self.board_moved = False
            # do not update last_thinking_phase as previous phase text still shows, giving wrong action

        # an allin would end here
        if self.engine.phase == self.engine.PHASE_SHOWDOWN:
            logger.debug('Game in phase showdown, not checking players')
            time.sleep(0.8)
            return

        # as long as someone else is thinking, run analysis
        logger.info('Checking parsing player...')
        try:
            current_s = self.site.parse_thinking_player(self.img)
            logger.debug(f'Current thinking player is {current_s}')

        except ThinkingPlayerError as e:
            logger.debug(f'Current thinking player is unknown, estimating action for {self.engine.s}')
            # during any phase, if pot removed, then have to loop to find winner with contrib
            pot, total = self.site.parse_pot_and_total(self.img)
            if not pot:
                while self.engine.phase not in [self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG] \
                        and self.engine.phase == self.last_thinking_phase:
                    try:
                        self.check_player_action()
                    except PlayerActionError as exc:
                        # happened when player did not move, but thinking already moved. wtf
                        return
                if self.engine.phase == self.engine.PHASE_SHOWDOWN:
                    self.check_showdown_winner()
                elif self.engine.phase == self.engine.PHASE_GG:
                    self.finish_it()
            # else we can check for action considering we are in same phase
            elif self.last_thinking_phase == self.engine.phase:
                try:
                    self.check_player_action()
                except PlayerActionError as exc:
                    # happened when player did not move, but thinking already moved. wtf
                    return

        else:
            self.last_thinking_phase = self.engine.phase

            # if player is still thinking, then so can we
            if current_s == self.engine.q[0][0]:
                logger.debug(f'player to act {current_s} is still thinking, so can we...')
                if current_s != self.last_thinking_seat:
                    self.check_player_name(current_s)
                    self.check_player_balance(current_s)
                    self.last_thinking_seat = current_s
                # longer thinking time for hero
                thinking_time = 2 if current_s == self.site.HERO else 1
                self.run_mc(thinking_time)

            # player (in engine) to act is not the one thinking on screen
            # whilst it is not the expected player to act use the same current img to catch up
            else:
                while current_s != self.engine.q[0][0]:
                    logger.debug(f'taking action for {self.engine.q[0][0]} as he is not thinking on screen')
                    if self.engine.phase in [self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG]:
                        logger.warning(f'exiting board phase as engine is now in {self.engine.phase}')
                        return
                    try:
                        self.check_player_action()
                    except (BalancesError, PlayerActionError) as e:
                        logger.warning(e)
                        # retry with new screen
                        return
                    self.run_mc(0.1)

    def check_player_action(self):
        """It is certain the expected player is not thinking, thus he finished
        his turn: check the player action.
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
        logger.info(f'check player {s} action')
        logger.info(f'expecting one of {self.expected} during {phase}')

        if 'fold' not in self.expected:
            logger.error(f'fold is not in {self.expected}')
            raise PlayerActionError('End of game should not be here: player cannot fold')

        pocket = self.check_players_pockets(s)
        contrib = self.site.parse_contribs(self.img, s)
        cmd = self.site.infer_player_action(self.img, s, phase, pocket, contrib or 0, self.engine,
                                            self.engine.current_pot, self.board_moved, self.expected)

        # do action, rotate, and get next actions
        logger.debug(f'parsed action {cmd}')
        action = self.engine.do(cmd)
        action_name = self.ACTIONS_MAP[action[0]]
        logger.info(f'Player {s} did {action_name} {action}')

        # cut tree based on action
        # do not have to cut tree when button moved
        if not self.button_moved:
            # self.mc.analyze_tree()
            child_nodes = self.mc.tree.children(self.mc.tree.root)
            logger.debug(f'{len(child_nodes)} child nodes on tree {self.mc.tree.root}')
            # logger.info('nodes:\n{}'.format(json.dumps([n.tag for n in child_nodes], indent=4, default=str)))
            action_nodes = [n for n in child_nodes if n.data['action'].startswith(action_name)]
            # create new
            if not action_nodes:
                logger.warning(f'action {action_name} not found in nodes {[n.data["action"] for n in child_nodes]}')
                self.mc.init_tree()
                logger.debug('tree recreated')
            # subtree
            else:
                # direct
                if len(action_nodes) == 1:
                    node = action_nodes[0]
                    self.mc.tree = self.mc.tree.subtree(node.identifier)
                    logger.debug(f'Tree branched from single node {node.tag}')
                    logger.debug(f'tree branched from single node {node.data}')
                # proximity
                else:
                    nodes_diffs = {abs(n.data['amount'] - action[1]): n for n in action_nodes}
                    node = nodes_diffs[min(nodes_diffs.keys())]
                    self.mc.tree = self.mc.tree.subtree(node.identifier)
                    logger.debug(f'tree recreated from closest node {node.tag}')
                    logger.debug(f'tree recreated from closest node {node.data}')
                    # increment traversed level
                    self.mc.traversed_ceiling += 1
                if not node.tag.endswith('_{}_{}'.format(s, phase)):
                    raise ValueError(f'Finished player {s} in {phase} not in subtree tag {node.tag}')

        logger.debug('get next actions')
        self.expected = self.engine.available_actions()

    def check_players_pockets(self, filter_seat=None):
        """Check if player has back side of pocket, otherwise check what his cards are"""
        pockets = {}
        for i in range(self.site.seats):
            s = i + 1
            if filter_seat and filter_seat != s:
                continue

            # check for back side
            if self.site.parse_pocket_back(self.img, s):
                logger.info(f'Player {s} has hole cards')
                pockets[s] = self.site.HOLE_CARDS
                continue

            # check if showing cards
            pocket = self.site.parse_pocket_cards(self.img, s)
            if pocket:
                logger.info(f'Player {s} is showing {pocket}')
                pockets[s] = pocket
                if hasattr(self, 'engine'):
                    self.engine.data[s]['hand'] = pocket
                continue

            logger.info(f'Player {s} has no cards')

        if filter_seat:
            return pockets.get(filter_seat)

        return pockets

    def check_player_name(self, seat):
        """Get name hashes and set it to players"""
        name = self.site.parse_names(self.img, seat)
        if name:
            self.players[seat]['name'] = name
            logger.info(f'Player {seat} name is {name}')

    def check_player_balance(self, seat):
        """Update player balances"""
        balance = self.site.parse_balances(self.img, seat)
        if balance:
            self.players[seat]['balance'] = balance
            logger.debug(f'Player {seat} balance is {balance}')

    def start_new_game(self):
        """Dealer button moved: create new game!

        Get players that are still IN: some sites have balances always available, but some are
        blocked by text. Thus at least 2 pockets are required.

        Get small blind and big blind and ante.
        Create new engine
        Create new MC
        Not waiting for a new game anymore.
        """
        # for joining table first time only
        if not self.btn:
            logger.info(f'init button at {self.btn_next}')
            self.btn = self.btn_next
            return

        logger.info('button moved: creating new game')
        self.btn = self.btn_next

        # there must be pockets for a game to have started
        pockets = self.check_players_pockets()
        if len(pockets) < 2:
            logger.debug(f'Game has not started as there are {len(pockets)} pockets right now')
            time.sleep(0.1)
            return

        # pot and total are required for a game to have started
        # cannot check pot anymore for when no ante, no pot in middle :(
        pot, total = self.site.parse_pot_and_total(self.img)
        if not total:
            logger.debug(f'Game has not started as there are no pot or total right now')
            time.sleep(0.1)
            return

        # contribs are required for blinds!
        contribs = self.site.parse_contribs(self.img)
        if len(contribs) < 2:
            logger.debug(f'Game has not started as there are {len(contribs)} contribs right now')
            time.sleep(0.1)
            return

        # not doing any more checks, since if they have cards and there is a pot: game on!
        # self.check_player_name()  # checked at flop to save time during start
        # always have text on it, so who cares
        # balances = self.site.parse_balances(self.img)

        vs_players = set(list(pockets.keys()) + list(contribs.keys()))
        ante = self.check_ante(len(vs_players), pot)
        sb, bb = self.check_blinds(contribs)

        self.pre_start(vs_players, contribs, ante)

        logger.debug('creating engine...')
        self.engine = Engine(self.site.NAME, self.btn, self.players, sb, bb, ante)

        # why does 'hand' return?
        self.expected = self.engine.available_actions()
        logger.debug(f'seat {self.engine.q[0][0]} available actions: {self.expected}')

        logger.debug('creating MC...')
        self.mc = MonteCarlo(engine=self.engine, hero=self.site.HERO)

        self.post_start(pockets)

        logger.info('new game created!')
        self.waiting_for_new_game = False
        self.button_moved = False
        self.board_moved = False

    def check_ante(self, vs, pot):
        """Check ante from contrib total before gathering/matched. Using player balances instead
        of recently scraped balances."""
        # no pot so there is no ante paid yet
        if not pot:
            return 0
        ante = pot / vs
        logger.debug(f'Ante {ante} from current pot {pot} and vs {vs}')
        if not ante.is_integer():
            logger.warning(f'Ante {ante} is not integer')
        ante = int(round(ante))
        logger.info(f'Ante: {ante}')
        return ante

    def check_blinds(self, contribs):
        """SB and BB from ante structure. Since hero blocks the play, this should be always found."""
        contribs_sorted = sorted([c for c in contribs.values() if c])
        sb, bb, *_ = contribs_sorted
        logger.info(f'Blinds found: SB {sb} and BB {bb}')
        if sb * 2 != bb:
            logger.warning('Smallest SB is not 1:2 to BB')
        return sb, bb

    def pre_start(self, vs_players, contribs, ante):
        """Add contribs back to balances for when engine take action it will subtract it
            again from matched/contrib.
        The status of players can be set if they have any balance/contrib"""
        for s in range(1, self.site.seats + 1):
            status = s in vs_players
            self.players[s]['status'] = status
            if not status:
                continue

            # balance might not be scraped as it might be obscured by text
            # if s in balances:
            #     balance = balances[s]
            #     balance_diff = self.players[s]['balance'] - balance
            #     if balance_diff:
            #         logger.warning(f'player {s} balance {balance} out by {balance_diff}')
            #     self.players[s]['balance'] = balance

            # if player is blind, then return money for engine to subtract on init. same for ante.
            # BUT with coinpoker, the balances are not scraped
            # so no need to add it back
            # contrib = contribs.get(s, 0)
            # if contrib:
            #     self.players[s]['balance'] += contrib
            #     logger.debug(f'player {s} contrib {contrib} added back to balance')
            # if ante:
            #     self.players[s]['balance'] += ante
            #     logger.debug(f'player {s} ante {ante} added back to balance')

        logger.info('pre start done')
        if self.debug:
            logger.info('Is all the contribs/ante correct?')

    def post_start(self, pockets):
        """Post start. Engine and MC has been created.
        Set hero hand immediately for analysis of EV"""
        hero = self.site.HERO
        pocket = pockets.get(hero)
        if pocket:
            self.engine.data[hero]['hand'] = pocket
            logger.info(f'Hero (p{hero}) hand set to {pocket}')
        else:
            logger.error('No hero pocket found!')
        self.print()

    def finish_it(self):
        """Finish the game. Should already have winner."""
        logger.info('finish the game')
        if not self.engine.winner:
            raise GamePhaseError(f'Game does not have winner but in phase {self.engine.phase}')
        self.waiting_for_new_game = True
        ES.save_game(self.players, self.engine.data, self.engine.site_name, self.engine.vs, self.engine.board)
        logger.info(f'Game over! Player {self.engine.winner} won!')

    def check_showdown_winner(self):
        """Winner can be identified by no pot amounts but one contrib"""
        if 'gg' not in self.expected:
            logger.debug(f'gg not in expected {self.expected}')
            return

        for s, d in self.engine.data.items():
            if 'in' in d['status'] and d['hand'] == self.site.HOLE_CARDS:
                self.check_players_pockets(s)

        # todo add check for board is 5 cards

        pot, total = self.site.parse_pot_and_total(self.img)
        if pot or total:
            logger.debug(f'pot {pot} or total {total} has values')
            return

        contribs = self.site.parse_contribs(self.img)
        # can contain pot and sidepots
        if len(contribs) < 1:
            logger.debug(f'There is not a single contrib but {contribs}')
            return

        # todo support split pot winners
        winner = max(contribs.items(), key=itemgetter(1))[0]
        logger.info(f'Winner of showdown is {winner}')
        cmd = ['gg', winner]
        self.engine.do(cmd)

        self.waiting_for_new_game = True
        ES.save_game(self.players, self.engine.data, self.engine.site_name, self.engine.vs, self.engine.board)
        logger.info(f'Game over! Player {self.engine.winner} won!')

    def cards(self):
        """Generate cards for a site"""
        self.site.generate_cards()

    def chips(self):
        """Generate cards for a site"""
        self.site.generate_chips()

    def calc_board_to_pocket_ratio(self):
        self.site.calc_board_to_pocket_ratio()

