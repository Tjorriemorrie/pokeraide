import datetime
import logging
import os
from PIL import Image

from scraper.screens.base import BaseScreen
from scraper.screens.avd.adb import ADB


class Avd(BaseScreen):
    """android debug screen provider"""
    # todo could start specific site app

    NAME = 'android'
    CODE = 'avd'
    FILE_TMP = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'tmp.png')

    def __init__(self):
        super().__init__()
        # using monekeyrunner is pointless
        # android_home = os.environ['ANDROID_HOME']
        # self.logger.info('loading modules from {}'.format(android_home))
        # sys.path.append(os.path.join(android_home))
        # sys.path.append(os.path.join(android_home, 'tools'))
        # sys.path.append(os.path.join(android_home, 'tools/lib'))
        # from com.android.monkeyrunner import MonkeyRunner
        # from com.android.monkeyrunner import MonkeyImage
        # self.logger.info('imported monkeyrunner')

        # python-adb does not work

        # just use adb directly
        self.adb = ADB()

    def take_screen_shot(self, save_local=False):
        """Takes screen shot of display

        backup? Will copy and timestamp file for backup

        returns an PIL.Image"""
        self.logger.info('taking screen shot to {}'.format(self.FILE_TMP))
        self.adb.screenShot(self.FILE_TMP)

        if save_local:
            self.save_local(self.FILE_TMP)
