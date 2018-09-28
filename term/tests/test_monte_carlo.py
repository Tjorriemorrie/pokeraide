from operator import itemgetter

from mc.mc import MonteCarlo
from engine.engine import Engine


class TestMonteCarlo:

    def test_removing_path_earlier_is_easier(self):
        e = Engine(
            'CoinPoker', 1,
            {
                1: {'name': 'joe', 'balance': 1000, 'status': 1},
                2: {'name': 'jane', 'balance': 1000, 'status': 1},
                3: {'name': 'mike', 'balance': 1000, 'status': 1},
                4: {'name': 'mark', 'balance': 1000, 'status': 1},
            },
            50, 100, 0,
        )
        e.available_actions()

        total_traversions = []
        mc = MonteCarlo(e, 1)
        for _ in range(10):
            mc.run(1)
            total_traversions.append(sum(a[2] for a in mc.current_actions))
            # assert len(mc.current_actions) > 0
        traversed_leaves = list(mc.tree.filter_nodes(lambda n: n.is_leaf() and n.data['traversed'] > 0))
        assert len(traversed_leaves) == total_traversions[-1]
        assert total_traversions[-1] > 5, 'Must have traversed something!'
        # 55 after changing showdown equities to search index
        # 55 with showdowns cache
        # 43 PE showdown equities
        # 44 with ES showdowns and cache @ last action
        # 44 with ES showdowns and cache of actions list
        # 44 with ES showdowns and no cache

    def test_longer_runs_are_better(self):
        e = Engine(
            'CoinPoker', 1,
            {
                1: {'name': 'joe', 'balance': 1000, 'status': 1},
                2: {'name': 'jane', 'balance': 1000, 'status': 1},
            },
            50, 100, 0,
        )
        e.available_actions()

        mc = MonteCarlo(e, 1)
        mc.run(10)
        assert len(mc.current_actions) > 0
        total_traversions = sum(a[2] for a in mc.current_actions)
        assert total_traversions > 1, 'Must have traversed something!'

        total_traversions_batches = 0
        for n in range(1, 11):
            mc = MonteCarlo(e, 1)
            mc.run(1)
            assert len(mc.current_actions) > 0
            total_traversions_batches += sum(a[2] for a in mc.current_actions)
            assert total_traversions_batches > 1, 'Must have traversed something!'

        assert total_traversions > total_traversions_batches

    def test_threading(self):
        e = Engine(
            'CoinPoker', 1,
            {
                1: {'name': 'joe', 'balance': 1000, 'status': 1},
                2: {'name': 'jane', 'balance': 1000, 'status': 1},
            },
            50, 100, 0,
        )
        e.available_actions()

        perfs = {}
        for n in range(1, 4):
            mc = MonteCarlo(e, 1)
            mc.N_THREADS = n
            mc.run(2)
            assert len(mc.current_actions) > 0
            total_traversions = sum(a[2] for a in mc.current_actions)
            assert total_traversions > 1, 'Must have traversed something!'
            perfs[n] = total_traversions
        assert perfs

    def test_hs_percentile(self):
        e = Engine(
            'CoinPoker', 1,
            {
                1: {'name': 'joe', 'balance': 1000, 'status': 1},
                2: {'name': 'jane', 'balance': 1000, 'status': 1},
            },
            50, 100, 0,
        )
        avail = e.available_actions()

        # p1 sb
        e.do(['c'])
        avail = e.available_actions()

        # p2 bb
        e.do(['k'])
        avail = e.available_actions()

        # p2
        e.do(['b', 50])
        avail = e.available_actions()

        # p1
        e.do(['c'])
        avail = e.available_actions()

        # p2
        e.do(['b', 100])
        avail = e.available_actions()

        # # p1
        # e.do('c')
        # avail = e.available_actions()
        #
        # # p2
        # e.do(['b', 150])
        # avail = e.available_actions()

        percentile = 50
        history = []
        ev = 1
        while ev > 0 and percentile <= 60:
            mc = MonteCarlo(e, 1)
            mc.PERCENTILE = percentile
            mc.run(100)
            actions = mc.current_actions
            actions.sort(key=itemgetter(1), reverse=True)
            best_action = actions[0]
            ev = best_action[1]
            history.append((percentile, int(ev)))
            percentile += 1
        assert 0 <= percentile <= 100
