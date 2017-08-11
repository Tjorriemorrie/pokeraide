import shelve
from os import path
import logging
from collections import deque
from tensorforce import Configuration
from tensorforce.agents import DQNAgent
from tensorforce.core.networks import layered_network_builder

from self_play.features import ACTIONS as labels

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base agent"""

    def get_action(self, obs):
        """Get action from observation"""
        x = [obs[c] for c in self.COLUMNS]
        # logger.debug('{} state [{}] = {}'.format(self.NAME, len(x), x))
        a = self.agent.act(x)
        label = labels[a]
        # logger.debug('{} action = [{}] {}'.format(self.NAME, a, label))
        return label

    def train(self, r, terminal=False):
        if r:
            if terminal:
                logger.debug('Player {} training with reward {}'.format(self.NAME, r))
            self.rewards.append(r)
            self.recent.append(r)
            if not len(self.rewards) % 100:
                avg = sum(self.recent) / len(self.recent) * 1000000
                logger.info('{} avg reward {:2f}'.format(self.NAME, avg))
        self.agent.observe(r, terminal)

    def reset(self):
        """Reset agent after """
        self.agent.reset()

    def save(self):
        """Save model"""
        self.agent.save_model(path.join(self.MODEL_PATH, 'model'))
        logger.info('{} model saved'.format(self.NAME))

        with shelve.open(path.join(self.MODEL_PATH, 'rewards.shlv'), writeback=True) as shlv:
            if 'rewards' not in shlv:
                shlv['rewards'] = []
            shlv['rewards'].extend(self.rewards)
            logger.info('{} shlv saved {} rewards'.format(self.NAME, len(shlv['rewards'])))

        # print recent
        avg = sum(self.recent) / len(self.recent) * 1000000
        logger.info('{} avg reward {:2f}'.format(self.NAME, avg))
