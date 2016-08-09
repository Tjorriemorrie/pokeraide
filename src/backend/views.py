from backend import app
from flask import render_template
from flask.ext.jsontools import jsonapi


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return render_template('index.html')


# ev = our equity * total pot - cost of our call

@app.route('/game/new')
@jsonapi
def game_new():
    game = {
        'id': 42,
        'status': 'setup',
        'players': [
            {
                'name': 'hero',
                'balance': 123,
            }
        ]
    }
    app.logger.info('new game: {}'.format(game))
    return game