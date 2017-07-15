import datetime
import logging
import os
from shutil import copyfile

from scraper.screens.local.screen import Local


class BaseScreen:
    """Base screen for all sites"""

    def __init__(self):
        self.logger = logging.getLogger()

    def take_screen_shot(self, save_local=False):
        """Takes labels screenshot
        Should implement saving it to local"""
        raise NotImplementedError()

    def save_local(self, tmp_img_file):
        """Saves file locally."""
        local_img_file = os.path.join(Local.IMG_PATH, '{}.png'.format(datetime.datetime.utcnow()))
        self.logger.debug('file saved locally to {}'.format(local_img_file))
        copyfile(tmp_img_file, local_img_file)
