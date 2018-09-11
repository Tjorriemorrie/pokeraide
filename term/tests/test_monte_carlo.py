from mc.mc import MonteCarlo
from engine.engine import Engine


class TestMonteCarlo:

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

        mc = MonteCarlo(e, 1)
        mc.run(2)
        assert len(mc.current_actions) > 0
        total_traversions = sum(a[2] for a in mc.current_actions)
        assert total_traversions > 1, 'Must have traversed something!'
