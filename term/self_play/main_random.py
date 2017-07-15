import logging

from self_play.random_agent import RandomAgent
from self_play.environment import Environment, TournamentFinished

logger = logging.getLogger(__name__)


def main():
    logger.info('creating environment')
    players = {}
    for s in range(1, 10):
        agent = RandomAgent(Environment.ACTIONS, s)
        players[s] = {
            'name': agent.NAME,
            'balance': 1,
            'status': 1,
            'agent': agent,
        }
    env = Environment(players)

    try:
        logger.info('Starting training')
        while True:
            obs = env.reset()
            done = False
            while True:
                agent = env.get_agent()
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
