import datetime
import logging
from os.path import dirname, realpath, join
import shelve
import random
import retrace
from string import ascii_uppercase, digits

from es.es import INDEX_NAME, GameAction
from engine.engine import Engine
from mc.mc import MonteCarlo


logger = logging.getLogger()


class Game:

    def __init__(self, table):
        '''
        Create an engine for this game
        monte carlo will use the engine instances for iterations
        Game will only keep track of this current game

        First get actions from engine, then the repr
        '''
        self.engine = Engine(table.button, table.players, table.sb, table.bb)
        # self.cut_pockets()

    @retrace.retry()
    def play(self):
        while True:
            available_actions = self.engine.available_actions()
            if not available_actions:
                logger.info('No actions received from engine!')
                break

            r = repr(self.engine)
            o = ' | '.join(available_actions)
            self.engine.save()

            i = input('\n\n\n' + r + '\n\n' + o + '\n$ ')
            if i == 'X':
                return
            if i == 'M':
                MonteCarlo(self.engine).run()
                continue
            self.handle_input(i.lower())

        self.save_game()

    def handle_input(self, i):
        logger.info('input = {}'.format(i))
        cmd = i.split(' ')
        self.engine.do(cmd)
        logger.debug('input handled and done')

    def save_game(self):
        logger.info('saving game...')
        game_id = ''.join(random.choice(ascii_uppercase + digits) for _ in range(8))
        for s, d in self.engine.data.items():
            doc = {}
            for phase in ['preflop', 'flop', 'turn', 'river']:
                for i, action_info in enumerate(d[phase]):
                    doc['{}_{}'.format(phase, i+1)] = action_info['action']
                    if i == 0:
                        doc['{}_aggro'.format(phase)] = action_info['aggro']
                    if 'bet_to_pot' in action_info:
                        doc['{}_{}_btp'.format(phase, i+1)] = action_info['bet_to_pot']
                    if action_info.get('pot_odds'):
                        doc['{}_{}_po'.format(phase, i+1)] = action_info['pot_odds']
            if doc:
                doc.update({
                    'player': self.engine.players[s]['name'],
                    'site': INDEX_NAME,
                    'game': game_id,
                    'vs': self.engine.vs,
                    'created_at': datetime.datetime.utcnow(),
                })
                GameAction(**doc).save()
                logger.info('saved {}'.format(doc))
