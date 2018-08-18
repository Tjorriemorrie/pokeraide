from collections import deque, Counter, namedtuple
from copy import deepcopy, copy
from datetime import datetime
from functools import lru_cache
from itertools import product, chain
import logging
from math import sqrt, log, floor, ceil
from operator import neg, pos, itemgetter
import pickle
import random
import retrace
import shelve
from string import ascii_uppercase, digits
import sys
import time
import uuid

import numpy as np

from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import Index, DocType, String, Date, Integer, Float, Boolean, Q, A
from pokereval import PokerEval
from sortedcontainers import SortedDict, SortedList
from treelib import Node, Tree


# logging.basicConfig(level=logging.DEBUG, format='%(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')
logger = logging.getLogger('poker')
for _ in ("boto", "elasticsearch", "urllib3"):
    logging.getLogger(_).setLevel(logging.CRITICAL)

connections.create_connection(hosts=['es_host'])

INDEX_NAME = 'governor'

es_index = Index(INDEX_NAME)
# for index in connections.get_connection().indices.get('*'):
#   print(index)
# es_index.delete(ignore=404)
es_index.create(ignore=400)
# logger.info('index truncated')
cluster_health = connections.get_connection().cluster.health()
for k, v in cluster_health.items():
    logger.info('Cluster health: {}: {}'.format(k, v))
active_primary_shards = cluster_health['active_primary_shards']

# ACTIONS_HERO = ['10.0', '30.0', '50.0', '70.0', '90.0']
ACTIONS_HERO = ['20.0', '50.0', '80.0']
# ACTIONS_FOES = ['20.0', '50.0', '80.0']
ACTIONS_FOES = ['50.0']


with shelve.open('/code/pocket_ranks.shlv') as shlv:
    pockets_ranks = SortedDict(neg, shlv['pocket_ranks'])
    # for ps, pc in pockets_ranks.items():
    #     logger.info('{} = {}'.format(ps, pc))


with shelve.open('/code/pocket_abstracts.shlv') as shlv:
    pockets_abstracts = shlv['pocket_abstracts']
    # for pp, pa in pockets_abstracts.items():
    #     logger.info('{} = {}'.format(pp, pa))


@es_index.doc_type
class GameAction(DocType):
    site = String(index='not_analyzed')
    game = String(index='not_analyzed')
    vs = Integer()
    player = String(index='not_analyzed')
    amount = Integer()
    pot = Integer()
    bet_to_pot = Float()
    pos = Integer()
    preflop_1 = String(index='not_analyzed')
    preflop_1_btp = Float()
    preflop_2 = String(index='not_analyzed')
    preflop_2_btp = Float()
    preflop_aggro = Boolean()
    flop_1 = String(index='not_analyzed')
    flop_1_btp = Float()
    flop_2 = String(index='not_analyzed')
    flop_2_btp = Float()
    flop_aggro = Boolean()
    turn_1 = String(index='not_analyzed')
    turn_1_btp = Float()
    turn_2 = String(index='not_analyzed')
    turn_2_btp = Float()
    turn_aggro = Boolean()
    river_1 = String(index='not_analyzed')
    river_1_btp = Float()
    river_2 = String(index='not_analyzed')
    river_2_btp = Float()
    river_aggro = Boolean()
    created_at = Date()

GameAction.init()


class ES:
    SAMPLE_SIZE = 1 << 7

    @classmethod
    def cut_hand_range(cls, stats):
        fold_perc = stats.get('f', 0.50)
        fold_cutoff = int(len(pockets_ranks) * (1 - fold_perc))
        logger.debug('fold {}% cutting at {}'.format(fold_perc * 100, fold_cutoff))

        hand_range_keys = pockets_ranks.islice(stop=fold_cutoff)
        # logger.debug('hand range keys {}'.format(hand_range_keys))
        hand_range = [pockets_ranks[k] for k in hand_range_keys]
        # logger.debug('player hand range is {} {}'.format(len(hand_range), hand_range))
        return hand_range

    @classmethod
    def player_stats(cls, engine, seat):
        """Get the stats for this history of actions, favouring the current player.

        Given number of players
        For every player,
        for every phase,
        get action distribution.

        Where it falls short of 1k hands
        get the rest from all players"""
        p = engine.players[seat]
        d = engine.data[seat]
        # logger.info('Get player stats for {} {}'.format(seat, p['name']))

        # build up the basic query
        query = {
            "bool": {
                "should": [
                    {"match": {"player": {"query": p['name'], "boost": 3}}},
                    {"match": {"vs": {"query": engine.vs, "boost": 2}}},
                    {"match": {"site": {"query": INDEX_NAME, "boost": 1}}},
                ]
            }
        }

        # add previous info
        phase_matching = []
        for phase in ['preflop', 'flop', 'turn', 'river']:
            for i, action_info in enumerate(d[phase]):
                phase_matching.append({'match': {'{}_{}'.format(phase, i+1): {'query': action_info['action'], 'boost': 5}}})
                if i == 0:
                    phase_matching.append({'match': {'{}_aggro'.format(phase): {'query': action_info['aggro'], 'boost': 8}}})
        # logger.debug('Added {} action filters'.format(len(phase_matching)))
        query['bool']['should'].extend(phase_matching)

        # agg field
        agg_phase = engine.phase
        if not d[agg_phase]:
            # logger.debug('player do not have data for this phase')
            agg_turn = 1
        elif len(d[agg_phase]) < 2:
            # logger.debug('player do not have data for second act')
            agg_turn = 2
        else:
            # logger.debug('player has acted twice, moving on to next phase')
            agg_turn = 1
            if agg_phase == engine.PHASE_PREFLOP:
                agg_phase = engine.PHASE_FLOP
            elif agg_phase == engine.PHASE_FLOP:
                agg_phase = engine.PHASE_TURN
            else:
                agg_phase = engine.PHASE_RIVER
        agg_field = '{}_{}'.format(agg_phase, agg_turn)
        # logger.info('aggregate field = {}'.format(agg_field))

        # exclude blinds and
        if agg_field == 'preflop_1':
            query['bool']['must_not'] = [
                {'term': {agg_field: 's'}},
                {'term': {agg_field: 'l'}}
            ]
            # logger.debug('excluding blinds for preflop first action')

        # facing aggression? (currently, not historically like in engine.do)
        max_contrib = max(pd['contrib'] for ps, pd in engine.data.items())
        contrib_short = max_contrib - d['contrib']
        if contrib_short:
            could_limp = True if engine.phase == engine.PHASE_PREFLOP and max_contrib == engine.bb_amt else False
            if not could_limp:
                query['bool']['should'].append({'match': {'{}_aggro'.format(agg_phase): {'query': True, 'boost': 8}}})
                # logger.debug('facing aggro: yes, contrib is short and not limping')
            else:
                # logger.info('facing aggro: no, could limp: {}'.format(could_limp))
                pass
        else:
            # logger.info('facing aggro: no, contrib short = {}'.format(contrib_short))
            pass

        sea = GameAction.search()
        sea = sea.query(query)
        sea = sea.sort('_score', {'created_at': 'desc'})

        # establish which doc field is to be aggregated on for this player
        docs_per_shard = cls.SAMPLE_SIZE / active_primary_shards
        # logger.info('docs per shard = {}'.format(docs_per_shard))

        sample = A('sampler', shard_size=docs_per_shard)
        terms = A('terms', field=agg_field)
        pottie = A('percentiles', field='{}_btp'.format(agg_field), percents=[50])
        sea.aggs.bucket('mesam', sample).metric('pottie', pottie).bucket('aksies', terms)

        res = sea.execute()

        # logger.info('response:')
        # logger.info('hits: {}'.format(res.hits.total))
        # for _, h in enumerate(sea):
        #     logger.info('{}-> {} {} {}'.format(_, h._score, h['player'], h['vs']))
        # for agg in res.aggregations.mesam.aksies.buckets:
        #     logger.info('aggs: {}: {}'.format(agg['key'], agg['doc_count']))

        # required to scale now mostly for using fold equity
        total_docs = sum(pa['doc_count'] for pa in res.aggregations.mesam.aksies.buckets)
        phase_actions = {a['key']: a['doc_count'] / total_docs for a in res.aggregations.mesam.aksies.buckets}
        # logger.info('scaled aggs: {}'.format(phase_actions))

        phase_btps = res.aggregations.mesam.pottie.values.to_dict()
        # clean out NaN
        phase_btps = {k: v if isinstance(v, float) else 0.50 for k, v in phase_btps.items()}

        # input('>> ')
        return {
            'actions': phase_actions,
            'btps': phase_btps,
        }

    @classmethod
    def dist_player_stats(cls, stats, strength=False):
        """Order the stats to create distribution
        previously 'hand strength'"""
        # logger.info('distributing the player stats')
        dist = SortedDict(pos, {0: 'f'})
        p = 0
        for o in ['f', 's', 'l', 'k', 'c', 'b', 'r', 'a']:
            if o in stats:
                dist[p] = o
                p += max(0.01, stats[o])
                dist[p - 0.001] = o
        logger.info('dist = {}'.format(dist))
        if len(dist) == 1:
            dist[1] = 'a'

        if not strength:
            return dist

        r = ''
        # logger.debug('dist = {}'.format(type(dist)))
        for _ in range(20):
            p = _ * 5 / 100
            i_pos = dist.bisect_key_left(p)
            # logger.debug('i_pos {} / {}'.format(i_pos, len(dist)))
            k = dist.iloc[i_pos]
            v = dist[k]
            r += v.upper() if (1 - strength) <= p <= 1 else v.lower()
            # logger.debug('bisected {} from {} at {}%'.format(v, k, r))
        logger.debug('dist_stats {}'.format(r))
        return r


class Engine:
    '''
    The engine requires various properties for the state
    - button location
    - players
    - data
        = status
        = cards
        = equity
    - board
    - pot
    - current phase
    - current player to act
    - all the turn data
        = preflop
        = flop
        = turn
        = river
        = showdown

    Must retain history per phase to establish who is next to play
    '''
    PHASE_PREFLOP = 'preflop'
    PHASE_FLOP = 'flop'
    PHASE_TURN = 'turn'
    PHASE_RIVER = 'river'
    PHASE_SHOWDOWN = 'showdown'
    PHASE_GG = 'gg'

    def __init__(self, button, players, sb, bb, **kwargs):
        logger.info('Engine button: {}'.format(button))
        logger.info('Engine players: {}'.format(len(players)))
        logger.info('Engine kwargs: {}'.format(kwargs))

        self.button = button
        self.players = players
        self.sb_amt = sb
        self.bb_amt = bb
        self.go_to_showdown = False
        self.mc = False

        if hasattr(kwargs, 'data'):
            self.data = kwargs['data']
        else:
            self.data = {s: {
                'status': 'in' if p.get('status') else 'out',
                'hand': [],
                'contrib': 0,
                'matched': 0,
                'preflop': [],
                'flop': [],
                'turn': [],
                'river': [],
                'showdown': [],  # for error at stats
            } for s, p in players.items()}
        self.vs = sum([1 if d['status'] == 'in' else 0 for d in self.data.values()])
        self.winner = None

        self.board = kwargs.get('board', [])
        self.pot = kwargs.get('pot', 0)
        self.phase = kwargs.get('phase', self.PHASE_PREFLOP)

        self.preflop = kwargs.get('preflop', {})
        self.flop = kwargs.get('flop', {})
        self.turn = kwargs.get('turn', {})
        self.river = kwargs.get('river', {})
        self.showdown = kwargs.get('showdown', {})

        self.q = None
        self.pe_equities = {}

        for s, d in self.data.items():
            if 'in' not in d['status']:
                continue
            self.data[s]['stats'] = ES.player_stats(self, s)
            self.players[s]['hand_range'] = ES.cut_hand_range(self.data[s]['stats'])
            self.data[s]['strength'] = 1

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, deepcopy(v, memo))
        return result

    def __repr__(self):
        r = '{}:\n'.format(self.phase)

        r += 'Pot: {}\n'.format(self.pot)

        if self.board:
            r += 'Board: {}\n'.format(' '.join(self.board))

        # self.pe.equities(self.data, self.board)

        pta = self.q[0][0] if self.q else 0

        for s, p in self.players.items():
            d = self.data[s]
            if 'in' not in d['status']:
                continue

            # add player info
            pr = '{:>10.10} '.format(p.get('name', ''))
            pr += '{: 6d} '.format(p.get('balance', 0) - d.get('contrib', 0))

            status = '<--' if s == pta and self.phase != self.PHASE_SHOWDOWN else '   '
            pr += '{:>6} '.format(d.get('matched', 0) + d.get('contrib', 0) or '')
            pr += '{} '.format(' '.join(d['hand']))
            pr += '{:>3} '.format(s)
            pr += '{} '.format('[]' if self.button == s else '  ')
            pr += '{} '.format(status)
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['preflop']))
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['flop']))
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['turn']))
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['river']))
            pr += '{:>6} '.format(d['contrib'] or '')
                # pr += '{:10} '.format('*' * d['equity'])
            r += '{}\n'.format(pr)

            # add player stats
            try:
                if self.phase != self.PHASE_SHOWDOWN:
                    d['stats'] = ES.player_stats(self, s)
                    dist_stats = ES.dist_player_stats(d['stats']['actions'], d['strength'])
                    r += '{:>63}\n\n'.format(dist_stats)
            except Exception as e:
                logger.exception(e)

        return r

    def player_queue(self):
        """
        Returns deque of players starting with player after button/dealer
        normally the SB.

        Start at dealer and then rotate to next player that is still playing.
        """
        players_from_button = [(s, p) for s, p in self.players.items() if s >= self.button]
        # logger.debug('players_from_button {}'.format(players_from_button))
        players_rest = [(s, p) for s, p in self.players.items() if s < self.button]
        # logger.debug('players_rest {}'.format(players_rest))
        self.q = deque(players_from_button + players_rest)
        # logger.info('new deque created for this phase {}'.format(self.q))
        self.rotate()

        logger.debug('calculating player positions')
        pos = 1
        for s, q in self.q:
            self.data[s]['pos'] = pos
            # logger.info('player position {} for seat {}'.format(pos, s))
            pos += 1

    def rotate(self):
        ''' Rotates the queue till next action is required.

        Only 'in' status is allowed to action/rotate to next.

        Allin is not available for action, but if all remaining players
        are all 'allin', then to prevent infinite loop check for at least
        1 'in' status before beginning the rotation loop.
        '''
        statuses = Counter([d['status'] for d in self.data.values()])
        if not statuses['in']:
            # logger.warn('No "in" statuses left to rotate to')
            return

        while True:
            # logger.debug('deque [{}]: {}'.format(len(list(self.q)), self.queue_display()))
            # logger.debug('rotate: player was seat {}'.format(self.q[0][0]))
            self.q.rotate(-1)
            # logger.debug('rotate: player now seat {}'.format(self.q[0][0]))
            d = self.data[self.q[0][0]]
            if d['status'] == 'in':
                logger.info('next player is {} {}'.format(self.q[0][0], self.q[0][1]['name']))
                break

    def queue_display(self):
        return ['#{}_s{}:{}'.format(_, qi[0], qi[1]['name']) for _, qi in enumerate(self.q)]

    def available_actions(self):
        '''
        Game status for finished is check so that we skip straight to showdown

        If init not done for every phase, then do the init first, e.g. dealing cards.

        If phase balances then set next phase. Next conditional will
        trigger. Do not use elifs

        Preflop will automatically set SB and BB. Cards defaulted to empty pockets
        and hands are set via Game or MC. Players should be updated via reference.

        Phase data holds:
        - Create phase_data list when starting
        - finishes of phase

        At start we check if game phase should skip ahead to showdown, e.g.
          all players are allin
        '''
        # logger.info('getting available actions from engine')
        self.check_game_finished()

        phase_data = getattr(self, self.phase)
        actions = ['hand']

        if self.phase == self.PHASE_PREFLOP:
            # logger.debug('adding preflop actions')
            if not phase_data.get('started'):
                # logger.debug('starting preflop')
                for s, p in self.players.items():
                    # logger.debug(p)
                    self.data[s]['hand'] = ['__', '__'] if bool(p.get('status')) else ['  ', '  ']
                self.player_queue()
                # for headsup the button posts SB
                if self.vs == 2:
                    self.rotate()
                self.do(['sb', self.sb_amt])
                self.do(['bb', self.bb_amt])
                phase_data['started'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_FLOP
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_FLOP:
            # logger.debug('adding flop actions')
            if not phase_data.get('started'):
                self.player_queue()
                phase_data['started'] = True
                self.board += ['__'] * 3 if self.mc else input('\n\nBoard? ').split(' ')
            if self.go_to_showdown:
                phase_data['finished'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_TURN
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_TURN:
            # logger.debug('adding turn actions')
            if not phase_data.get('started'):
                self.player_queue()
                phase_data['started'] = True
                self.board.append('__' if self.mc else input('\n\nTurn? '))
            if self.go_to_showdown:
                phase_data['finished'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_RIVER
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_RIVER:
            # logger.debug('adding river actions')
            if not phase_data.get('started'):
                self.player_queue()
                phase_data['started'] = True
                self.board.append('__' if self.mc else input('\n\nRiver? '))
            if self.go_to_showdown:
                phase_data['finished'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_SHOWDOWN
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_SHOWDOWN:
            logger.debug('phase in showdown')
            if not phase_data.get('started'):
                logger.debug('showdown has not started')
                phase_data['started'] = True
            if not phase_data.get('finished'):
                logger.debug('showdown has not finished')
                statuses = Counter([d['status'] for d in self.data.values()])
                logger.debug('SD statuses = {}'.format(list(statuses)))
                if statuses['in'] + statuses['allin'] <= 1:
                    logger.info('SD is finished')
                    for s, d in self.data.items():
                        if 'in' in d['status']:
                            self.do(['gg', s])
                            break
                    phase_data['finished'] = True
                    logger.debug('showdown finished with 1 player')
                else:
                    actions.append('gg')
                    logger.debug('showdown not finished with n players')
            if phase_data.get('finished'):
                logger.debug('showdown finished')
                self.phase = self.PHASE_GG

        else:
            # can only fold when not at showdown
            actions.append('fold')

        # if end of game, then no more actions
        if self.phase == self.PHASE_GG:
            # logger.info('no actions for GG')
            actions = []
        # and if the phase is not showdown, then players
        # can act
        elif self.phase != self.PHASE_SHOWDOWN:
            # the status of the player so
            # that we can see what his
            # available actions are
            s, p = self.q[0]
            d = self.data[s]

            # if allin then you can do no more
            if d['status'] != 'allin':
                # special case to handle blinds during preflop
                contribs = [pd['contrib'] for pd in self.data.values()]
                # preflop special only matters if nobody has raised
                if self.phase == self.PHASE_PREFLOP and max(contribs) == self.bb_amt:
                    # BB only have to check (not call)
                    if 'is_BB' in d:
                        actions.append('check')
                    else:
                        actions.append('call')
                    # always add bet (since no one has acted)
                    # technically a 'raise' but special handling for betting at add_actions
                    actions.append('raise')
                # otherwise someone has set their intention
                elif any(contribs):
                    actions.extend(['call', 'raise'])
                # otherwise nothing has happened and initial aggression available
                else:
                    actions.extend(['check', 'bet'])
                #
                # actions_player = []
                # for action_player in self.data.values():
                #     actions_player.extend(action_player[self.phase])
                # # if b has been made, then only call/raise
                # if set(actions_player) & set(['b']):
                # else:
                #
                # action[0] = 'r' if set(['s', 'l', 'b']) & set(actions_player) else 'b'
                # contribs = Counter([d['contrib'] for d in self.data.values()])
                # # if there is already a contrib to the phase then
                # # you can only call or raise
                # # also, that is only applicable as well during
                # #   preflop has blinds has been placed
                # if self.phase == self.PHASE_PREFLOP or (len(list(contribs)) > 1 and d[self.phase] != ['l']):
                # # else if there has been no action then
                # # you can just check or start betting

        logger.info('available actions = {}'.format(actions))
        return actions

    def do(self, action):
        '''
        Take the action. First are general settings, like setting the hand, otherwise
        it is specific to the current player that is to act.

        If an action indicates the end of a phase, then set that phase finished attr. Also
        put all the contribs to the pot (since bets needs to be matched).
        Todo: move this to per pot contrib & matched

        GG gets winner and gives that player the pot

        A raise cannot be lower and/or equal to current highest contrib. The
         bb should also be a raise if only previous calls

        Update the hand strength with the strength of the action taken by adding
        a row to the player's data's hand_strengths

        Update
            - phase data
                - most phase data will have started and finished attr
            - player status (changed by folding/allin)
            - pot amount
            - player balance

        '''
        logger.warn('Player {} phase {} DO {}'.format(self.q[0][0], self.phase, action))

        if not action[0]:
            logger.warn('no action received')
            return

        if self.mc and action[0] not in ['a', 'b', 'f', 'c', 'r', 'gg']:
            raise Exception('bad action {} given to engine during MC'.format(action))

        if action[0] == 'h':
            hand = [action[2], action[3]] if len(action) > 2 else ['__', '__']
            self.data[int(action[1])]['hand'] = hand
            logger.info('setting hand for player {} to {}'.format(action[1], hand))
            # nothing should change when setting hand
            return

        phase_data = getattr(self, self.phase)

        if action[0] == 'gg':
            logger.info('GG for player {}'.format(action[1]))
            if int(action[1]) < 0:
                logger.info('players draw!')
                # todo distribute monies correctly per pot
                statuses = Counter([d['status'] for d in self.data.values()])
                players_still_in = statuses['allin'] + statuses['in']
                cut = int(self.pot / players_still_in)
                self.winner = []
                for s, p in self.players.items():
                    if 'in' in self.data[s]['status']:
                        p['balance'] += cut
                        self.winner.append(s)
                        logger.info('GG winnings {} draw for = {}'.format(s, cut))
            else:
                p = self.players[int(action[1])]
                p['balance'] += self.pot
                self.winner = [int(action[1])]
                logger.info('GG winnings = {}'.format(self.pot))
            phase_data['finished'] = True
            return

        s, p = self.q[0]
        d = self.data[s]

        if action[0] == 'sb':
            d['is_SB'] = True
            d['contrib'] += action[1]
            d[self.phase].append({
                'action': 's',
                'aggro': False,
            })
            logger.debug('Did action SB')
            self.rotate()

        if action[0] == 'bb':
            d['is_BB'] = True
            d['contrib'] += action[1]
            d[self.phase].append({
                'action': 'l',
                'aggro': False,
            })
            logger.debug('Did action BB')
            self.rotate()

        contribs_all = [pd['contrib'] for pd in self.data.values()]
        total_contribs = sum(contribs_all)
        max_contrib = max(contribs_all)
        contrib_short = max_contrib - d['contrib']
        # logger.debug('total_contrib={} and max_contrib={} and contrib_short={}'.format(
        #     total_contribs, max_contrib, contrib_short))

        # facing_aggro if contrib_short AND not limping during preflop
        could_limp = True if self.phase == self.PHASE_PREFLOP and max_contrib == self.bb_amt else False
        faced_aggro = True if contrib_short and not could_limp else False
        logger.debug('faced_aggro? {}'.format(faced_aggro))

        if action[0] == 'f':
            d['status'] = 'fold'
            d[self.phase].append({
                'action': 'f',
                'aggro': faced_aggro,
            })
            d['hand'] = ['  ', '  ']
            logger.debug('Did action fold')
            self.rotate()

        if action[0] in ['b', 'r']:
            # cannot bet/raise less than required
            if int(action[1]) < max_contrib:
                raise ValueError('A raise {} cannot be less than the max contrib {}'.format(action[1], max_contrib))

            # player raising on BB gives error (since it is the same)
            if not int(action[1]) - contrib_short and 'is_BB' not in d:
                # logger.warn('changed bet/raise that is equal to maxcontrib instead to a call')
                action[0] = 'c'

            # change to allin if it is all the money
            if int(action[1]) >= p['balance'] - d['contrib']:
                # logger.warn('changed b/r to allin as it is everything player has')
                action[0] = 'a'
            else:
                # cannot bet if you are required to put in (e.g. somebody else made bet)
                actions_player = []
                for action_player in self.data.values():
                    actions_player.extend(''.join(pa['action'] for pa in action_player[self.phase]))
                action[0] = 'r' if set(['s', 'l', 'b']) & set(actions_player) else 'b'
                action_name = 'raise' if action[0] == 'r' else 'bet'
                # logger.error('action is {} from {} & {}'.format(action[0], set(['s', 'l', 'b']), set(actions_player)))

                bet_to_pot = int(action[1]) / (self.pot + total_contribs)
                d[self.phase].append({
                    'action': action[0],
                    'aggro': faced_aggro,
                    'bet_to_pot': bet_to_pot,
                })
                d['contrib'] += int(action[1])
                logger.debug('Did action bet/raise {}'.format(action[0]))
                self.rotate()

        if action[0] in ['k', 'c']:
            # if no balance left, then it is an allin
            if d['contrib'] >= p['balance']:
                action[0] = 'a'
            else:
                # cannot check if short
                if action[0] == 'k' and contrib_short:
                    action[0] = 'c'
                # fix call to check if nothing to match
                elif action[0] == 'c' and not contrib_short:
                    action[0] = 'k'

                d[self.phase].append({
                    'action': action[0],
                    'aggro': faced_aggro,
                })
                d['contrib'] += contrib_short
                logger.debug('Did action {} (contrib: {})'.format(action[0], contrib_short))
                self.rotate()

        if action[0] == 'a':
            # can be short, but still allin, therefore always use the balance for the amount
            d[self.phase].append({
                'action': 'a',
                'aggro': faced_aggro,
            })
            d['status'] = 'allin'
            d['contrib'] = p['balance']
            logger.debug('Did action allin')
            self.rotate()

        if self.is_round_finished():
            self.gather_the_money()
            phase_data['finished'] = True

        # adjust strength with current stats
        self.adjust_strength(s, d, action[0])

    def gather_the_money(self):
        """Gathering money from each player's contrib

        How to handle allin?

        Since gathering only happens when
        - round is finished
        - everybody goes allin
        - during MC when getting net EV

        Only the highest contrib of all players need to be reduced to
        the next highest contrib
        """
        contribs = [pd['contrib'] for pd in self.data.values()]
        max_first = contribs.pop(contribs.index(max(contribs)))
        max_second = contribs.pop(contribs.index(max(contribs)))
        returned = max_first - max_second
        for s, d in self.data.items():
            if returned and d['contrib'] == max_first:
                d['contrib'] -= returned
                logger.debug('Returned {} as unmatched for player {}'.format(returned, s))
            self.pot += d['contrib']
            self.players[s]['balance'] -= d['contrib']
            d['matched'] += d['contrib']
            # logger.info('player {} matched: {} (added {})'.format(s, d['matched'], d['contrib']))
            d['contrib'] = 0

    def is_round_finished(self):
        """
        This checks if the round is finished.
        - all players has had a chance to bet
        - money put in pot is the same for every 'in' player (ignoring allin)
        - in cannot be lower than allin (has to call with bigger pot)
        """
        is_bb_finished = True
        in_contribs = Counter()
        allin_contribs = Counter()
        for s, d in self.data.items():
            # logger.debug('{} is {}'.format(s, d))
            if d['status'] == 'in':
                if not d[self.phase]:
                    # logger.debug('#{} has not acted yet'.format(s))
                    return False
                elif 'is_BB' in d and len(d[self.phase]) < 2:
                    is_bb_finished = False
                in_contribs.update([d['contrib']])
            elif d['status'] == 'allin':
                allin_contribs.update([d['contrib']])

        if len(list(in_contribs)) > 1:
            # logger.debug('bets are not equal')
            return False

        elif list(in_contribs) and len(list(allin_contribs)) and min(list(in_contribs)) < max(list(allin_contribs)):
            # logger.debug('still have to call allin')
            return False

        elif not is_bb_finished:
            # logger.debug('BB still has to act')
            return False

        logger.info('round is finished')

        """Helper to quickly check if all players are allin
        or if one player is allin and another called

        If one goes allin, and TWO players call, then they can still bet again.
          Check the todo
        """
        # Todo need to handle allin players creating sidepot
        statuses = Counter([d['status'] for d in self.data.values()])
        if statuses['allin'] and statuses['in'] <= 1:
            self.go_to_showdown = True
            logger.debug('go_to_showdown {} players are allin'.format(statuses['allin']))

        return True

    def check_game_finished(self):
        """
        If all players fold preflop then end the game. This will mark every phase as
        finished, except SD - which still need to do the distribution to winners. Then
        it will mark itself as finished, as it is basically just a post-process game
        ending.

        Phase gets set to SD so that phases do not deal cards to the board
        and cause misinformation in the storage.

        Default is False
        Conditions:
        - all folded, last one left
         * this includes allins
         ** allins still need to follow the river and showdown
        """
        if self.phase == self.PHASE_SHOWDOWN:
            logger.debug('Game already in showdown')
            return

        statuses = Counter([d['status'] for d in self.data.values()])
        # logger.debug('statuses {}'.format(statuses))
        if (statuses['in'] + statuses['allin']) <= 1:
            logger.info('Game finished with only 1 player left "in"')
            self.gather_the_money()
            self.phase = self.PHASE_SHOWDOWN
            return

    def adjust_strength(self, s, d, a):
        """Adjust the min/max tuple of strength based on action taken"""
        # logger.info('adjusting strength for action {}'.format(a))

        if a in ['f', 'sb', 'bb']:
            logger.debug('action is fold, bye bye')
            return

        # update strength to fold limit
        fold_perc = d['stats']['actions'].get('f', 0.01)
        logger.debug('seat {} has fold perc {} for current stats'.format(s, fold_perc))

        new_strength = d['strength'] * (1 - fold_perc)
        logger.debug('new strength = {} (old {} * {})'.format(new_strength, d['strength'], (1 - fold_perc)))
        d['strength'] = new_strength


class PE(PokerEval):
    GAME = 'holdem'
    ITERATIONS = 50000
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
    @lru_cache(maxsize=1<<18)
    def pokereval_2(cls, b1, b2, b3, b4, b5, c1, c2, c3, c4):
        board = [b1, b2, b3, b5, b5]
        hrp = [[c1, c2], [c3, c4]]
        # logger.debug('reconstructed b= {} & c= {}'.format(board, hrp))
        eval = cls.poker_eval(cls, board=board, pockets=hrp,
                              iterations=cls.ITERATIONS_FAST, game=cls.GAME)
        # logger.debug('{} => {}'.format(hrp, [e['ev'] for e in eval['eval']]))
        return eval


class MonteCarlo:

    TIMEOUT = 1 << 6

    def __init__(self, engine):
        """Receives the engine and creates the tree
        Start with adding hero moves
        Do not use self.engine ever, wrong instance
        """
        self.engine = engine
        self.hero = engine.q[0][0]
        logger.info('HERO is at seat {} with {}'.format(self.hero, self.engine.data[self.hero]['hand']))

        self.leaves_reached = 0
        self.is_complete = False

        self.tree = Tree()
        root = self.tree.create_node('root', identifier='0_root', data={'traversed': 0, 'ev': 0})
        # logger.info('tree:\n{}'.format(self.tree.show()))

    def run(self):
        """Run simulations
        For x:
         - clone engine
         - start at root
          -- iterate and find next unprocessed node
          -- action engine to that node parent
          -- process that node
         - keep processing
         - with return EV

         Levelling:
            extremely huge iterations when many players. So
            do the most probably actions only till all done.
        """
        logger.info('Monte Carlo started')
        time_start = time.time()
        while not self.is_complete and time.time() - time_start < self.TIMEOUT:
            self.is_complete = True
            leaves = self.tree.paths_to_leaves()
            logger.debug('leaves from tree: {}'.format(len(leaves)))
            leaves.sort(key=len)
            logger.debug('{} leaves are now sorted by length'.format(len(leaves)))
            leaves.sort(key=lambda lp: lp[-1][0])
            logger.debug('{} leaves are now sorted by rank'.format(len(leaves)))
            for leave in leaves:
                self.run_item(leave)
                # self.show_best_action()
                # input('>>')
                # if random.random() < 0.001:
                #     input('random check')
                if time.time() - time_start >= self.TIMEOUT:
                    logger.warn('time is up for processing!')
                    break
        duration = time.time() - time_start
        logger.warn('Monte Carlo {}/s ended after {} taking {}s'.format(
            self.leaves_reached // duration, self.leaves_reached, int(duration)))
        self.show_best_action()

    def run_item(self, path):
        logger.debug('run item args: {}'.format(path))
        e = deepcopy(self.engine)
        e.mc = True
        """To calculate the investment for the loss EV, the total amounts used till end is required. Cannot
         use final player balance on engine as that might have winnings allocated to it by the engine. Instead
         the difference from all the new matched bets from the current matched bets will be used.
         Need to add current contrib
        """
        e.matched_start = e.data[e.q[0][0]]['matched'] + e.data[e.q[0][0]]['contrib']
        logger.info('starting matched = {} from {} + {}'.format(
            e.matched_start, e.data[e.q[0][0]]['matched'], e.data[e.q[0][0]]['contrib']))

        # self.tree.show()
        # logger.debug('fast forwarding to path {}'.format(args))
        self.fast_forward(e, path)
        logger.info('\n{}'.format('=' * 150))
        # input('check item')

    def fast_forward(self, e, path):
        """Do actions on engine till the leaf is reached. Need to do available_actions before
        every DO

        First check if the leave is already processed, then skip this path. When the leaf is reached
        then process from that node.

        Remember to send through only the first letter for the action.

        Then update the nodes from this leaf back up the tree
        """
        # logger.info('Fast forwarding to this path {}'.format(path))

        if len(path) == 1:
            logger.info('processing root for first time')
            self.process_node(e, self.tree[path[0]])
            self.is_complete = False
            return

        leaf_node = self.tree[path[-1]]
        if leaf_node.data['traversed']:
            logger.debug('This leaf node ({}) already traversed, skipping it'.format(leaf_node.tag))
            return

        for nid in path[1:]:
            node = self.tree[nid]
            # logger.debug('node data {}'.format(node.data))
            e.available_actions()
            cmd = [node.data['action'][0]]
            if 'amount' in node.data:
                cmd.append(node.data['amount'])
                logger.debug('Adding bet value of {}'.format(node.data['amount']))
            logger.debug('Executing path action {} for {}'.format(cmd, node.tag))
            e.do(cmd)

            if node.is_leaf():
                logger.debug('{} is a leaf node, processing next...'.format(node.tag))
                self.process_node(e, node)
                logger.info('nodes processed, now updating nodes that were fast forwarded')
                for processed_nid in reversed(path[1:]):
                    processed_node = self.tree[processed_nid]
                    self.update_node(processed_node)

        logger.info('all nodes in path processed')
        self.is_complete = False

    def show_best_action(self):
        """Calculates best action on root"""
        max_ev = float('-inf')
        action = None
        amount = None
        for nid in self.tree[self.tree.root].fpointer:
            dat = self.tree[nid].data
            # logger.debug('node data = {}'.format(dat))
            if dat['ev'] > max_ev:
                max_ev = dat['ev']
                action = dat['action']
                if action.startswith('bet'):
                    amount = dat['amount']
            logger.warn('{} @{} => {}'.format(dat['action'], dat['traversed'], dat['ev']))
        logger.error('Best action is {} {}'.format(
            action,
            'with {}'.format(amount) if amount else ''
        ))

    def process_node(self, e, n):
        """Process node
        Get actions available for node
        Pick action to traverse with UCT
        Process action selected
        Return EV
        """
        logger.info('processing node {}'.format(n.tag))

        if not n.fpointer:
            self.add_actions(e, n)

        if n.is_leaf():
            logger.info('node {} is the final action in the game'.format(n.tag))
            # either the game finished and we have winner and pot
            # or we have to use pokereval.winners
            if e.winner:
                logger.debug('engine gave winner {}'.format(e.winner))
                net_results = self.net(e)
                ev = net_results[0] if self.hero in e.winner else net_results[1]
            # else if the winner is unknown
            # then calculate winners and use
            # percentage of hero as amt
            else:
                equities = PE.showdown_equities(e)
                logger.debug('pokereval equities: {}'.format(equities))
                winnings, losses = self.net(e)
                ev_pos = winnings * equities[self.hero]
                logger.debug('ev_pos = {} from winnings {} * eq {}'.format(ev_pos, winnings, equities[self.hero]))
                ev_neg = losses * (1 - equities[self.hero])
                logger.debug('ev_neg = {} from losses {} * -eq {}'.format(ev_neg, losses, (1 - equities[self.hero])))
                ev = ev_pos + ev_neg
                logger.info('Net EV: {} from {} + {}'.format(ev, ev_pos, ev_neg))
            result = {
                'ev': ev,
                'traversed': 1,
            }
            logger.info('{} leaf has result {}'.format(n.tag, result))
            n.data.update(result)
            return

        # not a leaf, so get child actions and
        # process chosen uct node
        else:
            # a_node = self.uct_action(n)
            # a_node = self.min_action(n)
            a_node = self.most_probable_action(n)
            action = a_node.data['action']
            logger.info('taking action {}'.format(action))

            # if it is hero and he folds,
            # it is not necessarily an immediate ZERO equity
            # since my previous contrib needs to be added to the pot (i.e. contribs after starting mc)
            # i.e. make this a leaf node implicitly
            # no need to remove children as not added (at start of method)
            if action == 'fold' and self.hero == e.q[0][0]:
                winnings, losses = self.net(e)
                result = {
                    'ev': losses,
                    'traversed': 1,
                }
                logger.info('hero has folded: {}'.format(result))
                a_node.data.update(result)

            # else we must process the node
            else:
                logger.info('taking action {} and processing that node'.format(action))
                cmd = [action[0]]
                if 'amount' in a_node.data:
                    cmd.append(a_node.data['amount'])
                    logger.debug('Adding bet value of {}'.format(a_node.data['amount']))
                e.do(cmd)
                self.process_node(e, a_node)

            # it will traverse back up to the root
            # root can be skipped
            if n.is_root():
                logger.debug('reached the root')
                return

            # action node has been processed, now update node
            self.update_node(n)

    def update_node(self, node):
        """Update the node's data

        If leaf, then it was already calculated during processing, and now
        do not change it: the ev is the ev

        If hero then MAX, else avg by stat/p for foes
        """
        if not node.fpointer:
            # logger.debug('not updating {}: it iss final game result (no leaf nodes)'.format(node.tag))
            return

        # logger.info('updating node {}'.format(node.tag))
        n_ev = 0
        n_traversed = 0
        for child_nid in node.fpointer:
            child_node = self.tree[child_nid]
            dat = child_node.data
            if not dat['traversed']:
                # logger.debug('{} skipping untraversed'.format(child_node.tag))
                continue

            if node.data['seat'] == self.hero:
                n_ev = max(n_ev, dat['ev'])
            else:
                n_ev = min(n_ev, dat['ev'])
                # ev = dat['ev'] * dat['stats']
                # n_ev += ev
                # logger.debug('{} ev~{} from ev~{} * p~{}'.format(
                #     child_node.tag, int(ev * 100), round(dat['ev'], 3), round(dat['stats'], 3)))
            n_traversed += dat['traversed']

        node.data.update({
            'ev': n_ev,
            'traversed': n_traversed
        })
        logger.info('{} ev~{} after {} using {}'.format(
            node.tag, round(n_ev, 3), n_traversed,
            'hero MAX' if node.data['seat'] == self.hero else 'foe AVG'))
        self.leaves_reached += 1

    def net(self, e):
        """Stored the balance at the start of sim.
        Now calculate difference as player total contrib
        Winnings will be less total contrib

        if player is SB/BB then the blinds gets added to neg ev, which
          is probably wrong.
        """
        e.gather_the_money()
        p = e.players[self.hero]
        d = e.data[self.hero]

        matched_diff = d['matched'] - e.matched_start
        logger.debug('matched diff = {} from {} - {}'.format(matched_diff, d['matched'], e.matched_start))

        winnings = int(e.pot - matched_diff)
        logger.debug('winnings diff = {} from pot {} less matched {}'.format(winnings, e.pot, matched_diff))

        losses = int(-matched_diff)
        logger.info('Winnings = {} and losses = {}'.format(winnings, losses))
        return winnings, losses

    def most_probable_action(self, parent):
        """All nodes will be processed once at least but it will never happen. Just return
        the most probable node for most accurate play."""
        logger.info('getting most probable action for {}'.format(parent.tag))
        for _ in range(9):
            for nid in parent.fpointer:
                if not nid.startswith(str(_)):
                    continue
                child = self.tree[nid]
                if not child.data['traversed']:
                    logger.debug('{} is untraversed, returning that node for actioning'.format(child.tag))
                    return child
        raise Exception('All nodes processed, how is that possible, wtf?!')

    def add_actions(self, e, parent):
        """Add actions available to this node
        If in GG phase then no actions possible, ever.
        Remove 'hand'
        Bets:
            - preflop are 2-4x BB
            - postflop are 40-100% pot
        Raise:
            - always double
        Allin:
            - only on river
            - if out of money then converted to allin

        Scale non-fold probabilities even though it should not have an effect.
        """
        # logger.info('adding actions to {}'.format(parent.tag))
        s, p = e.q[0]
        d = e.data[s]
        balance_left = p['balance'] - d['contrib']
        actions = e.available_actions()

        if not actions:
            logger.warn('no actions to add to node')
            return

        if 'gg' in actions:
            logger.debug('no actions available, got gg')
            return

        actions.remove('hand')

        # remove fold if player can check
        if 'check' in actions:
            actions.remove('fold')
            logger.debug('removed fold when check available')

        # remove raise if player has already been aggressive
        if 'raise' in actions and any(pa['action'] in 'br' for pa in d[e.phase]):
            actions.remove('raise')
            logger.debug('removed raise as player has already been aggressive')

        # leave allin only for river
        if 'allin' in actions:
            actions.remove('allin')
            logger.debug('removed allin by default')

        # load stats (codes with counts)
        stats = ES.player_stats(e, s)

        # allin needs to be the doc count
        # where bets and raises result in allin, add those prob dists to this
        # that will give proper probability
        go_allin = stats['actions'].get('allin', 0.01) if e.phase == e.PHASE_RIVER else 0

        logger.info('filtered actions: {}'.format(actions))
        # ev 0 instead of none because of root node sum when not all traversed it gives error
        action_nodes = []
        for a in actions:
            node_data = {
                'stats': stats['actions'].get(a[0], 0.01),
                'action': a,
                'phase': e.phase,
                'seat': s,
                'name': p['name'],
                'traversed': 0,
                'ev': 0,
            }

            # bet x2-4 for preflop and 0.50 & 0.75 & 1.00 for postflop
            if a == 'bet':
                amt_prev = 0
                if e.phase == e.PHASE_PREFLOP:
                    bb_multis = [3, 5]
                    for bb_multi in bb_multis:
                        amt = int(e.bb_amt * bb_multi)
                        if amt >= balance_left:
                            go_allin += node_data['stats'] / len(bb_multis)
                            logger.debug('not enough money to raise, going allin {} vs {}'.format(amt, balance_left))
                        elif amt == amt_prev:
                            logger.error('amount same as previous bet! {} vs {}'.format(amt, amt_prev))
                        else:
                            node_data_copy = deepcopy(node_data)
                            node_data_copy['stats'] /= len(bb_multis)
                            node_data_copy['action'] = 'bet_{}BB'.format(bb_multi)
                            node_data_copy['amount'] = amt
                            action_nodes.append(node_data_copy)
                            amt_prev = amt
                            # logger.debug('preflop bet: {} <= {} * {}BB'.format(amt, e.bb_amt, bb_multi))
                else:
                    pot_ratios = stats['btps'].values()
                    for pot_ratio in pot_ratios:
                        amt = int(e.pot * pot_ratio)
                        if amt >= balance_left:
                            go_allin += node_data['stats'] / len(pot_ratios)
                            logger.debug('not enough money to raise, going allin {} vs {}'.format(amt, balance_left))
                        elif amt == amt_prev:
                            logger.error('amount same as previous bet! {} vs {}'.format(amt, amt_prev))
                        else:
                            node_data_copy = deepcopy(node_data)
                            node_data_copy['stats'] /= len(pot_ratios)
                            node_data_copy['action'] = 'bet_{}%'.format(pot_ratio)
                            node_data_copy['amount'] = amt
                            action_nodes.append(node_data_copy)
                            amt_prev = amt
                            logger.debug('postflop bet: {} <= {} * {}%'.format(amt, e.pot, pot_ratio))

            # only double
            elif a == 'raise':
                max_contrib = max(pd['contrib'] for pd in e.data.values())
                amt = max_contrib * 2
                if amt >= balance_left:
                    go_allin += node_data['stats']
                    logger.debug('not enough money to raise, going allin {} vs {}'.format(amt, balance_left))
                else:
                    node_data_copy = deepcopy(node_data)
                    # node_data_copy['stats'] /= len(pot_ratios)
                    node_data_copy['action'] = 'raise'
                    node_data_copy['amount'] = amt
                    action_nodes.append(node_data_copy)
                    # logger.debug('raise: {} <= {} * 2'.format(amt, max_contrib))

            else:
                action_nodes.append(node_data)

        # allin will have doc counts (from stat, maybe from bets, maybe from raise)
        if go_allin:
            node_data = {
                'stats': go_allin,
                'action': 'allin',
                'phase': e.phase,
                'seat': s,
                'name': p['name'],
                'traversed': 0,
                'ev': None,
            }
            action_nodes.append(node_data)
            # logger.debug('added allin to actions with stat {}'.format(node_data['stats']))

        # scale the stats (it is currently term counts aka histogram) and it is required to be
        # a probability distribution (p~1)
        total_stats = sum(an['stats'] for an in action_nodes if an['action'] != 'fold')
        non_fold_equity = 1 - stats['actions'].get('fold', 0)
        # logger.debug('total stats equity = {} and non_fold_equity = {}'.format(total_stats, non_fold_equity))
        logger.info('before sorting {}'.format(action_nodes))
        sorted(action_nodes, key=itemgetter('stats'))
        logger.info('after sorting {}'.format(action_nodes))
        for rank, action_node in enumerate(action_nodes):
            node_tag = '{}_{}_{}'.format(action_node['action'], s, e.phase)
            identifier = '{}_{}'.format(rank + 1, uuid.uuid4())
            if action_node['action'] != 'fold':
                action_node['stats'] = max(0.01, action_node['stats'] / total_stats * non_fold_equity)
            self.tree.create_node(tag=node_tag, identifier=identifier, parent=parent.identifier, data=action_node)
            logger.debug('new {} for {} with data {}'.format(node_tag, s, action_node))
        logger.info('{} node actions added'.format(len(action_nodes)))


class Game:
    def __init__(self, table):
        '''
        Create an engine for this game
        monte carlo will use the engine instances for iterations
        Game will only keep track of this current game

        First get actions from engine, then the repr
        '''
        self.engine = Engine(table.button, table.players, table.sb, table.bb)
        # self.cut_pockets()

    @retrace.retry(limit=3)
    def play(self):
        while True:
            available_actions = self.engine.available_actions()
            if not available_actions:
                logger.info('No actions received from engine!')
                break

            r = repr(self.engine)
            o = ' | '.join(available_actions)
            i = input('\n\n\n' + r + '\n\n' + o + '\n$ ')
            if i == 'X':
                return
            if i == 'M':
                MonteCarlo(self.engine).run()
                continue
            self.handle_input(i.lower())
            self.persist_engine()

        self.save_game()

    def handle_input(self, i):
        logger.info('input = {}'.format(i))
        cmd = i.split(' ')
        self.engine.do(cmd)

    def save_game(self):
        logger.info('saving game...')
        game_id = ''.join(random.choice(ascii_uppercase + digits) for _ in range(8))
        for s, d in self.engine.data.items():
            doc = {}
            for phase in ['preflop', 'flop', 'turn', 'river']:
                for i, action_info in enumerate(d[phase]):
                    doc['{}_{}'.format(phase, i+1)] = action_info['action']
                    if i == 0:
                        doc['{}_aggro'.format(phase)] = action_info['aggro']
                    if 'bet_to_pot' in action_info:
                        doc['bet_to_pot'] = action_info['bet_to_pot']
            if doc:
                doc.update({
                    'player': self.engine.players[s]['name'],
                    'site': INDEX_NAME,
                    'game': game_id,
                    'vs': self.engine.vs,
                })
                GameAction(**doc).save()
                logger.info('saved {}'.format(doc))

    def persist_engine(self):
        with shelve.open('/code/engine.shlv') as shlv:
            shlv['engine'] = self.engine


class Table:

    def __init__(self):
        with shelve.open('/code/current.shlv') as shlv:
            self.players = shlv.get('players', {})
            self.button = shlv.get('button', 0)
            self.sb = shlv.get('sb', 1)
            self.bb = shlv.get('bb', 2)

    def __repr__(self):
        r = 'Table:\n'
        r += '{} players:\n'.format(len(self.players))
        r += '{}/{} blinds:\n\n'.format(self.sb, self.bb)
        for s, p in self.players.items():
            pr = '{:>10.10}'.format(p.get('name', ''))
            pr += '{: 8d} '.format(p.get('balance', 0))
            pr += '{:>4}'.format(s)
            if p:
                pr += '{} '.format('   ' if p['status'] else 'OUT')
                pr += '{} '.format('[]' if self.button == s else '  ')
            r += '{}\n'.format(pr)
        return r

    @retrace.retry(limit=99)
    def run(self):
        while True:
            r = repr(self)
            o = ' | '.join(self.options)
            i = input('\n\n\n' + r + '\n\n' + o + '\n$ ')
            self.handle_input(i.split(' '))

    @property
    def options(self):
        my_options = [
            'Table [Button|Join|Leave|Seats]',
            '#seat [Name|Balance|Sitout]',
            'Play',
        ]
        return my_options

    def handle_input(self, cmd):
        '''
        Table
            Button
            Join
            Leave
            Seats
        #
            Name
            Balance
            Status
        '''
        # print('cmd 0 = [{}] {}'.format(type(cmd[0]), cmd[0]))
        if cmd[0] == 'Q':
            self.persist_table()
            sys.exit()

        elif cmd[0] == 't':
            if cmd[1] == 'b':
                self.button = int(cmd[2])
            elif cmd[1] == 'j':
                self.players[int(cmd[2])] = {
                    'name': 'joe',
                    'balance': 100,
                    'status': 1,
                }
            elif cmd[1] == 'l':
                self.players[int(cmd[2])] = {
                    'name': '',
                    'balance': 0,
                    'status': 0,
                }
            elif cmd[1] == 's':
                seats = int(cmd[2])
                logger.info('setting table seats from {} to {}'.format(len(self.players), seats))
                while len(self.players) < seats:
                    next_seat = 1 if not self.players else max(list(self.players.keys())) + 1
                    self.players[next_seat] = {
                        'name': 'joe',
                        'balance': 100,
                        'status': 1,
                    }
                    logger.info('adding seat {}'.format(next_seat))
                while len(self.players) > seats > 0:
                    last_seat = max(list(self.players.keys()))
                    del self.players[last_seat]
                    logger.info('removed seat {}'.format(last_seat))

        elif cmd[0].isdigit():
            seat = int(cmd[0])
            if cmd[1] == 'n':
                self.players[seat]['name'] = cmd[2]
            elif cmd[1] == 'b':
                self.players[seat]['balance'] = int(cmd[2])
            elif cmd[1] == 's':
                self.players[seat]['status'] = not self.players[seat]['status']

        elif cmd[0] == 'p':
            if len(cmd) == 3:
                self.sb = int(cmd[1])
                self.bb = int(cmd[2])
            self.play()

        elif cmd[0] == 'g':
            players = {}
            for _ in range(1, 9):
                players[_] = {
                    'name': '?',
                    'balance': 160,
                    'status': 1,
                }
            players[4]['name'] = 'me'
            self.players = players

        else:
            raise ValueError('unknown {}'.format(cmd))

    def play(self):
        """Plays a game

        Then afterwards forwards the button
        and set 0 balance player to out
        Save game state"""
        game = Game(self)
        game.play()

        while True:
            self.button += 1
            if self.button > len(self.players):
                self.button = 1
            if self.players[self.button]['status']:
                break

        for s, p in self.players.items():
            if not p['balance']:
                p['status'] = 0

        self.persist_table()

    def persist_table(self):
        logger.info('saving table info...')
        with shelve.open('/code/current.shlv') as shlv:
            shlv['players'] = self.players
            shlv['button'] = self.button
            shlv['sb'] = self.sb
            shlv['bb'] = self.bb


def pocket_rankings():
    """Calculate all possible starting hands"""
    from itertools import product, combinations

    ranks = list(range(2, 10)) + ['t', 'j', 'q', 'k', 'a']
    suits = ['s', 'd', 'c', 'h']
    cards = ['{}{}'.format(r, s) for r, s in product(ranks, suits)]
    logger.info('{} cards {}'.format(len(cards), cards))

    combs = list(combinations(cards, 2))
    logger.info('{} combos created'.format(len(combs)))

    pocket_ranks = {PE.hand_strength(c) + random.random() / 10**8: c for c in combs}
    logger.info('{} total pocket rankings'.format(len(pocket_ranks)))
    for ps, pc in pocket_ranks.items():
        logger.info('{} = {}'.format(ps, pc))
    with shelve.open('/code/pocket_ranks.shlv') as shlv:
        shlv['pocket_ranks'] = pocket_ranks

    abstracts = set()
    pocket_abstracts = {}
    for comb in combs:
        abstract = ''.join(sorted([comb[0][0], comb[1][0]]))
        if comb[0][0] != comb[1][0] and comb[0][1] == comb[1][1]:
            abstract += 's'
        pocket_abstracts[comb] = abstract
        abstracts.add(abstract)
        logger.debug('{} => {}'.format(comb, abstract))
    with shelve.open('/code/pocket_abstracts.shlv') as shlv:
        shlv['pocket_abstracts'] = pocket_abstracts
    logger.info('{} abstracts'.format(len(abstracts)))


class PokerError(ValueError):
    pass


def test_cache():
    assert cached(1, 2, 3) == 'a'
    logger.info(cached.cache_info())
    assert cached(2, 1, 3) == 'b'
    logger.info(cached.cache_info())
    assert cached(2, 3, 1) == 'c'
    logger.info(cached.cache_info())
    assert cached(1, 2, 3) == 'a'
    logger.info(cached.cache_info())
    assert cached(2, 1, 3) == 'b'
    logger.info(cached.cache_info())
    assert cached(2, 3, 1) == 'c'
    logger.info(cached.cache_info())

@lru_cache()
def cached(a, b, c):
    logger.info('a={} b={} c={}'.format(a, b, c))
    if a == 1:
        return 'a'
    if b == 1:
        return 'b'
    if c == 1:
        return 'c'
    return False


if __name__ == '__main__':
    table = Table()
    table.run()
    # pocket_rankings()
    # test_cache()
