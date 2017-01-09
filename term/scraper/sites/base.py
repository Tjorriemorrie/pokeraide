import cv2
from itertools import product
import logging
import numpy as np
import os.path
from PIL import Image
from pytesseract import image_to_string
import re
import ruamel.yaml


class BaseSite:
    """Base scraper for all sites"""

    def __init__(self, screen, seats):
        self.logger = logging.getLogger()
        self.logger.info('initialising site...')

        self.seats = int(seats)
        self.screen = screen

        self.path_images = os.path.join(self.DIR, screen.CODE, 'img')
        self.file_coords = os.path.join(self.DIR, screen.CODE, 'coords.yml')

        self.load_templates()
        self.load_coordinates()

    def load_templates(self):
        """Loads images contents onto instance"""
        self.logger.info('loading cards images...')
        self.img = {}
        self.rgb = {}
        for (dirpath, _, filenames) in os.walk(self.path_images):
            for filename in filenames:
                if filename.startswith('.'):
                    self.logger.info('skipping . file {}'.format(filename))
                    continue
                name = re.sub('[ \W]', '', filename.split('.')[0], re.I).lower()
                path_img = os.path.join(dirpath, filename)
                self.logger.debug('loading {} (from {})'.format(name, path_img))
                img = Image.open(path_img)
                self.img[name] = img
                # self.rgb[name] = cv2.cvtColor(np.array(img), cv2.COLOR_BGR2RGB)

    def load_coordinates(self):
        """Load coordinates"""
        self.logger.info('Loading coords from {}'.format(self.file_coords))
        with open(self.file_coords, 'r') as f:
            self.coords = ruamel.yaml.safe_load(f)
        self.logger.info(self.coords)

    def rotate(self, image, angle):
        """Rotates image"""
        center = tuple(np.array(image.shape[0:2]) / 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(image, rot_mat, image.shape[0:2], flags=cv2.INTER_LINEAR)

    def ocr_text(self, img, lang='eng'):
        """Extracts text from the image as is"""
        text = image_to_string(img, lang, False, '-psm 7')
        self.logger.info('ocr extracted text {}'.format(text))
        return text

    def ocr_number(self, img, lang='eng'):
        """Only extracts numbers from image
        Returns int or None"""
        text = image_to_string(img, lang, False, '-psm 8 digits')
        text_amt = re.sub('\D', '', text)
        text_amt = int(text_amt) if text_amt else None
        self.logger.info('ocr extracted number {} from {}'.format(text_amt, text))
        return text_amt
