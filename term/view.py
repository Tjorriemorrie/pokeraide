from colorama import Fore, Back, Style
from operator import itemgetter
from os import system
import numpy as np

from es.es import ES
from pe.pe import PE


class View:

    def print(self):
        """Prints data to terminal"""
        if self.waiting_for_new_game or self.button_moved:
            return

        system('cls||clear')

        print(Style.NORMAL + Fore.WHITE + self.site.NAME)
        print('\n')

        print(Style.NORMAL + Fore.YELLOW + 'Pot: {:7d}'.format(self.engine.pot))
        print('\n')

        board = 'Board: {:15}'.format(' '.join(self.engine.board))
        print(Style.NORMAL + Fore.YELLOW + board)
        print('\n')

        # equities = PE.showdown_equities(self.engine)
        for s, p in self.players.items():
            d = self.engine.data[s]

            r = '{:14}'.format(p['name'] or '---')

            if not p['status']:
                print(Style.DIM + Fore.RED + r)
                continue

            r += '{:7}'.format(p['balance'] + d['contrib'])
            r += '{:>8}'.format(' '.join(d['hand']))
            r += '{:3}'.format(s)
            r += '{:4d}%'.format(int((1 - d['strength']) * 100))
            r += '{:>6} '.format(d['matched'] + d['contrib'] or '')
            r += '{:3}'.format('')

            for phase in ['preflop', 'flop', 'turn', 'river']:
                r += '{:5} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d[phase]))
                if self.engine.phase == phase:
                    break

            # if self.engine.phase != self.engine.PHASE_SHOWDOWN and 'in' in d['status']:
            #     d['stats'] = ES.player_stats(self.engine, s)
            #     dist_stats = ES.dist_player_stats(d['stats']['actions'], d['strength'])
            #     # r += '{:>15}'.format(s)
            #     # r += '{:>5}%'.format(int(equities[s] * 100))
            #     r += '{:>22}'.format(dist_stats)

            if 'in' not in d['status']:
                print(Style.DIM + Fore.MAGENTA + r)
                continue

            if s == self.engine.q[0][0]:
                print(Style.NORMAL + Fore.GREEN + r)
                continue

            print(Style.NORMAL + Fore.CYAN + r)

        print('\n')

        if self.engine.data[self.site.HERO]['status'] == 'in':
            print(Style.NORMAL + Fore.WHITE + 'Actions:')

            # if self.mc.rolling_40:
            #     roc = sum(self.mc.rolling_10) / sum(self.mc.rolling_40)
            #     print(Style.NORMAL + Fore.WHITE + 'ROC: {:.0f}'.format(roc * 100))

            actions = [(c.data['action'], c.data['ev'], c.data['traversed'])
                       for c in self.mc.tree.children(self.mc.tree.root)]
            actions.sort(key=itemgetter(1), reverse=True)
            evs = np.array([i[1] for i in actions])
            for action in actions:
                a = '{:=+.1f}'.format((action[1] - np.mean(evs)) / np.std(evs))
                # a = '{:=+6d}'.format(int((1000 * action[1]) // self.engine.bb_amt))
                a += '{:5d} '.format(action[2])
                a += '{}'.format(action[0])
                print(Style.NORMAL + Fore.WHITE + a)

            print('\n')
