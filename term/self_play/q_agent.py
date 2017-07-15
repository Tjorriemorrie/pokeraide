from random import choice
import logging
import tensorflow as tf

logger = logging.getLogger(__name__)


class QAgent:
    """Random agent"""

    NAME = 'q_agent'

    def __init__(self, obs, actions, seat):
        """get actions space"""
        self.actions = actions
        self.seat = seat
        self.saver = tf.train.Saver()
        # saver.restore(sess, "/tmp/model.ckpt")

    def get_action(self, s):
        """Get action from observation"""
        a = choice(self.actions)
        logger.debug('random action = {}'.format(a))
        return a

    def train(self, s, r):
        logger.info('Player {} training with reward {}'.format(self.seat, r))
        pass

    def save(self):
        # save_path = saver.save(sess, "/tmp/model.ckpt")
