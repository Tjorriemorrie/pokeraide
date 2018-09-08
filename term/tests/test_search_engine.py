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
            },
            50, 100, 0,
        )
        e.available_actions()
        res = ES.player_stats(e, e.s, 200)
        hs = res.aggregations['hs']['hs_agg']['values']['50.0']
        e.do(['r', 50])
        e.available_actions()
        res = ES.player_stats(e, e.s, 200)
        hs = res.aggregations['hs']['hs_agg']['values']['50.0']
        e.do(['r', 50])
        e.available_actions()
        res = ES.player_stats(e, e.s, 200)
        hs = res.aggregations['hs']['hs_agg']['values']['50.0']
        e.do(['r', 50])
        e.available_actions()
        res = ES.player_stats(e, e.s, 200)
        hs = res.aggregations['hs']['hs_agg']['values']['50.0']
        assert hs is not None
        assert 0 < hs < 100
















