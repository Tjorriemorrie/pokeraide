import click
import logging.config

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
@click.option('--observe', is_flag=True)
@click.option('--replay', is_flag=True)
@click.argument('site')
@click.argument('seats', type=click.INT)
@click.pass_context
def scrape(ctx, site, seats, replay, observe):
    from scraper.main import Scraper
    scraper = Scraper(site, seats, debug=ctx.obj['debug'], replay=replay, observe=observe)
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


if __name__ == '__main__':
    logging.config.dictConfig(LOGGING_CONFIG)
    # for _ in ('boto', 'elasticsearch', 'urllib3', 'PIL', 'requests'):
    #     logging.getLogger(_).setLevel(logging.CRITICAL)
    # for key in logging.Logger.manager.loggerDict:
    #     print(key)

    cli(obj={})
