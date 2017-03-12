from collections import Counter
import cv2
from itertools import product
import logging
import numpy as np
import os.path
from PIL import Image
from pytesseract import image_to_string
import re
import ruamel.yaml
from sortedcontainers import SortedDict


class BaseSite:
    """Base scraper for all sites"""

    def __init__(self, seats, debug=False):
        self.logger = logging.getLogger()
        self.logger.info('initialising site...')

        self.debug = debug

        self.seats = int(seats)

        self.load_templates()
        self.load_coordinates()

        ranks = list(range(2, 10)) + ['t', 'j', 'q', 'k', 'a']
        suits = ['s', 'd', 'c', 'h']
        self.cards_names = ['{}{}'.format(r, s) for r, s in product(ranks, suits)]

    def load_templates(self):
        """Loads images contents onto instance"""
        self.logger.info('loading cards images...')
        self.img = {}
        for entry in os.scandir(self.PATH_IMAGES):
            if not entry.is_file() or entry.name.startswith('.'):
                self.logger.debug('skipping . file {}'.format(entry.name))
                continue
            name = re.sub('[ \W]', '', entry.name.split('.')[0], re.I).lower()
            path_img = os.path.join(self.PATH_IMAGES, entry.name)
            self.logger.debug('loading {}'.format(name))
            img = Image.open(path_img)
            self.img[name] = img

    def load_coordinates(self):
        """Load coordinates"""
        self.logger.info('Loading coords from {}'.format(self.FILE_COORDS))
        with open(self.FILE_COORDS, 'r') as f:
            coords = ruamel.yaml.safe_load(f)
        self.coords = coords[self.seats]
        self.logger.debug(self.coords)

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

    def mse_from_counts(self, tpl, comp):
        """Quickly matches two images. Useful if the exact
        positioning is a bit off."""
        if tpl.shape != comp.shape:
            self.logger.warn('template {} and comparison {} does not have the same shape!'.format(tpl.shape, comp.shape))
        tpl_cnts = Counter(tpl.flatten())
        comp_cnts = Counter(comp.flatten())
        diffs = [(cnt - comp_cnts[el]) ** 2 for el, cnt in tpl_cnts.items()]
        mse = sum(diffs) / len(tpl_cnts)
        self.logger.debug('MSE {} over {} pixels ({})'.format(int(mse), len(tpl_cnts), tpl_cnts.most_common(3)))
        return mse
    
    def find_coeffs(self, pa, pb):
        self.logger.info('perspective input original {}'.format(pa))
        self.logger.info('perspective input final {}'.format(pb))
        matrix = []
        for p1, p2 in zip(pa, pb):
            matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
            matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])

        A = np.matrix(matrix, dtype=np.float)
        B = np.array(pb).reshape(8)

        res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
        coeffs = np.array(res).reshape(8)
        self.logger.info('perspective coeffs {}'.format(coeffs))
        return coeffs

    def match_card(self, img, threshold=None):
        self.logger.info('identifying card')
        img_data = np.array(img)

        mse_cards = SortedDict()
        for card_name in self.cards_names:
            # load template
            tpl = self.img[card_name]
            tpl_data = np.array(tpl)
            # tpl.save(os.path.join(self.DEBUG_PATH, 'card_{}_tpl.png'.format(card_name)))

            # mse
            mse = self.mse_from_counts(tpl_data, img_data)
            mse_cards[mse] = card_name
            self.logger.debug('card {} has mse {}'.format(card_name, mse))

        cards_same_mse = len(self.cards_names) - len(mse_cards)
        if cards_same_mse:
            self.logger.warn('{} cards with same mse!'.format(cards_same_mse))

        if not threshold:
            return mse_cards

        mse_best = mse_cards.iloc[0]
        card = mse_cards[mse_best]
        self.logger.info('highest mse = {} with {}'.format(card, mse_best))
        if mse_best < threshold:
            return card

        self.logger.info('mse not above threshold of {}'.format(threshold))
        return None

    def match_template(self, img, template, threshold):
        """Matches a template
        Converts it to grayscale
        Checks against provided threshold if matched.
        Return None when below threshold"""
        template = template.convert('L')
        res = cv2.matchTemplate(np.array(img), np.array(template), cv2.TM_CCOEFF_NORMED)
        mml = cv2.minMaxLoc(res)
        max_loc = mml[1] >= threshold and mml[-1]
        self.logger.info('template match found: {} [{:.2f} >= {:.2f}]'.format(max_loc, mml[1], threshold))
        return max_loc


class SiteException(Exception):
    pass

class NoDealerButtonError(Exception):
    pass
