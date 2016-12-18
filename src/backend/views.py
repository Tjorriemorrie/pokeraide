import random
import shelve

from backend import app
from flask import render_template, request
from flask_jsontools import jsonapi


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return render_template('index.html')


# ev = our equity * total pot - cost of our call

@app.route('/game', methods=['GET'])
@jsonapi
def game_get():
    s = shelve.open('db.shlv')
    game = s.get('game', {
        'id': int(random.random()),
        'status': 'setup',
        'players': [],
    })
    s['game'] = game
    s.close()
    app.logger.info('game: {}'.format(game))
    return game


@app.route('/game', methods=['POST'])
@jsonapi
def game_post():
    s = shelve.open('db.shlv')
    game = {
        'id': random.randint(1, 999999),
        'status': 'setup',
        'players': [],
    }
    s['game'] = game
    s.close()
    app.logger.info('game: {}'.format(game))
    return game


@app.route('/game/player', methods=['POST'])
@jsonapi
def player_post():
    app.logger.info('player: {}'.format(request.form))
    s = shelve.open('db.shlv')
    # search and fetch db
    # for now, just create
    player = {
        'id': random.randint(2, 999),
        'name': request.form.get('name'),
        'balance': request.form.get('balance'),
        'sit_out': 0,
        'hold_1': '',
        'hold_2': '',
        'is_dealer': 0,
    }
    game = s.get('game')
    game['players'].append(player)
    s['game'] = game
    s.close()
    app.logger.info('final players {}'.format(game['players']))
    return game['players']


@app.route('/game/player/<int:id>', methods=['DELETE'])
@jsonapi
def player_delete(id):
    app.logger.info('remove player: {}'.format(id))
    s = shelve.open('db.shlv')
    game = s.get('game')
    game['players'] = [p for p in game['players'] if p['id'] != id]
    s['game'] = game
    s.close()
    app.logger.info('final players {}'.format(game['players']))
    return game['players']


@app.route('/game/player/<int:id>', methods=['PATCH'])
@jsonapi
def player_patch(id):
    app.logger.info('player patch id: {}'.format(id))
    app.logger.info('player patch form: {}'.format(request.form))
    s = shelve.open('db.shlv')
    game = s.get('game')
    players = game['players']
    app.logger.info('init players {}'.format(players))
    for player in players:
        if player['id'] != id:
            continue
        for k, v in request.form.to_dict().iteritems():
            app.logger.info('updating k,v {}:{}'.format(k, v))
            if k == 'id':
                pass
            elif k in ['balance', 'sit_out', 'is_dealer']:
                player[k] = int(v)
            elif k in ['hold_1', 'hold_2']:
                player[k] = str(v)
            else:
                raise NotImplementedError(k)
    game['players'] = players
    s['game'] = game
    s.close()
    app.logger.info('final players {}'.format(game['players']))
    return game['players']


@app.route('/game/status', methods=['POST'])
@jsonapi
def game_status():
    status = request.form.get('status', 'setup')
    app.logger.info('game status: {}'.format(status))
    s = shelve.open('db.shlv')
    game = s.get('game')
    game['status'] = status
    s['game'] = game
    s.close()
    app.logger.info('final game status '.format(game['status']))
    return game


@app.route('/game/player/dealer/<int:id>', methods=['POST'])
@jsonapi
def player_dealer(id):
    app.logger.info('player dealer: {}'.format(id))
    s = shelve.open('db.shlv')
    game = s.get('game')
    players = game['players']
    for player in players:
        player['is_dealer'] = 1 if player['id'] == id else 0
    game['players'] = players
    s['game'] = game
    s.close()
    app.logger.info('final players {}'.format(game['players']))
    return game['players']
