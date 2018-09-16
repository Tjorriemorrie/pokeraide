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

        total_traversions = 0
        for _ in range(11):
            mc = MonteCarlo(e, 1)
            mc.run(1)
            assert len(mc.current_actions) > 0
            total_traversions += sum(a[2] for a in mc.current_actions)
        assert total_traversions > 1, 'Must have traversed something!'
        # 134 for removing upon encountering in queue

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
