from collections import Counter
import datetime
import json
import logging
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import Index, DocType, String, Date, Integer, Float, Boolean, Q, A
from operator import pos
from sortedcontainers import SortedDict

from pocket_rankings.pocket_rankings import PocketRankings


logger = logging.getLogger()
for _ in ("boto", "elasticsearch", "urllib3"):
    logging.getLogger(_).setLevel(logging.ERROR)


connections.create_connection(hosts=['es_host'])

INDEX_NAME = 'governor'

es_index = Index(INDEX_NAME)
# for index in connections.get_connection().indices.get('*'):
#   print(index)
# es_index.delete(ignore=404)
es_index.create(ignore=400)
# logger.info('index truncated')


@es_index.doc_type
class GameAction(DocType):
    site = String(index='not_analyzed')
    game = String(index='not_analyzed')
    vs = Integer()
    player = String(index='not_analyzed')
    amount = Integer()
    pot = Integer()
    pos = Integer()

    preflop_1 = String(index='not_analyzed')
    preflop_1_btp = Float()
    preflop_1_po = Float()
    preflop_2 = String(index='not_analyzed')
    preflop_2_btp = Float()
    preflop_2_po = Float()
    preflop_aggro = Boolean()

    flop_1 = String(index='not_analyzed')
    flop_1_btp = Float()
    flop_1_po = Float()
    flop_2 = String(index='not_analyzed')
    flop_2_btp = Float()
    flop_2_po = Float()
    flop_aggro = Boolean()

    turn_1 = String(index='not_analyzed')
    turn_1_btp = Float()
    turn_1_po = Float()
    turn_2 = String(index='not_analyzed')
    turn_2_btp = Float()
    turn_2_po = Float()
    turn_aggro = Boolean()

    river_1 = String(index='not_analyzed')
    river_1_btp = Float()
    river_1_po = Float()
    river_2 = String(index='not_analyzed')
    river_2_btp = Float()
    river_2_po = Float()
    river_aggro = Boolean()

    created_at = Date()


GameAction.init()


cluster_health = connections.get_connection().cluster.health()
for k, v in cluster_health.items():
    logger.info('Cluster health: {}: {}'.format(k, v))
active_primary_shards = cluster_health['active_primary_shards']


pocket_rankings = PocketRankings.load()


class ES:

    SAMPLE_SIZE = 1 << 7

    @classmethod
    def cut_hand_range(cls, stats):
        fold_perc = stats.get('f', 0.50)
        fold_cutoff = int(len(pocket_rankings) * (1 - fold_perc))
        logger.debug('fold {}% cutting at {}'.format(fold_perc * 100, fold_cutoff))

        hand_range_keys = pocket_rankings.islice(stop=fold_cutoff)
        # logger.debug('hand range keys {}'.format(hand_range_keys))
        hand_range = [pocket_rankings[k] for k in hand_range_keys]
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
            'bool': {
                'should': [
                    {'match': {'player': {'query': p['name'], 'boost': 5}}},
                    # {'match': {'vs': {'query': engine.vs, 'boost': 2}}},
                    {'match': {'site': {'query': INDEX_NAME, 'boost': 1}}},
                ]
            }
        }
        # logger.debug('basic query {}'.format(query))

        # build function score
        function_score = {
            'function_score': {
                'query': query,
                'functions': [
                    {'gauss': {'vs': {'origin': engine.vs, 'scale': 1, 'decay': 0.4}}},
                    # {'gauss': {'created_at': {'origin': datetime.datetime.utcnow(), 'scale': '1d', 'decay': 0.99}}},
                ]
            }
        }
        # logger.debug('function score {}'.format(function_score))

        # HISTORIC
        # add previous info
        phase_matching = []
        for phase in ['preflop', 'flop', 'turn', 'river']:
            for i, action_info in enumerate(d[phase]):
                phase_matching.append({'match': {'{}_{}'.format(phase, i+1): {'query': action_info['action'], 'boost': 3}}})
                if i == 0:
                    phase_matching.append({'match': {'{}_aggro'.format(phase): {'query': action_info['aggro'], 'boost': 3}}})
        # logger.debug('Added {} action filters'.format(len(phase_matching)))
        query['bool']['should'].extend(phase_matching)

        # CURRENT
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

        # get current sitwrap
        contribs_all = [pd['contrib'] for pd in engine.data.values()]
        total_contribs = sum(contribs_all)
        max_contrib = max(contribs_all)
        contrib_short = max_contrib - d['contrib']

        # facing aggression? (currently, not historically like in engine.do)
        pot_odds = None
        if contrib_short:
            could_limp = True if engine.phase == engine.PHASE_PREFLOP and max_contrib == engine.bb_amt else False
            if not could_limp:
                # facing aggro now?
                query['bool']['should'].append({'match': {'{}_aggro'.format(agg_phase): {'query': True, 'boost': 2}}})
                logger.debug('facing aggro: yes, contrib is short and not limping')
                # what is po now?
                balance_left = p['balance'] - d['contrib']
                pot_odds = min(balance_left, contrib_short) / (engine.pot + total_contribs)
                function_score['function_score']['functions'].append(
                    {
                        'gauss': {'{}_po'.format(agg_field): {'origin': pot_odds, 'scale': 0.1, 'decay': 0.9}},
                        'weight': 5,
                    }
                )
                logger.debug('added pot odds at {}'.format(pot_odds))
            else:
                # logger.info('facing aggro: no, could limp: {}'.format(could_limp))
                pass
        else:
            # logger.info('facing aggro: no, contrib short = {}'.format(contrib_short))
            pass

        sea = GameAction.search()
        sea = sea.query(function_score)
        sea = sea.sort('_score', {'created_at': 'desc'})

        # establish which doc field is to be aggregated on for this player
        docs_per_shard = cls.SAMPLE_SIZE / active_primary_shards
        # # logger.info('docs per shard = {}'.format(docs_per_shard))

        sample = A('sampler', shard_size=docs_per_shard)
        terms = A('terms', field=agg_field)
        pottie = A('percentiles', field='{}_btp'.format(agg_field), percents=[10, 30, 50, 70, 90])
        sea.aggs.bucket('mesam', sample).metric('pottie', pottie).bucket('aksies', terms)

        sea = sea[:0]
        res = sea.execute()

        cls.analyze_stats(sea)

        # required to scale now mostly for using fold equity
        total_docs = sum(pa['doc_count'] for pa in res.aggregations.mesam.aksies.buckets)
        phase_actions = {a['key']: a['doc_count'] / total_docs for a in res.aggregations.mesam.aksies.buckets}
        # logger.info('scaled aggs: {}'.format(phase_actions))

        phase_btps = res.aggregations.mesam.pottie.values.to_dict()
        # logger.debug('phase_btps {}'.format(phase_btps))

        # clean out NaN
        phase_btps = {k: round(v, 2) for k, v in phase_btps.items() if isinstance(v, float)} or {'0.50': 0.50}
        # logger.debug('cleaned phase_btps {}'.format(phase_btps))

        # input('>> ')
        return {
            'actions': phase_actions,
            'btps': phase_btps,
        }

    @classmethod
    def analyze_stats(cls, sea):
        # logger.info('analyzing stats returned...')

        sea = sea[:cls.SAMPLE_SIZE]
        res = sea.execute()

        # for h in res:
        #     logger.debug('doc: score {}\n{}'.format(h._score, json.dumps(h.to_dict(), indent=4, sort_keys=True, default=str)))

        docs_by_field = {}
        for h in res:
            for k, v in h.to_dict().items():
                docs_by_field.setdefault(k, []).append(v)
        logger.info('docs_by_field: {}'.format(docs_by_field))

        data = {}
        query = sea.to_dict()
        # logger.debug('query: {}'.format(json.dumps(query, indent=4, sort_keys=True, default=str)))

        shoulds = {}
        for should in query['query']['function_score']['query']['bool']['should']:
            f = list(should['match'].keys())[0]
            c = Counter(docs_by_field.get(f, []))
            v = ['{}% {}'.format(100 * mc[1] // res.hits.total, mc[0]) for mc in c.most_common(3)]
            shoulds[f] = '{} got {}'.format(
                should['match'][f]['query'],
                ' & '.join(v) if v else '<empty>'
            )
        data['shoulds'] = shoulds

        functions = {}
        for function in query['query']['function_score']['functions']:
            f = list(function['gauss'].keys())[0]
            c = Counter(docs_by_field.get(f, []))
            v = ['{}% {}'.format(100 * mc[1] // res.hits.total, mc[0]) for mc in c.most_common(3)]
            data[f] = '{} got {}'.format(
                function['gauss'][f]['origin'],
                ' & '.join(v) if v else '<empty>'
            )
        data['functions'] = functions

        aggs = {
            'askies': res.aggregations.mesam.aksies.buckets,
            'percs': res.aggregations.mesam.pottie['values'],
        }
        data['aggs'] = aggs

        logger.info('data:\n{}'.format(json.dumps(data, indent=4, sort_keys=True, default=str)))

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
        # logger.info('dist = {}'.format(dist))
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
        # logger.debug('dist_stats {}'.format(r))
        return r
