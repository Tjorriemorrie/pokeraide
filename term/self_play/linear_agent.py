from os import path
from random import choice
import logging
import tensorflow as tf
from tensorflow.contrib.learn import LinearClassifier
from self_play.features import FEATURES as f
from self_play.features import ACTIONS as labels

logger = logging.getLogger(__name__)

label_strings = ['_'.join(l) for l in labels]
logger.info('label_strings: {}'.format(label_strings))
columns = [
    'p1_status', 'p2_status', 'p3_status', 'p4_status',
    'p5_status', 'p6_status', 'p7_status', 'p8_status',
]


class LinearAgent1:
    """Linear agent"""

    NAME = 'linear_agent_1'

    def __init__(self):
        """get actions space"""
        model_path = path.join(path.dirname(path.abspath(__file__)), self.NAME)
        self.e = LinearClassifier(
            feature_columns=[f[c] for c in columns],
            model_dir=model_path,
            n_classes=len(labels),
            label_keys=label_strings
        )

        x = {c: 0 for c in columns}
        y = [0] * len(columns)
        self.e.fit(input_fn=self.input_predict, max_steps=0)
        logger.info('{} fitted'.format(self.NAME))

    def input_predict(self, obs=None):
        x = []
        y = []
        for s in obs or []:
            x.append({c: s[c] for c in columns})
            y.append([0] * len(columns))
        logger.info('x: {}'.format(x))
        logger.info('y: {}'.format(y))
        return x, y

    def get_action(self, s):
        """Get action from observation"""
        a = self.e.predict_classes(input_fn=lambda: self.input_predict([s]))
        logger.debug('{} action = {}'.format(self.NAME, a))
        return a

    def train(self, s, r):
        logger.info('Player {} training with reward {}'.format(self.NAME, r))
        pass
