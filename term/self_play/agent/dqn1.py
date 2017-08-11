import shelve
from os import path
from self_play.agent.base import BaseAgent
import logging
from collections import deque
from tensorforce import Configuration
from tensorforce.agents import DQNAgent
from tensorforce.core.networks import layered_network_builder

from self_play.features import ACTIONS as labels

logger = logging.getLogger(__name__)


class DqnAgent1(BaseAgent):
    """Dqn agent"""

    NAME = 'dqn_agent_1'
    MODEL_PATH = path.join(path.dirname(path.abspath(__file__)), NAME)
    COLUMNS = [
        'p1_status', 'p2_status', 'p3_status', 'p4_status', 'p5_status',
        'p6_status', 'p7_status', 'p8_status', 'p9_status',
        'p1_balance', 'p2_balance', 'p3_balance', 'p4_balance', 'p5_balance',
        'p6_balance', 'p7_balance', 'p8_balance', 'p9_balance',
    ]

    def __init__(self):
        self.rewards = []
        self.recent = deque([], maxlen=1000)
        self.config = Configuration(
            tf_summary=path.join(self.MODEL_PATH, 'summary'),
            states=dict(shape=(len(self.COLUMNS,)), type='float'),
            actions=dict(continuous=False, num_actions=len(labels)),
            network=layered_network_builder([]),
            target_update_frequency=10,
            double_dqn=False,
        )
        self.agent = DQNAgent(self.config)
        try:
            self.agent.load_model(path.join(self.MODEL_PATH, 'model'))
            logger.info('loaded model from path')
        except: pass
