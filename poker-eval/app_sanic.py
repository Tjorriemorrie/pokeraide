from sanic import Sanic
from sanic import response
from pokereval import PokerEval


GAME = 'holdem'
ITERATIONS = 20000

app = Sanic()
pe = PokerEval()


@app.post('/')
async def post_handler(request):
    data = request.json
    equities = pe.poker_eval(
        iterations=ITERATIONS,
        game=GAME,
        **data
    )
    return response.json(equities)


@app.get('/')
async def get_handler(request):
    return response.text('https://github.com/minmax/pypoker-eval')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5657)
