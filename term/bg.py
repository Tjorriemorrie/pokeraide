import logging

from mc.mc import MonteCarlo


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')

    MonteCarlo().watch()
