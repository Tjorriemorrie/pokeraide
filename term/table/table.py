import logging
from os.path import dirname, realpath, join
import shelve
import retrace
from sys import exit

from game.game import Game


logger = logging.getLogger()


class Table:

    FILE = join(dirname(realpath(__file__)), 'table_state')

    def __init__(self):
        with shelve.open(self.FILE) as shlv:
            self.players = shlv.get('players', {})
            self.button = shlv.get('button', 0)
            self.sb = shlv.get('sb', 1)
            self.bb = shlv.get('bb', 2)

    def __repr__(self):
        r = 'Table:\n'
        r += '{} players:\n'.format(len(self.players))
        r += '{}/{} blinds:\n\n'.format(self.sb, self.bb)
        for s, p in self.players.items():
            pr = '{:>10.10}'.format(p.get('name', ''))
            pr += '{: 8d} '.format(p.get('balance', 0))
            pr += '{:>4}'.format(s)
            if p:
                pr += '{} '.format('   ' if p['status'] else 'OUT')
                pr += '{} '.format('[]' if self.button == s else '  ')
            r += '{}\n'.format(pr)
        return r

    @retrace.retry()
    def run(self):
        while True:
            r = repr(self)
            o = ' | '.join(self.options)
            i = input('\n\n\n' + r + '\n\n' + o + '\n$ ')
            self.handle_input(i.split(' '))

    @property
    def options(self):
        my_options = [
            'Table [Button|Join|Leave|Seats]',
            '#seat [Name|Balance|Sitout]',
            'Play',
        ]
        return my_options

    def handle_input(self, cmd):
        '''
        Table
            Button
            Join
            Leave
            Seats
        #
            Name
            Balance
            Status
        '''
        # print('cmd 0 = [{}] {}'.format(type(cmd[0]), cmd[0]))
        if cmd[0] == 'Q':
            self.persist_table()
            exit()

        elif cmd[0] == 't':
            if cmd[1] == 'b':
                self.button = int(cmd[2])
            elif cmd[1] == 'j':
                self.players[int(cmd[2])] = {
                    'name': 'joe',
                    'balance': 100,
                    'status': 1,
                }
            elif cmd[1] == 'l':
                self.players[int(cmd[2])] = {
                    'name': '',
                    'balance': 0,
                    'status': 0,
                }
            elif cmd[1] == 's':
                seats = int(cmd[2])
                logger.info('setting table seats from {} to {}'.format(len(self.players), seats))
                while len(self.players) < seats:
                    next_seat = 1 if not self.players else max(list(self.players.keys())) + 1
                    self.players[next_seat] = {
                        'name': 'joe',
                        'balance': 100,
                        'status': 1,
                    }
                    logger.info('adding seat {}'.format(next_seat))
                while len(self.players) > seats > 0:
                    last_seat = max(list(self.players.keys()))
                    del self.players[last_seat]
                    logger.info('removed seat {}'.format(last_seat))

        elif cmd[0].isdigit():
            seat = int(cmd[0])
            if cmd[1] == 'n':
                self.players[seat]['name'] = cmd[2]
            elif cmd[1] == 'b':
                self.players[seat]['balance'] = int(cmd[2])
            elif cmd[1] == 's':
                self.players[seat]['status'] = not self.players[seat]['status']

        elif cmd[0] == 'p':
            if len(cmd) == 3:
                self.sb = int(cmd[1])
                self.bb = int(cmd[2])
            self.play()

        elif cmd[0] == 'g':
            players = {}
            for _ in range(1, 9):
                players[_] = {
                    'name': '?',
                    'balance': 160,
                    'status': 1,
                }
            players[4]['name'] = 'me'
            self.players = players

        else:
            raise ValueError('unknown {}'.format(cmd))

    def play(self):
        """Plays a game

        Then afterwards forwards the button
        and set 0 balance player to out
        Save game state"""
        game = Game(self)
        game.play()

        while True:
            self.button += 1
            if self.button > len(self.players):
                self.button = 1
            if self.players[self.button]['status']:
                break

        for s, p in self.players.items():
            if not p['balance']:
                p['status'] = 0

        self.persist_table()

    def persist_table(self):
        logger.info('saving table info...')
        with shelve.open(self.FILE) as shlv:
            shlv['players'] = self.players
            shlv['button'] = self.button
            shlv['sb'] = self.sb
            shlv['bb'] = self.bb
