from collections import deque
from os import path
from random import choice
import logging
from self_play.features import FEATURES as f
from self_play.features import ACTIONS as labels
import numpy as np
from tensorforce import Configuration
from tensorforce.agents.random_agent import RandomAgent
from self_play.agent.base import BaseAgent

logger = logging.getLogger(__name__)



class RandomAgent1(BaseAgent):
    """Random agent"""

    NAME = 'random_agent_1'
    MODEL_PATH = path.join(path.dirname(path.abspath(__file__)), NAME)
    COLUMNS = [
        'p1_status', 'p2_status', 'p3_status', 'p4_status',
        'p5_status', 'p6_status', 'p7_status', 'p8_status',
        'p9_status',
    ]

    def __init__(self):
        self.rewards = []
        self.recent = deque([], maxlen=1000)
        self.config = Configuration(
            states=dict(shape=(len(self.COLUMNS),), type='float'),
            actions=dict(continuous=False, num_actions=len(labels)),
        )
        self.agent = RandomAgent(self.config)
