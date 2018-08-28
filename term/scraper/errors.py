class SiteParsingError(Exception):
    """Problems with the site scraper"""


class NoPotInBalancesError(SiteParsingError):
    """no pot scraped in balance"""
