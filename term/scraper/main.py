import logging

from scraper.sites.partypoker.site import PartyPoker
from scraper.sites.zynga.site import Zynga

from scraper.screens.vbox.screen import Vbox
from scraper.screens.avd.screen import Avd
from scraper.screens.local.screen import Local


class Scraper:
    """Runs a scraper for a site"""

    def __init__(self, site_info, screen_name):
        self.logger = logging.getLogger()

        if screen_name == 'vbox':
            screen = Vbox()
        elif screen_name == 'avd':
            screen = Avd()
        elif screen_name.startswith('local'):
            screen = Local(screen_name.split('-')[-1])
        else:
            raise NotImplementedError('{} is not implemented'.format(screen_name))

        site_name, seats = site_info.split('-')
        if site_name == 'pp':
            self.site = PartyPoker(screen, seats)
        elif site_name == 'zg':
            self.site = Zynga(screen, seats)
        else:
            raise NotImplementedError('{} is not implemented'.format(site_info))

    def play(self):
        self.logger.info('scraping {} via {}'.format(self.site.NAME, self.site.screen.NAME))
        for _ in range(1):
            img_file = self.site.screen.take_screen_shot()
            self.site.parse_screen(img_file)

    def record(self):
        self.logger.info('recording {} via {}'.format(self.site.NAME, self.site.screen.NAME))
        while True:
            self.site.screen.take_screen_shot(True)
