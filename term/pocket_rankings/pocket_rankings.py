from itertools import combinations, product
import logging
from operator import neg
from os.path import dirname, realpath, join
from random import random
import shelve
from sortedcontainers import SortedDict

from pe.pe import PE


logger = logging.getLogger()


class PocketRankings:

    FILE = join(dirname(realpath(__file__)), 'pocket_rankings.shlv')

    @classmethod
    def run(cls):
        logger.info('running pocket rankings...')
        pr = PocketRankings()
        pr.create_rankings()

    @classmethod
    def load(cls):
        """Loads from file and return in sorted dictionary"""
        with shelve.open(cls.FILE) as shlv:
            pockets_rankings = SortedDict(neg, shlv['pocket_rankings'])
            # for ps, pc in pockets_ranks.items():
            #     logger.info('{} = {}'.format(ps, pc))
            logger.info('{} pocket rankings loaded and sorted'.format(len(pockets_rankings)))
            return pockets_rankings

    def all_combinations(self):
        """Creates the 1326 starting combinations."""
        ranks = list(range(2, 10)) + ['t', 'j', 'q', 'k', 'a']
        suits = ['s', 'd', 'c', 'h']
        cards = ['{}{}'.format(r, s) for r, s in product(ranks, suits)]
        logger.info('{} cards created'.format(len(cards)))
        combs = list(combinations(cards, 2))
        logger.info('{} combos created'.format(len(combs)))
        return combs

    def create_rankings(self):
        """Calculate all possible starting hands."""
        combs = self.all_combinations()

        pocket_rankings = {PE.hand_strength(c) + random() / 10**8: c for c in combs}
        logger.info('{} total pocket rankings'.format(len(pocket_rankings)))

        for ps, pc in pocket_rankings.items():
            logger.info('{} = {}'.format(ps, pc))

        with shelve.open(self.FILE) as shlv:
            shlv['pocket_rankings'] = pocket_rankings
            logger.info('saved to {}'.format(self.FILE))
