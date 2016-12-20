from collections import Counter
import functools
from itertools import product, chain
import logging
from math import ceil, floor
from pokereval import PokerEval
from sortedcontainers import SortedList
import time


logger = logging.getLogger()


class PE(PokerEval):
    GAME = 'holdem'
    ITERATIONS = 100000
    ITERATIONS_FAST = 10000
    # Sample size for the product of the hand ranges
    SAMPLE_SIZE = 0.10

    @classmethod
    def hand_strength(cls, hand):
        """Used for calculating the hand strengths for ranking pockets"""
        pockets = [list(hand), ['__', '__']]
        board = [255] * 5
        equities = cls.poker_eval(cls,
            pockets=pockets,
            board=board,
            iterations=cls.ITERATIONS,
            game=cls.GAME
        )
        return equities['eval'][0]['ev'] / 1000

    @classmethod
    def showdown_equities(cls, engine):
        """Calculate winning equities for the players given on engine.

        1) get players hand ranges
        2) for every product of the hand ranges:
            a) exclude dead card or duplicate cards
            b) calculate ev's
            c) append ev to player hand range pocket pair
        3) sum&avg every pocket and sort every player's range
        4) weigh every players' equities
        5) normalize all player's final equity (to 1)

        Returns:
            dict: seat: equity
        """
        logger.info('calculating showdown equities...')

        seats = []
        hand_ranges = []
        for s, d in engine.data.items():
            # logger.debug('player {} status {}'.format(s, d['status']))
            if 'in' in d['status']:
                seats.append(s)
                pocket = engine.data[s]['hand']
                # logger.debug('player {} has pocket {}'.format(s, pocket))
                if pocket != ['__', '__']:
                    hand_range = [tuple(engine.data[s]['hand'])]
                    logger.debug('player {} added {} pocket cards'.format(s, hand_range))
                else:
                    hand_range = engine.players[s]['hand_range']
                    logger.debug('player {} added {} hand ranges'.format(s, len(hand_range)))
                hand_ranges.append(hand_range)

        seats_len = len(seats)
        if seats_len < 2:
            raise ValueError('Not enough players still in given to calculate winners')
        elif seats_len > 2:
            equities = PE.showdown_equities_n(engine, seats, hand_ranges, seats_len)
        else:
            equities = PE.showdown_equities_2(engine, seats, hand_ranges, seats_len)

        # input('check cache and hits')
        return equities

    @classmethod
    def showdown_equities_n(cls, engine, seats, hand_ranges, seats_len):
        logger.warn('too many players still in, defaulting to random pockets for foes')
        board = engine.board
        pockets = [engine.data[s]['hand'] for s in seats]
        logger.info('pockets = {} and board = {}'.format(pockets, board))

        eval = cls.poker_eval(cls, board=board, pockets=pockets,
                              iterations=cls.ITERATIONS_FAST, game=cls.GAME)

        equities = {}
        for s, e in zip(seats, eval['eval']):
            logger.debug('s={} e={}'.format(s, e))
            equities[s] = e['ev'] / 1000

        logger.info('final equities: {}'.format(equities))
        return equities

    @classmethod
    def showdown_equities_2(cls, engine, seats, hand_ranges, seats_len):
        time_start = time.time()
        board_len = len(Counter(engine.board))

        calcs = 0
        logger.debug('calculating equities for {} players with {}'.format(seats_len, engine.board))
        equities_evals = {s: [] for s in seats}
        for hrp in product(*hand_ranges):
            # logger.debug('HRP = {} {}'.format(len(hrp), hrp))
            cnts = Counter([c for h in list(hrp) + engine.board for c in h])
            if len(cnts) < seats_len * 2 + board_len:
                # logger.debug('duplicated cards found {} < {} * 2 + {} [{}]'.format(
                #     len(cnts), seats_len, board_len, cnts.most_common()))
                continue
            calcs += 1
            hrps = list(chain.from_iterable(map(list, hrp)))
            # logger.debug('board and hrps {} {}'.format(engine.board, hrps))
            eval = cls.pokereval_2(*engine.board, *hrps)
            for s, e, p in zip(seats, eval['eval'], hrp):
                # logger.debug('s={} e={} p={}'.format(s, e, p))
                equities_evals[s].append(e['ev'] / 1000)

        # have now a list of equities for every player
        # every player has same length of evals
        # sort the equities in order to map it to hand strengths
        logger.debug('sorting equities evals...')
        equities_ranked = {s: {} for s in seats}
        for s, equity_eval in equities_evals.items():
            equity_ranked = SortedList(equity_eval)
            equities_ranked[s] = equity_ranked
            # logger.debug('sorted list = {}'.format(equity_ranked))

        # the equities are now averaged per pocket
        # get hand probs to map against

        hss = {s: (0, 1) if len(hr) == 1 else (1 - engine.data[s]['strength'], 1)
                      for s, hr in zip(seats, hand_ranges)}
        logger.debug('hand strength boundaries {}'.format(hss))

        # now have list of sorted avg equities and hand strength boundaries
        # average card equities within range
        # todo: maybe recalc?

        logger.debug('cutting hand ranges')
        equities_filtered = {s: [] for s in seats}
        for s in seats:
            per = equities_ranked[s]
            hs = hss[s]
            start = floor(len(per) * hs[0])
            end = ceil(len(per) * hs[1]) + 1
            logger.debug('seat {} range start at {} and end at {}'.format(s, start, end))
            rng_fil = per[start:end]
            logger.debug('seat {} has {} filtered equities'.format(s, len(rng_fil)))
            equities_filtered[s] = sum(rng_fil) / len(rng_fil)

        # final normalization to return p~1
        total_equities = sum(e for e in equities_filtered.values())
        equities = {s: e / total_equities for s, e in equities_filtered.items()}
        logger.debug('equities normalized {} from total {}'.format(equities, total_equities))

        duration = time.time() - time_start
        logger.info('calculated {}/s  [{} calcs in {}s]'.format(calcs // duration, calcs, duration))
        # logger.info('cache info: {}'.format(cls.pokereval_2.cache_info()))

        logger.info('final equities: {}'.format(equities))
        return equities

    @classmethod
    @functools.lru_cache(maxsize=1<<18)
    def pokereval_2(cls, b1, b2, b3, b4, b5, c1, c2, c3, c4):
        board = [b1, b2, b3, b5, b5]
        hrp = [[c1, c2], [c3, c4]]
        # logger.debug('reconstructed b= {} & c= {}'.format(board, hrp))
        eval = cls.poker_eval(cls, board=board, pockets=hrp,
                              iterations=cls.ITERATIONS_FAST, game=cls.GAME)
        # logger.debug('{} => {}'.format(hrp, [e['ev'] for e in eval['eval']]))
        return eval
