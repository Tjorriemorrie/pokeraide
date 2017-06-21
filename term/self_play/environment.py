import logging
from itertools import product
from collections import deque, Counter
from random import shuffle
from es.es import ES
from pe.pe import PE
import numpy as np

from engine.engine import Engine

logger = logging.getLogger(__name__)


class Environment:
    """Environment"""

    ACTIONS = [
        ('fold',),
        ('check', 'fold'),
        ('check', 'call'),
        ('bet', 'fold'),
        ('bet', 'raise'),
        ('allin',),
    ]

    STRUCTURE = [
        (1500, 3000),
        (1000, 200),
        (500, 1000),
        (300, 600),
        (200, 400),
        (100, 200),
        (75, 150),
        (50, 100),
        (25, 50),
        (15, 30),
        (10, 20),
    ]

    def __init__(self, players):
        self.observation = np.zeros(10)
        logger.debug('observation space {}'.format(self.observation.shape))
        self.actions = np.arange(len(self.ACTIONS))
        logger.debug('action space {}'.format(self.actions.shape))
        self.i = 0
        self.blinds = deque(self.STRUCTURE)
        self.button = 0
        self.sb = None
        self.bb = None
        for s, player in players.items():
            player['balance'] = 1500
            player['status'] = 1
        self.players = players

        ranks = list(range(2, 10)) + ['t', 'j', 'q', 'k', 'a']
        suits = ['s', 'd', 'c', 'h']
        self.cards = ['{}{}'.format(r, s) for r, s in product(ranks, suits)]
        self.board_map = {v: k for k, v in Engine.BOARD_MAP.items()}

    def reset(self):
        """Increment game number and check blinds"""
        logger.info('resetting environment')

        shuffle(self.cards)
        self.deck = deque(self.cards)
        logger.debug('random deck created {}'.format(list(self.deck)[:10]))

        status_in = sum(p['status'] for p in self.players.values())
        if status_in < 2:
            raise TournamentFinished()

        if not self.i % 20 and len(self.blinds) > 1:
            self.sb, self.bb = self.blinds.pop()
            logger.info('SB: {}'.format(self.sb))
            logger.info('BB: {}'.format(self.bb))

        self.i += 1
        logger.info('Game number: {}'.format(self.i))

        while True:
            self.button += 1
            if self.button > len(self.players):
                self.button = 1
            if self.players[self.button]['status']:
                break

        logger.debug('creating engine')
        self.engine = Engine('pokerstars', self.button, self.players, self.sb, self.bb)

        self.engine.available_actions()
        obs = []

        logger.debug('starting balances for reward')
        for s, player in self.players.items():
            player['balance_prev'] = player['balance']
            # give starting hands
            if player['status']:
                card_1 = self.deck.popleft()
                card_2 = self.deck.popleft()
                player['hand'] = [card_1, card_2]
                logger.info('Player {} hand {}'.format(s, player['hand']))

        return obs

    def get_agent(self):
        """Get action from agent currently to play"""
        return self.players[self.engine.s]['agent']

    def step(self, action_pair):
        """
        observation (object): an environment-specific object representing your observation of the environment. For example, pixel data from a camera, joint angles and joint velocities of a robot, or the board state in a board game.
        reward (float): amount of reward achieved by the previous action. The scale varies between environments, but the goal is always to increase your total reward.
        done (boolean): whether it's time to reset the environment again. Most (but not all) tasks are divided up into well-defined episodes, and done being True indicates the episode has terminated. (For example, perhaps the pole tipped too far, or you lost your last life.)
        info (dict): diagnostic information useful for debugging. It can sometimes be useful for learning (for example, it might contain the raw probabilities behind the environment's last state change). However, official evaluations of your agent are not allowed to use this for learning.
        """
        seat = self.engine.s
        a = None
        available_actions = self.engine.available_actions()
        if not available_actions:
            if not self.engine.winner:
                raise EnvironmentError('No actions but no winner?')
            logger.info('No more actions, winner already set')
            logger.info('Winner is {}'.format(self.engine.winner))
            return None, self.engine.pot, True, {'winners': self.engine.winner}

        for action in action_pair:
            if action in available_actions:
                a = action[0]
                break
        logger.info('Player {} do {}'.format(seat, a))

        if not a:
            logger.info('No more actions available')
            if not self.processed_gg(available_actions):
                raise EnvironmentError('Action ({}) not in available {}'.format(action_pair, available_actions))
            return None, self.engine.pot, True, {'winners': self.engine.winner}

        cmd = [a]
        if a == 'r':
            cmd.append(self.engine.contrib_short(seat))
        elif a == 'b':
            cmd.append(self.engine.pot)

        logger.debug('sending cmd {}'.format(cmd))
        self.engine.do(cmd)

        o = self.get_observation()

        current_balance = self.engine.current_balance(seat)
        r = current_balance - self.players[seat]['balance_prev']
        logger.debug('reward = {} <= {} - {}'.format(r, self.players[seat]['balance'], self.players[seat]['balance_prev']))
        self.players[seat]['balance_prev'] = current_balance

        new_actions = self.engine.available_actions()
        done = self.engine.phase == self.engine.PHASE_GG
        logger.debug('done? {}'.format(done))

        # deal board?
        try:
            board_req = self.board_map[self.engine.phase]
        except:
            pass
        else:
            while len(self.engine.board) < board_req:
                self.engine.board.append(self.deck.popleft())
                logger.info('Board {}'.format(self.engine.board))

        info = {}

        return o, r, done, info

    def processed_gg(self, available_actions):
        if 'gg' in available_actions:
            equities = PE.showdown_equities(self.engine)
            logger.debug('equities: {}'.format(equities))
            for s, equity in equities.items():
                if equity == max(equities.values()):
                    winner = s
                    break
            self.engine.do(['gg', winner])
            logger.info('Winner is {}'.format(s))
            ES.save_game(self.players, self.engine.data, self.engine.site_name, self.engine.vs)
            logger.info('game saved')
            return True
        return False

    def get_observation(self):
        """Get observation of game state"""
        o = []

        seat = self.engine.s

        # players
        q = deque(range(1, 10))
        while q[0] != seat:
            q.rotate(-1)
        logger.debug('seat {} now at front of queue'.format(seat))

        self.engine.data[seat]['hand'] = self.players[seat]['hand']
        equities = PE.showdown_equities(self.engine)
        for s, p in self.players.items():
            o.append(equities.get(s, 0))
        self.engine.data[seat]['hand'] = ['__', '__']

        balance_sum = 9 * 1500
        while len(q):
            s = q.popleft()
            p = self.players[s]
            d = self.engine.data[s]
            player_inputs = [0] * 8
            if 'in' in d['status']:
                player_inputs[0] = 1
                player_inputs[1] = round(p['balance'] / balance_sum, 2)
                # stats
                stats = ES.player_stats(self.engine, s)
                player_inputs[2] = stats.get('f', 0)
                player_inputs[3] = stats.get('k', 0)
                player_inputs[4] = stats.get('c', 0)
                player_inputs[5] = stats.get('b', 0)
                player_inputs[6] = stats.get('r', 0)
                player_inputs[7] = stats.get('a', 0)
            o.extend(player_inputs)

        # game
        # add phase
        if self.engine.phase in [self.engine.PHASE_RIVER, self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG]:
            o.extend([1, 1, 1])
        elif self.engine.phase == self.engine.PHASE_TURN:
            o.extend([1, 1, 0])
        elif self.engine.phase == self.engine.PHASE_FLOP:
            o.extend([1, 0, 0])
        else:
            o.extend([0, 0, 0])

        # pot odds
        o.append(self.engine.contrib_short(seat) / self.engine.current_pot)

        # board
        # suited
        board_cards = len(self.engine.board)
        if board_cards:
            board_inputs = []
            suits = Counter([c[1] for c in self.engine.board])
            highest_suited = suits.most_common()[0][1]
            for l in range(2, 6):
                board_inputs.append(1 if highest_suited >= l else 0)
        else:
            board_inputs = [0] * 4
        o.extend(board_inputs)

        # high
        highs = sum(c[0] in ['j', 'k', 'q', 'a'] for c in self.engine.board)
        if board_cards:
            board_inputs = []
            for l in range(1, 6):
                board_inputs.append(1 if highs >= l else 0)
        else:
            board_inputs = [0] * 5

        logger.debug('new observation = {}'.format(o))
        return o

class TournamentFinished(BaseException):
    """The tournament finished"""




















