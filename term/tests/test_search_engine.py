from es.es import ES
from engine.engine import Engine


class TestSearchEngine:

    def test_player_stats(self):
        e = Engine(
            'CoinPoker', 1,
            {
                1: {'name': 'joe', 'balance': 1000, 'status': 1},
                2: {'name': 'jane', 'balance': 1000, 'status': 1},
            },
            50, 100, 0,
        )
        e.available_actions()
        stats = ES.player_stats(e, e.s)
        assert 'actions' in stats
        assert len(stats['actions']) >= 4
        assert 0 < stats['hs'] < 100

    def test_player_stats_on_hand(self):
        e = Engine(
            'CoinPoker', 1,
            {
                1: {'name': 'joe', 'balance': 1000, 'status': 1},
                2: {'name': 'jane', 'balance': 1000, 'status': 1},
                3: {'name': 'jane', 'balance': 1000, 'status': 1},
                4: {'name': 'jane', 'balance': 1000, 'status': 1},
                5: {'name': 'jane', 'balance': 1000, 'status': 1},
                6: {'name': 'jane', 'balance': 1000, 'status': 1},
            },
            50, 100, 0,
        )
        e.available_actions()

        # p4
        e.do(['r', 100])
        e.available_actions()

        # p5
        e.do(['f'])
        e.available_actions()

        # p6
        e.do(['f'])
        e.available_actions()

        # p1
        e.do(['c'])
        e.available_actions()

        # p2
        e.do(['c'])
        e.available_actions()

        # p3
        e.do(['k'])
        e.available_actions()

        # p2
        e.do(['b', 100])
        e.available_actions()

        # p3
        stats = ES.player_stats(e, e.s)
        # hs = res.aggregations['hs']['hs_agg']['values']['50.0']
        assert len(stats['actions']) >= 4
        assert stats['hs'] is not None
        assert 0 < stats['hs'] < 100

        res = ES.player_stats(e, e.s, 100)
        hits = res.hits.hits
        assert res.aggregations['hs'].doc_count >= 85
        hs = res.aggregations['hs']['hs_agg']['values']['50.0']
        assert hs is not None
        assert 0 < hs < 100

    def test_showdown_hs(self):
        e = Engine(
            'CoinPoker', 1,
            {
                1: {'name': 'joe', 'balance': 1000, 'status': 1},
                2: {'name': 'joe', 'balance': 1000, 'status': 1},
            },
            50, 100, 0,
        )
        e.available_actions()

        # p1
        e.do(['r', 100])
        e.available_actions()

        # p2
        e.do(['c'])
        e.available_actions()

        # p2
        e.do(['k'])
        e.available_actions()

        # p1
        e.do(['b', 200])
        e.available_actions()

        # p2 has:
        # preflop_1 = l
        # preflop_2 = c
        # flop_1 = k
        hs = ES.showdown_hs(e, e.s, percentile=50)
        assert hs is not None
        assert 0 < hs < 1
        hs2 = ES.showdown_hs(e, e.s, percentile=10)
        assert hs2 < hs
        hs3 = ES.showdown_hs(e, e.s, percentile=90)
        assert hs3 > hs

        res = ES.showdown_hs(e, e.s, 200)
        hits = res.hits.hits
        assert len(hits) == 200
        assert hits[0]['_score'] > 4
        assert hits[-1]['_score'] > 0
















