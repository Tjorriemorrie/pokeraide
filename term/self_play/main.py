import logging
import json
import tensorflow as tf
import numpy as np

from self_play.random_agent import RandomAgent
from self_play.linear_agent import LinearAgent1
from self_play.environment import Environment, TournamentFinished

logger = logging.getLogger(__name__)


def main():
    logger.info('creating environment')

    random_agent = RandomAgent()
    linear_agent_1 = LinearAgent1()

    players = {}
    for s in range(1, 10):
        players[s] = {
            'name': random_agent.NAME,
            'balance': 1,
            'status': 1,
            'agent': random_agent,
        }
    players[1]['name'] = LinearAgent1.NAME
    players[1]['agent'] = linear_agent_1
    logger.info('players: {}'.format(json.dumps(players, indent=4, default=str)))

    env = Environment(players)

    try:
        logger.info('Starting training')
        while True:
            obs = env.reset()
            while True:
                agent = env.get_agent()
                logger.debug('obs? {}'.format(obs))
                a = agent.get_action(obs)
                obs_new, r, done, info = env.step(a)
                if done:
                    break
                agent.train(obs, r)
                obs = obs_new
            # train winner for last time
            # logger.info('players {}'.format(players))
            # logger.info('info {}'.format(info))
            for winner in info['winners']:
                agent_winner = players[winner]['agent']
                agent_winner.train(obs, r)
            input('Game ended')


    except TournamentFinished:
        logging.info('Tournament finished')
