from collections import Counter
import functools
from itertools import product, chain
import logging
from math import ceil, floor
import requests
from sortedcontainers import SortedList
import time


logger = logging.getLogger()


class PE:
    # Sample size for the product of the hand ranges
    SAMPLE_SIZE = 0.10

    @classmethod
    def req_equities(cls, board, pockets):
        """Makes request to service for PE"""
        logger.debug('requesting equities')
        res = requests.post('http://127.0.0.1:5000/', json={
            'pockets': pockets,
            'board': board,
        })
        res.raise_for_status()
        equities = res.json()
        return equities

    @classmethod
    def hand_strength(cls, hand):
        """Used for calculating the hand strengths for ranking pockets"""
        pockets = [list(hand), ['__', '__']]
        board = ['__'] * 5
        equities = PE.req_equities(board, pockets)
        hand_strength = equities['eval'][0]['ev'] / 1000
        logger.debug('pocket {} strength: {}'.format(hand, hand_strength))
        return hand_strength

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
        # logger.info('calculating showdown equities...')
        seats = []
        hand_ranges = []
        for s, d in engine.data.items():
            # logger.debug('player {} status {}'.format(s, d['status']))
            if 'in' in d['status']:
                seats.append(s)
                pocket = engine.data[s]['hand']
                # logger.debug('player {} has pocket {}'.format(s, pocket))ª
                if pocket != ['__', '__']:
                    hand_range = [tuple(engine.data[s]['hand'])]
                    # logger.debug('player {} added {} pocket cards'.format(s, hand_range))
                else:
                    hand_range = engine.players[s]['hand_range']
                    # logger.debug('player {} added {} hand ranges'.format(s, len(hand_range)))
                hand_ranges.append(hand_range)

        seats_len = len(seats)
        equities = {s: 1 / seats_len for s in seats}
        try:
            if seats_len < 2:
                logger.error('Not enough players still in given to calculate winners')
            elif seats_len > 2 or all(len(hr) > 1 for hr in hand_ranges):
                equities = PE.showdown_equities_n(engine, seats, hand_ranges, seats_len)
            else:
                equities = PE.showdown_equities_2(engine, seats, hand_ranges, seats_len)
        except RuntimeError as e:
            logger.exception(e)
            engine.board = []

        return equities

    @classmethod
    def showdown_equities_n(cls, engine, seats, hand_ranges, seats_len):
        logger.info('too many players still in, defaulting to random pockets for foes')
        board = engine.board + ['__'] * (5 - len(engine.board))
        pockets = [engine.data[s]['hand'] for s in seats]
        # logger.info('seats = {} and pockets = {} and board = {}'.format(seats, pockets, board))

        eval_res = PE.req_equities(board, pockets)

        equities = {}
        for s, e in zip(seats, eval_res['eval']):
            # logger.debug('s={} e={}'.format(s, e))
            equities[s] = e['ev'] / 1000

        logger.info('final equities: {}'.format(equities))
        return equities

    @classmethod
    def showdown_equities_2(cls, engine, seats, hand_ranges, seats_len):
        time_start = time.time()
        board = engine.board + ['__'] * (5 - len(engine.board))
        board_len = len(Counter(board))

        calcs = 0
        logger.debug('calculating equities for {} players with {}'.format(seats_len, board))
        equities_evals = {s: [] for s in seats}
        for hrp in product(*hand_ranges):
            # logger.debug('HRP = {} {}'.format(len(hrp), hrp))
            cnts = Counter([c for h in list(hrp) + board for c in h])
            if len(cnts) < seats_len * 2 + board_len:
                # logger.debug('duplicated cards found {} < {} * 2 + {} [{}]'.format(
                #     len(cnts), seats_len, board_len, cnts.most_common()))
                continue
            calcs += 1
            hrps = list(chain.from_iterable(map(list, hrp)))
            # logger.debug('hrps {} and board {}'.format(hrps, board))
            eval = cls.pokereval_2(*board, *hrps)
            for s, e, p in zip(seats, eval['eval'], hrp):
                # logger.debug('s={} e={} p={}'.format(s, e, p))
                equities_evals[s].append(e['ev'] / 1000)

        # have now a list of equities for every player
        # every player has same length of evals
        # sort the equities in order to map it to hand strengths
        # logger.debug('sorting equities evals...')
        equities_ranked = {s: {} for s in seats}
        for s, equity_eval in equities_evals.items():
            equity_ranked = SortedList(equity_eval)
            equities_ranked[s] = equity_ranked
            # logger.debug('sorted list = {}'.format(equity_ranked))

        # the equities are now averaged per pocket
        # get hand probs to map against

        hss = {s: (0, 1) if len(hr) == 1 else (1 - engine.data[s]['strength'], 1)
                      for s, hr in zip(seats, hand_ranges)}
        # logger.debug('hand strength boundaries {}'.format(hss))

        # now have list of sorted avg equities and hand strength boundaries
        # average card equities within range
        # todo: maybe recalc?

        # logger.debug('cutting hand ranges')
        equities_filtered = {s: [] for s in seats}
        for s in seats:
            per = equities_ranked[s]
            hs = hss[s]
            start = floor(len(per) * hs[0])
            end = ceil(len(per) * hs[1]) + 1
            # logger.debug('seat {} range start at {} and end at {}'.format(s, start, end))
            rng_fil = per[start:end]
            # logger.debug('seat {} has {} filtered equities'.format(s, len(rng_fil)))
            equities_filtered[s] = 0 if not rng_fil else sum(rng_fil) / len(rng_fil)

        # final normalization to return p~1
        total_equities = sum(e for e in equities_filtered.values())
        equities = {s: e / total_equities for s, e in equities_filtered.items()}
        # logger.debug('equities normalized {} from total {}'.format(equities, total_equities))

        duration = time.time() - time_start
        # logger.info('calculated {}/s  [{} calcs in {}s]'.format(calcs // duration, calcs, duration))
        # logger.info('cache info: {}'.format(cls.pokereval_2.cache_info()))

        # logger.info('final equities: {}'.format(equities))
        return equities

    @classmethod
    @functools.lru_cache(maxsize=1<<18)
    def pokereval_2(cls, b1, b2, b3, b4, b5, c1, c2, c3, c4):
        board = [b1, b2, b3, b5, b5]
        hrp = [[c1, c2], [c3, c4]]
        # logger.debug('reconstructed b= {} & c= {}'.format(board, hrp))
        equities = PE.req_equities(board, hrp)
        # logger.debug('{} => {}'.format(hrp, [e['ev'] for e in eval['eval']]))
        return equities
