from pe.pe import req_equities


class TestPokerEval:

    def test_req_equities(self):
        board = ['__'] * 5
        pockets = [['as', 'ac'], ['__'] * 2]
        res = req_equities(board, pockets)
        # a = {
        #     'eval': [
        #         {'ev': 850, 'losehi': 2916, 'loselo': 0, 'scoop': 16947, 'tiehi': 137, 'tielo': 0, 'winhi': 16947, 'winlo': 0},
        #         {'ev': 149, 'losehi': 16947, 'loselo': 0, 'scoop': 2916, 'tiehi': 137, 'tielo': 0, 'winhi': 2916, 'winlo': 0}
        #     ],
        #     'info': [20000, 0, 1]
        # }
        assert res['info'][0] == 20000
        assert res['eval'][0]['ev'] == 850
        assert res['eval'][1]['ev'] == 149
