import datetime
from itertools import combinations
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
    ACtIONS_MAP = {
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
        self.waiting_for_new_game = True

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

    def run(self):
        """Run application"""
        while True:
            self.take_screen()

            if self.observe:
                continue

            btn = self.check_dealer()

            if btn != self.btn:
                self.start_new_game(btn)

            if self.waiting_for_new_game:
                self.logger.info('waiting for new game...')
                time.sleep(1)
                continue

            self.wait_player_action()

            self.logger.info('loop finished')
            # self.img.show()
            input()

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

        # check actions till phase has caught up
        phase = self.engine.phase
        board = self.site.parse_board(self.img)

        # try getting think bar twice
        s = self.engine.q[0][0]
        failed_prev = False
        while True:
            try:
                current_s = self.site.parse_thinking(self.img)
                if current_s != s:
                    self.logger.debug('Player finished thinking, it is now {}'.format(current_s))
                    return self.check_player_action()
            except ThinkBarError as e:
                self.logger.exception(e)
                if failed_prev:
                    raise
                else:
                    failed_prev = True
                input()
            else:
                failed_prev = False

                # if player is still thinking, then so can we
                timeout += 0.1
                self.mc.timeout = timeout
                # self.mc.run()

            # get new state for second try
            self.take_screen()

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
            contribs_scr = self.site.parse_contribs(self.img, s).get(s, 0)
            contrib_diff = contribs_scr - self.engine.data[s]['contrib']
            self.logger.debug('balance diff {} and contrib diff {}'.format(balance_diff, contrib_diff))

            # check
            if not balance_diff and not contrib_diff:
                self.logger.debug('No change in balance')
                if 'check' not in self.expected:
                    raise ValueError('No balance change on player but he cannot check')
                cmd = ['k']

            # chips moved
            else:
                # get diff (or max in disagreement)
                if balance_diff == contrib_diff:
                    amt = balance_diff
                else:
                    self.logger.warn('player balance/contrib changed, but did not fold')
                    amt = max(balance_diff, contrib_diff)
                cmd = ['b', amt]

        # do action, rotate, and get next actions
        self.logger.debug('parsed action {}'.format(cmd))
        action = self.engine.do(cmd)
        action_name = self.ACtIONS_MAP[action[0]]
        self.logger.debug('engine actioned {} {}'.format(action_name, action))

        # import pdb
        # pdb.set_trace()
        # cut tree based on action
        child_nodes = self.mc.tree.children(self.mc.tree.root)
        self.logger.debug('{} child nodes on tree'.format(len(child_nodes)))
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
                self.logger.debug('Tree created from single node {}'.format(node.tag))
                self.logger.debug('tree created from single node {}'.format(node.data))
            # proximity
            else:
                nodes_diffs = {abs(n.data['amount'] - action[1]): n for n in action_nodes}
                node = nodes_diffs[min(nodes_diffs.keys())]
                self.mc.tree = self.mc.tree.subtree(node.identifier)
                self.logger.debug('tree created from closest node {}'.format(node.tag))
                self.logger.debug('tree created from closest node {}'.format(node.data))

        self.logger.debug('get next actions')
        self.expected = self.engine.available_actions()

    def start_new_game(self, btn):
        """Dealer button moved. Create new game.
        Get players that are still IN (not necessary to check pockets. The balances will return 0
            or empty if player left/out)
        Get small blind and big blind.
        Create new engine
        Create new MC
        Not waiting for a new game anymore.
        """
        if not self.btn:
            self.logger.info('init btn at {}'.format(btn))
            self.btn = btn
            return

        self.logger.info('btn moved: creating new game')
        self.btn = btn

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
                self.engine.pot = balance
            else:
                self.players[s]['balance'] = balance
        self.logger.info('post start done')
