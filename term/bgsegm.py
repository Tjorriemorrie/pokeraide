import argparse
import logging


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')

    import scraper.bgsegm.main
