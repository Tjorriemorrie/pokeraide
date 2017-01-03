# import cv2
# from itertools import product
import logging
# import numpy as np
# from PIL import Image  #, ImageFilter, ImageGrab
import os
# import re
# import ruamel.yaml

# import sys
# import time
# import pytesseract
# from configobj import ConfigObj

# from decisionmaker.genetic_algorithm import GeneticAlgorithm
# from tools.vbox_manager import VirtualBoxController
from scraper.screens.local.screen import Local


class BaseScreen:
    """Base screen for all sites"""

    def __init__(self):
        self.logger = logging.getLogger()

    def take_screen_shot(self, save_local=False):
        """Takes a screenshot
        Should implement saving it to local"""
        raise NotImplementedError()

    def save_local(self, tmp_img_file):
        """Saves file locally."""
        local_img_file = os.path.join(Local.IMG_PATH, '{}.png'.format(datetime.datetime.utcnow()))
        self.logger.debug('file saved locally to {}'.format(local_img_file))
        copyfile(tmp_img_file, local_img_file)
