import logging
import os.path

from scraper.sites.base import BaseSite


class PartyPoker(BaseSite):

    NAME = 'Party Poker'
    PATH_IMAGES = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'img')
    FILE_COORDS = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'coords.yml')

    def parse_screen(self, img):
        """Parses screen. Load coords"""
        img = self.parse_top_left_corner(img)
        # img = self.parse_fullscreen(img)

        # dealers = self.parse_dealer(img, coords)
        # participants = self.parse_playing(img, coords)
        # balances = self.parse_balances(img, coords, participants)
        # board = self.parse_board(img, coords)
        # hero_cards = self.parse_cards_hero(img, coords)
        # foes_cards = self.parse_cards_foes(img, coords)

    def parse_top_left_corner(self, img):
        threshold = self.coords['top_left_corner']['threshold']
        self.logger.info('parsing top left corner with threshold {}'.format(threshold))
        result = self.match_template(img, self.img['top_left_corner'], threshold)
