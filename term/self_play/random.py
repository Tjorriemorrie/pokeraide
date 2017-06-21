from random import choice
import logging

logger = logging.getLogger(__name__)


class RandomAgent:
    """Random agent"""

    NAME = 'random_agent'

    def __init__(self, actions, seat):
        """get actions space"""
        self.actions = actions
        self.seat = seat

    def get_action(self, s):
        """Get action from observation"""
        a = choice(self.actions)
        logger.debug('random action = {}'.format(a))
        return a

    def train(self, s, r):
        logger.info('Player {} training with reward {}'.format(self.seat, r))
        pass
