import logging
import os.path

from scraper.sites.base import BaseSite


class PartyPoker(BaseSite):

    NAME = 'Party Poker'
    PATH_IMAGES = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'img')
    FILE_COORDS = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'coords.yml')
