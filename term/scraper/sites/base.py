from collections import Counter
import cv2
from itertools import product
import logging
import numpy as np
from os import scandir, path, walk, makedirs
from PIL import Image
from pytesseract import image_to_string
import re
import ruamel.yaml
from sortedcontainers import SortedDict


logger = logging.getLogger(__name__)


class BaseSite:
    """Base scraper for all sites"""

    def __init__(self, seats, debug=False):
        logger.info('initialising site...')

        self.debug = debug

        self.seats = int(seats)

        self.load_templates()
        self.load_coordinates()
        self.load_cards_map()

        self.ranks = list(range(2, 10)) + ['t', 'j', 'q', 'k', 'labels']
        self.suits = ['s', 'd', 'c', 'h']
        self.cards_names = ['{}{}'.format(r, s) for r, s in product(self.ranks, self.suits)]

    def load_templates(self):
        """Loads images contents onto instance"""
        logger.info('loading cards images...')
        self.img = {}
        for entry in scandir(self.PATH_IMAGES):
            if not entry.is_file() or entry.name.startswith('.'):
                logger.debug('skipping . file {}'.format(entry.name))
                continue
            name = re.sub('[ \W]', '', entry.name.split('.')[0], re.I).lower()
            path_img = path.join(self.PATH_IMAGES, entry.name)
            logger.debug('loading {}'.format(name))
            img = Image.open(path_img)
            self.img[name] = img

    def load_coordinates(self):
        """Load coordinates"""
        logger.info('Loading coords from {}'.format(self.FILE_COORDS))
        with open(self.FILE_COORDS, 'r') as f:
            coords = ruamel.yaml.safe_load(f)
        self.coords = coords[self.seats]
        logger.debug(self.coords)

    def load_cards_map(self):
        """Load cards map"""
        logger.info('Loading cards map from {}'.format(self.FILE_CARDS_MAP))
        with open(self.FILE_CARDS_MAP, 'r') as f:
            cards_map = ruamel.yaml.safe_load(f)
        self.cards_map = cards_map
        logger.debug('Cards map: {}'.format(cards_map))

    def rotate(self, image, angle):
        """Rotates image"""
        center = tuple(np.array(image.shape[0:2]) / 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(image, rot_mat, image.shape[0:2], flags=cv2.INTER_LINEAR)

    def ocr_text(self, img, lang='Lucida'):
        """Extracts text from the image as is"""
        text = image_to_string(img, lang, False, '-psm 7')
        logger.info('ocr extracted text {}'.format(text))
        return text

    def ocr_number(self, img, lang='Lucida'):
        """Only extracts numbers from image
        Returns int or None"""
        text = image_to_string(img, lang, False, '-psm 8 digits')
        text_amt = re.sub('\D', '', text)
        text_amt = int(text_amt) if text_amt else None
        logger.info('ocr extracted number {} from {}'.format(text_amt, text))
        return text_amt

    def mse_from_counts(self, tpl, comp):
        """Quickly matches two images. Useful if the exact
        positioning is labels bit off."""
        if tpl.shape != comp.shape:
            logger.warn('template {} and comparison {} does not have the same shape!'.format(tpl.shape, comp.shape))
            if self.debug:
                input('$ did you forget to copy over img?')
        tpl_cnts = Counter(tpl.flatten())
        comp_cnts = Counter(comp.flatten())
        diffs = [(cnt - comp_cnts[el]) ** 2 for el, cnt in tpl_cnts.items()]
        mse = sum(diffs) / len(tpl_cnts)
        logger.debug('MSE {} over {} pixels ({})'.format(int(mse), len(tpl_cnts), tpl_cnts.most_common(3)))
        return mse
    
    def find_coeffs(self, pa, pb):
        logger.info('perspective input original {}'.format(pa))
        logger.info('perspective input final {}'.format(pb))
        matrix = []
        for p1, p2 in zip(pa, pb):
            matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
            matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])

        A = np.matrix(matrix, dtype=np.float)
        B = np.array(pb).reshape(8)

        res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
        coeffs = np.array(res).reshape(8)
        logger.info('perspective coeffs {}'.format(coeffs))
        return coeffs

    def match_template(self, img, template, threshold, multiple=False):
        """Matches labels template
        Converts it to grayscale
        Checks against provided threshold if matched.
        Return None when below threshold"""
        template = template.convert('L')
        res = cv2.matchTemplate(np.array(img), np.array(template), cv2.TM_CCOEFF_NORMED)
        if not multiple:
            mml = cv2.minMaxLoc(res)
            logger.debug('Min Max Loc: {}'.format(mml))
            loc_found = mml[1] >= threshold
            logger.info('template match found: {} @ {} [{:.2f} >= {:.2f}]'.format(loc_found, mml[-1], mml[1], threshold))
            return loc_found and list(mml[-1])
        else:
            locs = np.where(res >= threshold)
            locs = [list(l) for l in zip(*locs[::-1])]
            logger.info('template match found {:d} with threshold {:.2f}'.format(len(locs), threshold))
            return list(map(list, locs))

    def generate_cards(self):
        """Generate cards for site"""
        card_shape = self.coords['card_shape']
        cards_shape = (card_shape[0] * 13, card_shape[1] * 5)
        logger.info('Generating cards on {} sheet'.format(cards_shape))

        img = Image.new('L', cards_shape)
        x = 0
        y = 0
        cards_map = {}

        # add deck
        for rank in self.ranks:
            y = 0
            for suit in self.suits:
                card_name = '{}{}'.format(rank, suit)
                logger.debug('adding card {} at {}, {}'.format(card_name, x, y))
                img.paste(self.img[card_name], (x, y))
                cards_map['{},{}'.format(x, y)] = card_name
                y += card_shape[1]
            x += card_shape[0]

        # add other
        for b in ['board']:
            x = 0
            y = card_shape[1] * 4
            for i in range(1, 6):
                card_name = 'board_{}'.format(i)
                logger.debug('adding card {} at {}, {}'.format(card_name, x, y))
                img.paste(self.img[card_name], (x, y))
                cards_map['{},{}'.format(x, y)] = card_name
                x += card_shape[0]

        img.save(path.join(self.PWD, 'img', 'cards_map.png'))

        with open(self.FILE_CARDS_MAP, 'w') as f:
            cards_map = ruamel.yaml.dump(cards_map, f)

    def generate_chips(self):
        """Generate chips for site"""
        logger.info('Generating chips: {}'.format(self.PATH_CHIPS))

        for root, dirs, files in walk(self.PATH_CHIPS):
            logger.info('root: {}'.format(root))
            logger.info('dirs: {}'.format(dirs))
            dir = root.lstrip(self.PATH_CHIPS)
            logger.info('directory: {}'.format(dir))
            fake_dir = path.join(self.PWD, 'chips_fake', dir)
            for file in files:
                logger.info('file: {}'.format(file))
                if file.endswith('png'):
                    img = Image.open(path.join(root, file))
                    data = img.getdata()
                    new_data = []
                    for px in data:
                        # logger.debug('px: {}'.format(px))
                        new_data.append((px[0], px[1], px[2], 0))
                    img.putdata(new_data)
                    try:
                        img.save(path.join(fake_dir, file))
                    except FileNotFoundError:
                        makedirs(fake_dir)
                        img.save(path.join(fake_dir, file))

    def match_cards(self, img, threshold):
        """Parses img provided for any card in the deck"""
        logger.info('Matching cards in img')
        cards = {}
        for card_name in self.cards_names:
            # load template
            tpl = self.img[card_name]
            loc = self.match_template(img, tpl, threshold)
            if loc:
                cards[card_name] = loc
                logger.debug('Found card {} at {}'.format(card_name, loc))
        logger.debug('Found {} cards'.format(len(cards)))
        return cards


class SiteException(Exception):
    pass

class NoDealerButtonError(Exception):
    pass

class PocketError(Exception):
    pass

class BalancesError(Exception):
    pass

class ContribError(Exception):
    pass

class ThinkingPlayerError(Exception):
    pass

class BoardError(Exception):
    pass
