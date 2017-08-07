import shelve
from collections import Counter
import logging
import json
import tensorflow as tf
import numpy as np
from os import path

from self_play.agent.random1 import RandomAgent1
from self_play.agent.trpo import TrpoAgent1
from self_play.agent.dqn1 import DqnAgent1
from self_play.agent.ddqn1 import DDqnAgent1
from self_play.agent.vpg1 import VPGAgent1
from self_play.agent.ddqn2 import DDqnAgent2
from self_play.agent.ddqn3 import DDqnAgent3
from self_play.agent.ddqn4 import DDqnAgent4
from self_play.agent.ddqn5 import DDqnAgent5
from self_play.environment import Environment, TournamentFinished

logger = logging.getLogger(__name__)


def main():
    logger.info('creating environment')

    random_agent_1 = RandomAgent1()
    trpo_agent_1 = TrpoAgent1()
    dqn_agent_1 = DqnAgent1()
    ddqn_agent_1 = DDqnAgent1()
    vpg_agent_1 = VPGAgent1()
    ddqn_agent_2 = DDqnAgent2()
    ddqn_agent_3 = DDqnAgent3()
    ddqn_agent_4 = DDqnAgent4()
    ddqn_agent_5 = DDqnAgent5()

    for _ in range(50):
        players = {}
        for s in range(1, 10):
            players[s] = {
                'name': random_agent_1.NAME,
                'balance': 1,
                'status': 1,
                'agent': random_agent_1,
            }
        players[4]['name'] = trpo_agent_1.NAME
        players[4]['agent'] = trpo_agent_1
        players[5]['name'] = dqn_agent_1.NAME
        players[5]['agent'] = dqn_agent_1
        players[6]['name'] = ddqn_agent_1.NAME
        players[6]['agent'] = ddqn_agent_1
        players[7]['name'] = vpg_agent_1.NAME
        players[7]['agent'] = vpg_agent_1
        players[8]['name'] = ddqn_agent_2.NAME
        players[8]['agent'] = ddqn_agent_2
        players[9]['name'] = ddqn_agent_3.NAME
        players[9]['agent'] = ddqn_agent_3
        players[1]['name'] = ddqn_agent_4.NAME
        players[1]['agent'] = ddqn_agent_4
        players[2]['name'] = ddqn_agent_5.NAME
        players[2]['agent'] = ddqn_agent_5

        logger.info('players: {}'.format(json.dumps(players, indent=4, default=str)))

        env = Environment(players)

        try:
            logger.info('Starting training')
            while True:
                obs = env.reset()

                # save actions for all agents till episode terminates
                while True:
                    agent = env.get_agent()
                    # logger.debug('obs? {}'.format(obs))
                    a = agent.get_action(obs)
                    obs_new, r, done, info = env.step(a)
                    agent.train(0)
                    if done:
                        break
                    obs = obs_new

                # observe rewards for all actions
                for s, p in players.items():
                    if p['balance_start']:
                        r = (p['balance'] - p['balance_start']) / env.engine.bb_amt
                        agent.train(r, True)
                    if p['balance'] <= 0:
                        p['status'] = 0

                # input('Game ended')

        except TournamentFinished:
            logging.info('Tournament finished')

    trpo_agent_1.save()
    dqn_agent_1.save()
    ddqn_agent_1.save()
    vpg_agent_1.save()
    ddqn_agent_2.save()
    ddqn_agent_3.save()
    ddqn_agent_4.save()
    ddqn_agent_5.save()
