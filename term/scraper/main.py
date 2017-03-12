import datetime
import logging
import os
from PIL import Image, ImageGrab

from engine.engine import Engine
from mc.mc import MonteCarlo
from scraper.sites.base import SiteException, NoDealerButtonError
from scraper.sites.pokerstars.site import PokerStars
from scraper.sites.partypoker.site import PartyPoker
from scraper.sites.zynga.site import Zynga


class Scraper:
    """Runs a scraper for a site. Will use the site to do the scraping, and with the data
    calculate what action needs to be taken and pass that into the engine and MC"""

    PATH_DEBUG = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'debug')

    def __init__(self, site_name, seats, debug=False):
        self.logger = logging.getLogger()
        self.debug = debug
        self.logger.debug('Debug {}'.format(self.debug))

        if site_name == 'ps':
            self.site = PokerStars(seats, debug)
        elif site_name == 'pp':
            self.site = PartyPoker(seats, debug)
        elif site_name == 'zg':
            self.site = Zynga(seats, debug)
        else:
            raise NotImplementedError('{} is not implemented'.format(site_info))

        self.players = {
            s: {
                'name': 'joe',
                'balance': 1000,
                'status': 1,
            }
            for s in range(1, seats + 1)
        }
        self.players[5]['name'] = 'me'
        self.sb = 10
        self.bb = 20
        self.btn = None

        # self.engine = Engine(table.site_name, table.button, table.players, table.sb, table.bb)

    def run(self):
        """Runs the scraper
        Loads a screen shot"""
        self.logger.info('running scraping on {}'.format(self.site.NAME))
        for _ in range(1000):
            img = ImageGrab.grab()
            self.logger.debug('screenshot {}'.format(img))
            if self.debug:
                img_file = os.path.join(self.PATH_DEBUG, '{}.png'.format(datetime.datetime.utcnow()))
                img.save(img_file)
                self.logger.debug('file saved locally to {}'.format(img_file))
                # self.site.parse_screen(img)

    def replay(self):
        """Replays through images saved during debug run"""
        self.logger.info('loading files')
        for entry in os.scandir(self.PATH_DEBUG):
            if not entry.is_file() or entry.name.startswith('.'):
                self.logger.debug('skipping file {}'.format(entry.name))
                continue
            self.logger.info('replaying {}'.format(entry.name))
            img = Image.open(entry.path)
            self.parse(img)
            input()

    def parse(self, img_full):
        """Parses a run from screenshot or file.
        1) First convert img to greysacale for all analysis
        2) Get game window
        3) player names and balances
        4) dealer button - detect if new game
        """
        try:
            img_full = img_full.convert('L')
            img_win = self.site.parse_top_left_corner(img_full)
            self.check_names(img_win)
            btn = self.site.parse_dealer(img_win)
            self.start_new_game(btn)
        except SiteException as e:
            self.logger.error(e)
            img_full.show()
        except NoDealerButtonError as e:
            self.logger.warn(e)
            img_full.show()

    def start_new_game(self, btn):
        """Dealer button moved. Create new game.
        Create new engine and MC"""
        if btn != self.btn:
            self.btn = btn
            self.engine = Engine(self.site.NAME, self.btn, self.players, self.sb, self.bb)
            self.mc = MonteCarlo(self.engine)
            self.logger.info('New game created')

    def check_names(self, img):
        """Get name hashes and set it to players"""
        names = self.site.parse_names(img)
        for s, name in names.items():
            self.players[s]['name'] = name
        self.logger.info('checked player names')
