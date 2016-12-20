import logging



if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')

    # from pocket_rankings.pocket_rankings import PocketRankings
    # PocketRankings.run()

    from table.table import Table
    table = Table()
    table.run()

