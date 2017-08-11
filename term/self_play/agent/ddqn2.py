from self_play.agent.base import BaseAgent
import shelve
from os import path
import logging
from collections import deque
from tensorforce import Configuration
from tensorforce.agents import DQNAgent
from tensorforce.core.networks import layered_network_builder

from self_play.features import ACTIONS as labels

logger = logging.getLogger(__name__)


class DDqnAgent2(BaseAgent):
    """DDqn agent"""

    NAME = 'ddqn_agent_2'
    MODEL_PATH = path.join(path.dirname(path.abspath(__file__)), NAME)
    COLUMNS = [
        'p1_status', 'p2_status', 'p3_status', 'p4_status', 'p5_status',
        'p6_status', 'p7_status', 'p8_status', 'p9_status',
        'p1_balance', 'p2_balance', 'p3_balance', 'p4_balance', 'p5_balance',
        'p6_balance', 'p7_balance', 'p8_balance', 'p9_balance',
        'p1_fold', 'p2_fold', 'p3_fold', 'p4_fold', 'p5_fold',
        'p6_fold', 'p7_fold', 'p8_fold', 'p9_fold',
        'p1_check', 'p2_check', 'p3_check', 'p4_check', 'p5_check',
        'p6_check', 'p7_check', 'p8_check', 'p9_check',
        'p1_call', 'p2_call', 'p3_call', 'p4_call', 'p5_call',
        'p6_call', 'p7_call', 'p8_call', 'p9_call',
        'p1_bet', 'p2_bet', 'p3_bet', 'p4_bet', 'p5_bet',
        'p6_bet', 'p7_bet', 'p8_bet', 'p9_bet',
        'p1_raise', 'p2_raise', 'p3_raise', 'p4_raise', 'p5_raise',
        'p6_raise', 'p7_raise', 'p8_raise', 'p9_raise',
        'p1_allin', 'p2_allin', 'p3_allin', 'p4_allin', 'p5_allin',
        'p6_allin', 'p7_allin', 'p8_allin', 'p9_allin',
        'pot_odds', 'flop', 'turn', 'river', 'vs', 'rvl',
    ]

    def __init__(self):
        self.rewards = []
        self.recent = deque([], maxlen=1000)
        self.config = Configuration(
            tf_summary=path.join(self.MODEL_PATH, 'summary'),
            states=dict(shape=(len(self.COLUMNS,)), type='float'),
            actions=dict(continuous=False, num_actions=len(labels)),
            network=layered_network_builder([
                dict(type='dense', size=32),
            ]),
            target_update_frequency=10,
            double_dqn=True,
            exploration={
                "type": "epsilon_decay",
                "epsilon": 1.0,
                "epsilon_final": 0.1,
                "epsilon_timesteps": 1e6,
            }
        )
        self.agent = DQNAgent(self.config)
        try:
            self.agent.load_model(path.join(self.MODEL_PATH, 'model'))
            logger.info('loaded model from path')
        except: pass
