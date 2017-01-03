import argparse
import logging

from scraper.main import Scraper


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')

    parser = argparse.ArgumentParser(description='play live on a site')
    parser.add_argument('site', type=str, help='name of site')
    parser.add_argument('screen', type=str, help='name of screen')

    args = parser.parse_args()
    site = args.site
    screen = args.screen

    Scraper(site, screen).run()
