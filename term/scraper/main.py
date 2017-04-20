import datetime
from itertools import combinations
import json
import logging
import os
from PIL import Image, ImageGrab
from retrace import retry
import time

from engine.engine import Engine
from mc.mc import MonteCarlo
from scraper.sites.base import SiteException, NoDealerButtonError, PocketError, ThinkBarError
from scraper.sites.pokerstars.site import PokerStars
from scraper.sites.partypoker.site import PartyPoker
from scraper.sites.zynga.site import Zynga


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
        self.logger = logging.getLogger()
        self.debug = debug
        self.logger.debug('Debug {}'.format(self.debug))
        self.observe = observe
        self.logger.debug('Observing {}'.format(self.observe))
        self.replay = replay
        self.logger.debug('Replay {}'.format(self.replay))
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

        self.players = {
            s: {
                'name': 'joe',
                'balance': 1000,
                'status': 1,
            }
            for s in range(1, seats + 1)
        }
        self.sb = 10
        self.bb = 20
        self.btn = None
        # not currently in a game
        self.waiting_for_new_game = True
        # button moved
        self.button_moved = False

    def load_files(self):
        """Replays through images saved during debug run"""
        self.files = []
        for entry in os.scandir(self.PATH_DEBUG):
            if not entry.is_file() or entry.name.startswith('.'):
                self.logger.debug('skipping file {}'.format(entry.name))
                continue
            self.files.append(entry.path)
        self.logger.info('loading {} files'.format(len(self.files)))

    def take_screen(self):
        """Get screen image
        Takes screen shot or load file if replaying
        """
        if not self.replay:
            self.logger.debug('taking screen shot')
            img = ImageGrab.grab()
            if self.debug:
                img_file = os.path.join(self.PATH_DEBUG, '{}.png'.format(datetime.datetime.utcnow()))
                img.save(img_file)
                self.logger.debug('file saved locally to {}'.format(img_file))
        else:
            img_path = self.files.pop(0)
            self.logger.debug('loading file: {}'.format(img_path))
            img = Image.open(img_path)
        img_full = img.convert('L')
        if not self.observe:
            self.img = self.site.parse_top_left_corner(img_full)
            btn = self.check_dealer()
            if btn != self.btn:
                self.button_moved = True
                self.btn_next = btn

    def run(self):
        """Run application"""
        while True:
            self.take_screen()

            if self.observe:
                continue

            # we are ready for a new game
            if self.waiting_for_new_game:
                self.logger.debug('waiting for a new game')
                if self.button_moved:
                    self.logger.debug('button moved and waiting for new game: create new game')
                    self.start_new_game()
                else:
                    self.logger.info('just waiting for new game to start...')
                    time.sleep(1)
                    continue
            # else game in progress
            else:
                self.logger.debug('still playing same game')
                if not self.button_moved:
                    self.logger.debug('button not moved, just continue loop')
                    self.wait_player_action()
                    self.logger.info('loop finished')
                    # self.img.show()
                    self.logger.debug('=' * 150)
                    input('$ run normal')
                    self.logger.debug('=' * 150)
                else:
                    self.logger.debug('button moved! we need to finish up what engine is')
                    self.finish_it()

    def check_dealer(self):
        """Get dealer button location"""
        backoff = 0
        while True:
            try:
                return self.site.parse_dealer(self.img)
            except NoDealerButtonError as e:
                self.logger.error(e)
                backoff += 1
                self.logger.debug('trying again in {} sec'.format(backoff))
                time.sleep(backoff)
                self.take_screen()

    def wait_player_action(self):
        """Think a little. Always think at least 1 second after every player
        actioned.
        First detect if the phase haven't moved on by checking board cards
        Secondly detect if current player isn't still thinking"""
        timeout = 1
        self.mc.timeout = timeout
        self.mc.run()

        # todo check if gg in expected
        # todo then scan for foe pockets and exit

        # check actions till phase has caught up
        # board will not trigger (as cards cleanedup) as we will have button_moved flag
        # this works when card dealt and players still need to act
        # this fails when normally finished last action, then when turn comes the whole phase is
        #   considered board phase...
        # check if phase from number of cards on board is what current player expected phase is
        phase = self.engine.phase
        board = self.site.parse_board(self.img)
        if board != self.engine.board:
            self.logger.debug('The board changed with {}'.format(set(board) - set(self.engine.board)))
            board_phase = self.engine.BOARD_MAP[len(board)]
            player_tag = self.mc.tree.children(self.mc.tree.root)[0].tag
            self.logger.debug('board_phase={} vs player_tag={}'.format(board_phase, player_tag))
            while not player_tag.endswith('_{}'.format(board_phase)):
                self.logger.warn('current player is {} but only {} board cards'.format(player_tag, len(board)))
                self.check_player_action()
                self.logger.debug('=' * 150)
                input('$ board phase')
                self.logger.debug('=' * 150)
                self.mc.run()
                player_tag = self.mc.tree.children(self.mc.tree.root)[0].tag
            self.engine.board = board
            self.logger.debug('board set to {}'.format(board))
            input('$ board done')

        engine_s = self.engine.q[0][0]
        self.logger.debug('Is player {} thinking?'.format(engine_s))
        # as long as someone else is thinking, run analysis
        # but try it at least twice, just to prevent animation taking away think bar
        failed_before = False
        while True:
            try:
                current_s = self.site.parse_thinking_player(self.img)
                if current_s != engine_s:
                    self.logger.debug('Player finished thinking, it is now {}'.format(current_s))
                    return self.check_player_action()
            except ThinkBarError as e:
                input('really no think bar?')
                if failed_before:
                    self.logger.exception(e)
                    return
                self.logger.error(e)
                failed_before = True
            else:
                failed_before = False

                # if player is still thinking, then so can we
                self.logger.debug('player to act {} is still thinking, so can we...'.format(current_s))
                timeout += 0.3
                self.mc.timeout = timeout
                self.mc.run()

                self.take_screen()
                # exit if new game already started!
                if self.button_moved:
                    self.logger.info('button moved, not the time to worry about thinkbar')
                    return

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
        self.logger.info('check player {} action'.format(s))

        if 'fold' not in self.expected:
            raise ValueError('wtf are these expected? {}'.format(self.expected))

        # has pocket
        if not self.site.parse_pocket(self.img, s):
            self.logger.debug('Player has folded')
            cmd = ['f']

        # balance changed
        else:
            balances_scr = self.site.parse_balances(self.img, s)
            balance_diff = self.players[s]['balance'] - balances_scr[s]
            self.logger.debug('balance diff = {} (bal {} - scr {})'.format(
                balance_diff, self.players[s]['balance'], balances_scr[s]))

            contribs_scr = self.site.parse_contribs(self.img, s).get(s, 0)
            contrib_diff = contribs_scr - self.engine.data[s]['contrib']
            self.logger.debug('contrib diff= {} (scr {} - trib {})'.format(
                contrib_diff, contribs_scr, self.engine.data[s]['contrib']))

            # check
            if not balance_diff and not contrib_diff:
                self.logger.debug('No change in balance')
                if 'check' not in self.expected:
                    raise ValueError('No balance change on player but he cannot check')
                cmd = ['k']

            # chips moved
            else:
                # certain when both changes are equal (normally during phase)
                if balance_diff == contrib_diff:
                    amt = balance_diff
                # when table has gathered money
                elif not contribs_scr:
                    amt = balance_diff + contrib_diff
                # catch
                else:
                    raise NotImplementedError('WTF todo when contrib still on screen?')
                cmd = ['b', amt]

        # do action, rotate, and get next actions
        self.logger.debug('parsed action {}'.format(cmd))
        action = self.engine.do(cmd)
        action_name = self.ACTIONS_MAP[action[0]]
        self.logger.debug('engine actioned {} {}'.format(action_name, action))

        # cut tree based on action
        # do not have to cut tree when button moved
        if not self.button_moved:
            child_nodes = self.mc.tree.children(self.mc.tree.root)
            self.logger.debug('{} child nodes on tree {}'.format(len(child_nodes), self.mc.tree.root))
            self.logger.info('nodes:\n{}'.format(json.dumps([n.tag for n in child_nodes], indent=4, default=str)))
            action_nodes = [n for n in child_nodes if n.data['action'].startswith(action_name)]
            # create new
            if not action_nodes:
                self.logger.warn('action {} not found in nodes {}'.format(
                    action_name,
                    [n.data['action'] for n in child_nodes]
                ))
                self.mc.init_tree()
                self.logger.debug('tree recreated')
            # subtree
            else:
                # direct
                if len(action_nodes) == 1:
                    node = action_nodes[0]
                    self.mc.tree = self.mc.tree.subtree(node.identifier)
                    self.logger.debug('Tree branched from single node {}'.format(node.tag))
                    self.logger.debug('tree branched from single node {}'.format(node.data))
                # proximity
                else:
                    nodes_diffs = {abs(n.data['amount'] - action[1]): n for n in action_nodes}
                    node = nodes_diffs[min(nodes_diffs.keys())]
                    self.mc.tree = self.mc.tree.subtree(node.identifier)
                    self.logger.debug('tree recreated from closest node {}'.format(node.tag))
                    self.logger.debug('tree recreated from closest node {}'.format(node.data))
                if not node.tag.endswith('_{}_{}'.format(s, phase)):
                    raise ValueError('Finished player {} in {} not in subtree tag {}'.format(s, phase, node.tag))

            # self.logger.warn(json.dumps(json.loads(self.mc.tree.to_json()), indent=4, default=str))
            # child_nodes = self.mc.tree.children(self.mc.tree.root)
            # self.logger.debug('{} child nodes on new tree {}'.format(len(child_nodes), self.mc.tree.root))
            # self.logger.info('new nodes:\n{}'.format(json.dumps([n.tag for n in child_nodes], indent=4, default=str)))
            # input('tree')

        self.logger.debug('get next actions')
        self.expected = self.engine.available_actions()

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
            self.logger.info('init btn at {}'.format(self.btn_next))
            self.btn = self.btn_next
            return

        self.logger.info('btn moved: creating new game')
        self.btn = self.btn_next

        self.check_names()

        balances = self.check_balances()

        self.check_contribs()

        self.logger.debug('creating engine...')
        self.engine = Engine(self.site.NAME, self.btn, self.players, self.sb, self.bb)
        self.expected = self.engine.available_actions()
        self.logger.debug('seat {} available actions: {}'.format(
            self.engine.q[0][0],
            self.expected
        ))

        self.logger.debug('creating MC...')
        self.mc = MonteCarlo(engine=self.engine, hero=self.site.HERO)

        self.post_start(balances)

        self.logger.info('new game created!')
        self.waiting_for_new_game = False
        self.button_moved = False

    def check_names(self):
        """Get name hashes and set it to players"""
        names = self.site.parse_names(self.img)
        for s, name in names.items():
            self.players[s]['name'] = name
        self.logger.info('checked player names')

    def check_balances(self):
        """Check balances of players"""
        balances = self.site.parse_balances(self.img)
        for s, balance in balances.items():
            if s == 'pot':
                continue
            if abs(self.players[s]['balance'] - balance):
                self.logger.warn('player {} balance {} out by {}'.format(
                    s, balance, abs(self.players[s]['balance'] - balance)))
            self.players[s]['balance'] = balance
            self.players[s]['status'] = 1 if balance else 0
        self.logger.info('checked player balances')
        return balances

    def check_contribs(self):
        """Check contribs of players"""
        contribs = self.site.parse_contribs(self.img)
        for sb, bb in combinations(sorted(contribs.values()), 2):
            if sb * 2 == bb:
                self.sb = sb
                self.bb = bb
                self.logger.debug('Blinds found: SB {} and BB {}'.format(sb, bb))
                break
            self.logger.warn('Smallest SB {} is not 1:2 to BB {}'.format(sb, bb))

    def post_start(self, balances):
        """Reset balances amounts after sb and bb.
        UTG could have acted and his balance would be incorrect, but hopefully the
            scraping would be fast enough.
        Set pot value to include antes.
        Player status ignored here as they could go all in with sb"""
        for s, balance in balances.items():
            if s == 'pot':
                # self.engine.pot = balance
                # self.logger.debug('pot set to {}'.format(balance))
                self.logger.debug('ignoring balance pot value {}'.format(balance))
            else:
                self.players[s]['balance'] = balance
                # adding SB and BB amounts back to balances, as it is only subtracted when
                # money is gathered at end of phase
                data = self.engine.data[s]
                self.logger.debug('data = {}'.format(data))
                if data.get('is_SB') or data.get('is_BB'):
                    self.players[s]['balance'] += data['contrib']
                    self.logger.debug('added sb {} amount back to balance {} for player {}'.format(
                        data['contrib'], self.players[s]['balance'], s))

        self.logger.info('post start done')

    def cards(self):
        """Generate cards for a site"""
        self.site.generate_cards()

    def finish_it(self):
        """Finish the game. Calculate the winner and winnings
         * set board
         * finish players moves by checking balance only (check/fold)
         * till gg state,
        """
        self.logger.info('finish the game')

        board = self.site.parse_board(self.img)
        if len(board) > len(self.engine.board):
            self.engine.board = board
            self.logger.debug('final board set to {}'.format(board))

        balances = {
            s: self.site.parse_balances(self.img, s)[s]
            for s, d in self.engine.data.items()
            if 'in' in d['status']
        }
        self.logger.debug('current balances = {}'.format(balances))

        balances_diffs = {
            s: cb - self.players[s]['balance']
            for s, cb in balances.items()
        }
        self.logger.debug('balance diff: {}'.format(balances_diffs))

        while 'gg' not in self.expected:
            s = self.engine.q[0][0]
            balance = balances[s]
            balance_diff = balances_diffs[s]
            self.logger.debug('take player {} action on balance {} (diff {}) during {}'.format(
                s, balance, balance_diff, self.engine.phase))
            self.logger.debug('available actions = {}'.format(self.expected))
            if balance == 0:
                self.logger.debug('player {} went allin with balance {}'.format(s, balance))
                cmd = ['a']
            elif balance_diff < 0:
                self.logger.debug('player {} has less money, thus called/raised/bet'.format(s))
                if 'call' in self.expected:
                    cmd = ['c']
                elif 'raise' in self.expected:
                    cmd = ['r', abs(balance_diff)]
                elif 'bet' in self.expected:
                    cmd = ['b', abs(balance_diff)]
                else:
                    raise ValueError('unknown action: call/raise/bet not found')
            elif balance_diff == 0:
                self.logger.debug('player {} exchanged no money, thus checked/folded'.format(s))
                if 'check' in self.expected:
                    cmd = ['k']
                elif 'fold' in self.expected:
                    cmd = ['f']
                else:
                    raise ValueError('unknown action: check/fold not found')
            elif balance_diff > 0:
                self.logger.debug('player {} gained money, thus won, thus checked/called'.format(s))
                if 'check' in self.expected:
                    cmd = ['k']
                elif 'call' in self.expected:
                    cmd = ['c']
                else:
                    raise ValueError('unknown action: check/fold not found')
            self.engine.do(cmd)
            self.logger.debug('action = {}'.format(cmd))
            self.logger.debug('=' * 200)
            input('$ finish it')
            self.logger.debug('=' * 200)
            self.expected = self.engine.available_actions()

        cmd = ['gg']
        if sum([1 if b > 0 else 0 for s, b in balances_diffs.items()]) == 1:
            cmd.append([s for s, bd in balances_diffs.items() if bd > 0][0])
            self.logger.debug('setting specific winner: {}'.format(cmd[1]))
        self.logger.debug('final cmd = {}'.format(cmd))
        self.engine.do(cmd)

        self.waiting_for_new_game = True
        self.logger.info('Game finished, waiting on button move')
        self.logger.debug('=' * 200)
        input('finito')
        self.logger.debug('=' * 200)
