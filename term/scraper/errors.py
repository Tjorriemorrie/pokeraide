class SiteParsingError(Exception):
    """Problems with the site scraper"""


class PlayerBalanceIsTextError(SiteParsingError):
    """player balance is replaced with text"""


class NoPotInBalancesError(SiteParsingError):
    """no pot scraped in balance"""
