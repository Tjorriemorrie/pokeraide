from random import choice
import logging
from self_play.features import ACTIONS as labels

logger = logging.getLogger(__name__)


class RandomAgent:
    """Random agent"""

    NAME = 'random_agent'

    def get_action(self, s):
        """Get action from observation"""
        a = choice(labels)
        logger.debug('{} action = {}'.format(self.NAME, a))
        return a

    def train(self, s, r):
        logger.info('Player {} training with reward {}'.format(self.NAME, r))
        pass
