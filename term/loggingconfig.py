LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(levelname)-7s - %(name)-8s [%(funcName)s:%(lineno)d] :: %(message)s',
        },
        'short': {
            'format': '%(asctime)s - %(levelname)-7s - %(funcName)-12s :: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'formatter': 'short',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
        'errors': {
            'level': 'ERROR',
            'formatter': 'short',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
        },
        'file_main': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'default',
            'filename': 'log/main.log',
            'maxBytes': 2**20,
        },
        'file_back': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'default',
            'filename': 'log/back.log',
            'maxBytes': 2**20,
        },
        'file_vendor': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'default',
            'filename': 'log/vendor.log',
            'maxBytes': 2**20,
        },
        'file_scraper': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'default',
            'filename': 'log/scraper.log',
            'maxBytes': 2**20,
        },
    },
    'loggers': {
        'scraper': {
            'handlers': ['file_scraper', 'errors'],
            'propagate': False,
        },
        'mc': {
            'handlers': ['file_back', 'errors'],
            'propagate': False,
        },
        'engine': {
            'handlers': ['file_back', 'errors'],
            'propagate': False,
        },
        'urllib3': {
            'handlers': ['file_vendor', 'errors'],
            'propagate': False,
        },
        'elasticsearch': {
            'handlers': ['file_vendor', 'errors'],
            'propagate': False,
        },
        'PIL': {
            'handlers': ['file_vendor', 'errors'],
            'propagate': False,
        },
        'es': {
            'handlers': ['file_back', 'errors'],
            'propagate': False,
        },
        'pe': {
            'handlers': ['file_back', 'errors'],
            'propagate': False,
        },
        'requests': {
            'handlers': ['file_vendor', 'errors'],
            'propagate': False,
        },
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['file_scraper', 'file_main', 'console'],
        'loggers': ['mc']
    },
}
