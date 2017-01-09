import cv2
from itertools import product
import json
import logging
import numpy as np
from operator import mul
import os
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import re
import time

from scraper.sites.base import BaseSite


class Zynga(BaseSite):
    """Zynga poker app on android

    Google nexus 5 avd with changed resolution to 640x960 320dpi
    giving about 750kb screenshots to copy at ~1/sec
    It is the lowest res with > 300dpi
    Needs to be rotated -90

    Cash and tourney seats should be the same. Tables sizes are five and nine"""

    NAME = 'Zynga'
    DIR = os.path.dirname(os.path.realpath(__file__))
    DEBUG = True
    DEBUG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'debug')

    def parse_screen(self, img_file):
        """Parses screen for elements"""
        # load coords
        self.logger.info('loading coords for {} screen with {} seats'.format(self.screen.CODE, self.seats))
        coords = self.coords[self.screen.CODE][self.seats]

        img = self.parse_fullscreen(img_file)

        participants = self.parse_playing(img, coords)

        balances = self.parse_balances(img, coords, participants)

    def parse_fullscreen(self, img_file):
        # load, rotate and gray
        img = Image.open(img_file)
        img = img.transpose(Image.ROTATE_90)
        img = img.convert('L')
        img.save(os.path.join(self.DEBUG_PATH, 'img.png'))
        return img

    def parse_playing(self, img, coords):
        """Parses to see who have cards and is playing
        Template will be blank background"""
        participants = []
        for seat, bb in coords['pockets'].items():
            self.logger.debug('parsing seat {} for pocket within {}'.format(seat, bb))

            # crop pocket
            box = img.crop(bb[0:4])
            box_data = np.array(box)
            self.logger.debug('pocket box {} from {}'.format(box, bb[:4]))
            box.save(os.path.join(self.DEBUG_PATH, 'pocket_{}.png'.format(seat)))

            if seat == 5:
                self.logger.info('auto add hero')
                participants.append(seat)
            else:
                # load template
                tpl = self.img['pocket_{}'.format(seat)]
                tpl_data = np.array(tpl)
                self.logger.debug('loaded pocket template {}'.format(tpl))
                tpl.save(os.path.join(self.DEBUG_PATH, 'pocket_{}_tpl.png'.format(seat)))

                # MSE
                mse = np.sum(box_data.astype(np.float) - tpl_data.astype(np.float)) ** 2
                mse /= mul(*box.size)
                has_cards = mse > bb[-1]
                self.logger.info('{}: {} calculated from MSE = {} (threshold {})'.format(
                    seat, has_cards, int(mse), bb[-1]))
                if has_cards:
                    participants.append(seat)
        self.logger.info('participants {}'.format(participants))
        return participants

    def parse_balances(self, img, coords, participants):
        """parses the balances on the screenshot"""
        balances = {}
        participants = range(1, 10)
        for seat in participants:
            bb = coords['balances'][seat]
            self.logger.debug('seats {} has box {}'.format(seat, bb))

            # crop
            balance_box = img.crop(bb[0:4])
            balance_box.save(os.path.join(self.DEBUG_PATH, 'balance_{}.png'.format(seat)))
            balance_box_data = np.array(balance_box)

            if seat == 5:
                balance_diff = balance_box
            else:
                # subtract bg
                balance_bg = self.img['balance_{}'.format(seat)]
                self.logger.info('balance_bg {}'.format(balance_bg))
                balance_bg.save(os.path.join(self.DEBUG_PATH, 'balance_{}_bg.png'.format(seat)))
                balance_bg_data = np.array(balance_bg)
                balance_bg = Image.fromarray(balance_bg_data)
                mask = balance_box_data.astype(np.float) - balance_bg_data.astype(np.float)
                balance_diff = Image.fromarray(mask.astype(np.uint8))
                balance_diff.save(os.path.join(self.DEBUG_PATH, 'balance_{}_diff.png'.format(seat)))

            # threshold
            balance_box = balance_diff.point(lambda p: 0 if p > bb[-1] else 255)
            balance_box.save(os.path.join(self.DEBUG_PATH, 'balance_{}_point.png'.format(seat)))

            # allin or balance
            if self.ocr_text(balance_box) == 'All In':
                balances[seat] = 0
                # todo set contrib
            else:
                balances[seat] = self.ocr_number(balance_box)
        self.logger.info('balances {}'.format(json.dumps(balances, indent=4, default=str)))
        return balances
