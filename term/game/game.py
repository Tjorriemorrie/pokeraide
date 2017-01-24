from copy import deepcopy
import datetime
import logging
from os.path import dirname, realpath, join
import shelve
import random
import retrace
from string import ascii_uppercase, digits

from es.es import GameAction
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
        self.engine = Engine(table.site_name, table.button, table.players, table.sb, table.bb)
        self.history = {}
        self.cursor = 0

    @retrace.retry()
    def play(self):
        """iterative process of inputting commands from table
        engine saved after available actions have been executed"""
        while True:
            available_actions = self.engine.available_actions()
            if not available_actions:
                logger.info('No actions received from engine!')
                break
            self.engine.save()

            r = repr(self.engine)
            o = ' | '.join(available_actions)
            u = self.replay()

            i = input('\n\n\n' + r + '\n\n' + o + u + '\n$ ')
            # exit?
            if i == 'X':
                return
            # undo?
            if i == 'u':
                self.undo()
                continue
            # redo?
            if i == 'R':
                self.replay(True)
                continue
            # analyse?
            if i == 'M':
                MonteCarlo(self.engine).run()
                continue
            # play
            self.handle_input(i.lower())

        self.save_game()

    def handle_input(self, i):
        logger.info('input = {}'.format(i))
        cmd = i.split(' ')
        e_copy = deepcopy(self.engine)
        self.engine.do(cmd)

        # action successful, save in history
        self.history[self.cursor] = (e_copy, i)
        logger.info('keeping history at {} (before cmd {})'.format(self.cursor, i))
        self.cursor += 1

        logger.debug('input handled and done')

    def save_game(self):
        logger.info('saving game...')
        game_id = ''.join(random.choice(ascii_uppercase + digits) for _ in range(8))
        for s, d in self.engine.data.items():
            doc = {}
            for phase in ['preflop', 'flop', 'turn', 'river']:
                for i, action_info in enumerate(d[phase]):
                    doc['{}_{}'.format(phase, i+1)] = action_info['action']
                    doc['{}_{}_rvl'.format(phase, i+1)] = action_info['rvl']
                    if i == 0:
                        doc['{}_aggro'.format(phase)] = action_info['aggro']
                    if 'bet_to_pot' in action_info:
                        doc['{}_{}_btp'.format(phase, i+1)] = action_info['bet_to_pot']
                    if action_info.get('pot_odds'):
                        doc['{}_{}_po'.format(phase, i+1)] = action_info['pot_odds']
            if doc:
                doc.update({
                    'player': self.engine.players[s]['name'],
                    'site': self.engine.site_name,
                    'game': game_id,
                    'vs': self.engine.vs,
                    'created_at': datetime.datetime.utcnow(),
                })
                GameAction(**doc).save()
                logger.info('saved {}'.format(doc))

    def undo(self):
        """Restore previous engine state (before that cmd)
        Since current state is last entry in history, restore
        second to last item"""
        logger.info('undo last action')
        if self.cursor <= 0:
            logger.warn('cannot restore snapshot! cursor at {}'.format(self.cursor))
            return
        self.cursor -= 1
        snapshot = self.history[self.cursor]
        self.engine = snapshot[0]
        logger.info('previous snapshot restored. cursor back at {}'.format(self.cursor))

    def replay(self, force=False):
        """allow same commands to be replayed if in history"""
        if len(self.history) <= self.cursor:
            return ''
        past_i = self.history[self.cursor]
        if not force:
            return '\nReplay: {}?'.format(past_i[1])
        self.handle_input(past_i[1])

