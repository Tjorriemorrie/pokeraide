import logging

def getLogger(name):
    # logging.basicConfig(level=logging.DEBUG, format='%(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')
    logger = logging.getLogger(name)
    return logger

for _ in ("boto", "elasticsearch", "urllib3"):
    logging.getLogger(_).setLevel(logging.CRITICAL)
