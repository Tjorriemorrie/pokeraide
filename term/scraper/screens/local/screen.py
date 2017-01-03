import logging
import os
from PIL import Image


class Local:
    """local screen provider"""

    NAME = 'local host'
    CODE = 'local'
    IMG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'img')

    def __init__(self, code):
        self.logger = logging.getLogger()
        self.CODE = code
        self.logger.info('local imitating {}'.format(code))
        self.load_files()

    def load_files(self):
        self.logger.info('loading files')
        self.files = []
        for (dirpath, _, filenames) in os.walk(self.IMG_PATH):
            for filename in filenames:
                if filename.startswith('.'):
                    self.logger.debug('skipping {}'.format(filename))
                    continue
                self.files.append(os.path.join(dirpath, filename))
        self.logger.info('loaded {} files'.format(len(self.files)))

    def take_screen_shot(self):
        """return next file from iterator"""
        img_file = self.files.pop(0)
        self.logger.debug('next img file {}'.format(img_file))
        im = Image.open(img_file)
        self.logger.debug('loaded {} {} {}'.format(im.format, im.size, im.mode))
        return im
