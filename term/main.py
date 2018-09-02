import click
import cProfile
import logging.config
from es.es import ES

from loggingconfig import LOGGING_CONFIG


@click.group()
@click.option('--debug', is_flag=True)
@click.pass_context
def cli(ctx, debug):
    ctx.obj['debug'] = debug


@click.command()
def rankings():
    click.echo('rankings')
    from pocket_rankings.pocket_rankings import PocketRankings
    PocketRankings.run()
cli.add_command(rankings)


@click.command()
def table():
    click.echo('table')
    from table.table import Table
    table = Table()
    table.run()
cli.add_command(table)


@click.command()
@click.option('--profile', is_flag=True, help='cprofile app for performance')
@click.option('--observe', is_flag=True, help='will not run mc')
@click.option('--replay', is_flag=True, help='will reuse saved images')
@click.argument('site')
@click.argument('seats', type=click.INT)
@click.pass_context
def scrape(ctx, site, seats, replay, observe, profile):
    debug = ctx.obj['debug']
    # change logging based on debug
    if not debug:
        logger = logging.getLogger()
        for hdlr in logger.handlers:
            hdlr.setLevel(logging.INFO)
    from scraper.main import Scraper
    scraper = Scraper(site, seats, debug=debug, replay=replay, observe=observe)
    if profile:
        cProfile.runctx('scraper.run()', globals(), locals(), 'stats.prof')
    else:
        scraper.run()
cli.add_command(scrape)


@click.command()
@click.argument('site')
@click.argument('seats', type=click.INT)
def cards(site, seats):
    from scraper.main import Scraper
    scraper = Scraper(site, seats)
    scraper.cards()
cli.add_command(cards)


@click.command()
@click.argument('site')
@click.argument('seats', type=click.INT)
def chips(site, seats):
    from scraper.main import Scraper
    scraper = Scraper(site, seats)
    scraper.chips()
cli.add_command(chips)


@click.command()
def self_play():
    from self_play.main import main
    main()
cli.add_command(self_play)


@click.command()
def self_play_q():
    from self_play.main import main
    main()
cli.add_command(self_play_q)


@click.command()
@click.option('--rm')
def es(rm):
    if rm:
        ES.delete_player(rm)
    else:
        ES.most_frequent_players()
cli.add_command(es)


@click.command()
@click.argument('site')
@click.argument('seats', type=click.INT)
def board2pocket(site, seats):
    from scraper.main import Scraper
    scraper = Scraper(site, seats)
    scraper.calc_board_to_pocket_ratio()
cli.add_command(board2pocket)

if __name__ == '__main__':
    logging.config.dictConfig(LOGGING_CONFIG)
    cli(obj={})
