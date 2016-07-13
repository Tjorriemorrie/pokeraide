class Prod(object):
    DEBUG = False
    TESTING = False
    SECRET_KEY = '3tJhmR0XFbSOUG02Wpp7'
    CSRF_ENABLED = True
    CSRF_SESSION_LKEY = 'e8uXRmxo701QarZiXxGf'

class Dev(Prod):
    DEBUG = True
