from flask import Flask, request, jsonify
from pokereval import PokerEval


GAME = 'holdem'
ITERATIONS = 20000

app = Flask(__name__)
pe = PokerEval()


@app.route('/', methods=['POST', 'GET'])
def index():
    app.logger.info('index route')
    if request.method == 'POST':
        data = request.get_json()
        app.logger.info('request {}'.format(data))
        equities = pe.poker_eval(
            iterations=ITERATIONS,
            game=GAME,
            **data
        )
        app.logger.info('equities {}'.format(equities))
        return jsonify(equities)
    return 'https://github.com/minmax/pypoker-eval'


app.run(host='0.0.0.0', port=5000, debug=True)
