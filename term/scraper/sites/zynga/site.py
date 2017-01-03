from itertools import product
import logging
import os
from PIL import Image, ImageFilter, ImageEnhance
from pytesseract import image_to_string
import time

from scraper.sites.base import BaseSite


class Zynga(BaseSite):
    """Zynga poker app on android

    Google nexus 5 avd with changed resolution to 640x960 320dpi
    giving about 750kb screenshots to copy at ~1/sec
    Needs to be rotated -90

    Cash and tourney seats should be the same. Tables sizes are five and nine"""

    NAME = 'Zynga'
    DIR = os.path.dirname(os.path.realpath(__file__))
    DEBUG = True
    DEBUG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'debug')

    def parse_screen(self, screen):
        """Parses screen for elements"""
        # load coords
        self.logger.info('loading coords for {} screen with {} seats'.format(self.screen.CODE, self.seats))
        coords = self.coords[self.screen.CODE][self.seats]

        # prepare image
        img = screen.transpose(Image.ROTATE_90)
        if self.DEBUG:
            img.save(os.path.join(self.DEBUG_PATH, 'img_rotated.png'))

        # black and white image
        img = img.convert('L')
        if self.DEBUG:
            img.save(os.path.join(self.DEBUG_PATH, 'img_bw.png'))

        # # min filter
        # img = img.filter(ImageFilter.MinFilter(size=3))
        # if self.DEBUG:
        #     img.save(os.path.join(self.DEBUG_PATH, 'img_min_filter.png'))

        # Contrast
        img = ImageEnhance.Contrast(img).enhance(4)
        if self.DEBUG:
            img.save(os.path.join(self.DEBUG_PATH, 'img_contrast.png'))

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        if self.DEBUG:
            img.save(os.path.join(self.DEBUG_PATH, 'img_sharpen.png'))

        # unsharp mask
        # img = img.filter(ImageFilter.UnsharpMask(radius=3, percent=150, threshold=3))
        # if self.DEBUG:
        #     img.save(os.path.join(self.DEBUG_PATH, 'img_unsharp_mask.png'))

        # img = img.filter(ImageFilter.ModeFilter(size=3))
        # if self.DEBUG:
        #     img.save(os.path.join(self.DEBUG_PATH, 'img_mode_filter.png'))

        # median filter
        # img = img.filter(ImageFilter.MedianFilter(size=1))
        # if self.DEBUG:
        #     img.save(os.path.join(self.DEBUG_PATH, 'img_median_filter.png'))

        # max filter
        # img = img.filter(ImageFilter.MaxFilter(size=3))
        # if self.DEBUG:
        #     img.save(os.path.join(self.DEBUG_PATH, 'img_max_filter.png'))

        # filter image detail
        # radii = [0, 2, 4, 6]
        # percent = [100, 200, 300]
        # threshold = [0]
        # for p, r, t in product(percent, radii, threshold):
        #     img = img.filter(ImageFilter.UnsharpMask(radius=r, percent=p, threshold=t))
        #     if self.DEBUG:
        #         img.save(os.path.join(self.DEBUG_PATH, 'img_unsharp_mask_{}_{}_{}.png'.format(r, p, t)))

        # # filter image detail
        # img = img.filter(ImageFilter.SHARPEN)
        # if self.DEBUG:
        #     img.save(os.path.join(self.DEBUG_PATH, 'img_sharpen.png'))
        # for f in ['BLUR', 'CONTOUR', 'DETAIL', 'EDGE_ENHANCE', 'EDGE_ENHANCE_MORE', 'EMBOSS', 'FIND_EDGES', 'SMOOTH', 'SMOOTH_MORE', 'SHARPEN']:
        #     time_start = time.time()
        #     img_tmp = img.copy().filter(getattr(ImageFilter, f))
        #     if self.DEBUG:
        #         img_tmp.save(os.path.join(self.DEBUG_PATH, 'img_{}.png'.format(f)))
        #     self.logger.debug('{} took {}'.format(f, time.time() - time_start))
        #
        # for f in ['MedianFilter', 'MinFilter', 'MaxFilter', 'ModeFilter']:
        #     time_start = time.time()
        #     img_tmp = img.copy().filter(getattr(ImageFilter, f))
        #     if self.DEBUG:
        #         img_tmp.save(os.path.join(self.DEBUG_PATH, 'img_{}.png'.format(f)))
        #     self.logger.debug('{} took {}'.format(f, time.time() - time_start))
        #
        # for f in ['Color', 'Contrast', 'Brightness', 'Sharpness']:
        #     enhancer = getattr(ImageEnhance, f)(img.copy())
        #     for i in [0, 0.5, 1, 1.5, 2]:
        #         time_start = time.time()
        #         img_tmp = enhancer.enhance(i)
        #         if self.DEBUG:
        #             img_tmp.save(os.path.join(self.DEBUG_PATH, 'img_{}_{}.png'.format(f, i)))
        #         self.logger.debug('{}_{} took {}'.format(f, i, time.time() - time_start))

        # parse balances
        for seat, bb in coords['balances'].items():
            self.logger.debug('seats {} has box {}'.format(seat, bb))
            balance_box = img.crop(bb)
            if self.DEBUG:
                balance_box.save(os.path.join(self.DEBUG_PATH, 'balance_{}.png'.format(seat)))
            text = image_to_string(balance_box, None, False, '-psm 8 digits')
            self.logger.info('balance of {} = {}'.format(seat, text))
