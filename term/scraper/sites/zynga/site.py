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

        # dealers = self.parse_dealer(img, coords)
        # participants = self.parse_playing(img, coords)
        # balances = self.parse_balances(img, coords, participants)
        # board = self.parse_board(img, coords)
        # hero_cards = self.parse_cards_hero(img, coords)
        foes_cards = self.parse_cards_foes(img, coords)

    def parse_fullscreen(self, img_file):
        # load, rotate and gray
        img = Image.open(img_file)
        img = img.transpose(Image.ROTATE_90)
        img = img.convert('L')
        img.save(os.path.join(self.DEBUG_PATH, 'img.png'))
        return img

    def parse_dealer(self, img, coords):
        """Parses to see who is the dealer
        Template will be image with button
        Low MSE is true"""
        # load template
        tpl = self.img['dealer']
        tpl_data = np.array(tpl)
        self.logger.debug('loaded dealer template {}'.format(tpl))
        tpl.save(os.path.join(self.DEBUG_PATH, 'dealer_tpl.png'))

        dealers = {}
        for seat, bb in coords['dealers'].items():
            self.logger.debug('parsing seat {} for dealer within {}'.format(seat, bb))

            # crop out box
            box = img.crop(bb[0:4])
            box_data = np.array(box)
            self.logger.debug('dealer box {} from {}'.format(box, bb[:4]))
            box.save(os.path.join(self.DEBUG_PATH, 'dealer_{}.png'.format(seat)))

            # MSE
            mse = np.sum((box_data.astype(np.float) - tpl_data.astype(np.float)) ** 2)
            mse /= mul(*box.size)
            is_dealer = mse <= bb[-1]
            self.logger.info('{}: {} calculated from MSE = {} (threshold {})'.format(
                seat, is_dealer, int(mse), bb[-1]))
            dealers[seat] = is_dealer
        self.logger.info('dealers {}'.format(dealers))
        return dealers

    def parse_playing(self, img, coords):
        """Parses to see who have cards and is playing
        Template will be blank background"""
        participants = []
        for seat, bb in coords['pockets'].items():
            self.logger.debug('parsing seat {} for pocket within {}'.format(seat, bb))

            if seat == 5:
                self.logger.info('auto add hero')
                participants.append(seat)
            else:
                # crop pocket
                box = img.crop(bb[0:4])
                box_data = np.array(box)
                self.logger.debug('pocket box {} from {}'.format(box, bb[:4]))
                box.save(os.path.join(self.DEBUG_PATH, 'pocket_{}.png'.format(seat)))

                # load template
                tpl = self.img['pocket_{}'.format(seat)]
                tpl_data = np.array(tpl)
                self.logger.debug('loaded pocket template {}'.format(tpl))
                tpl.save(os.path.join(self.DEBUG_PATH, 'pocket_{}_tpl.png'.format(seat)))

                # MSE
                mse = self.mse_from_counts(tpl_data, box_data)
                # mse = np.sum((box_data.astype(np.float) - tpl_data.astype(np.float)) ** 2)
                # mse /= mul(*box.size)
                has_cards = mse <= bb[-1]
                self.logger.info('{}: {} calculated from MSE = {} (threshold {})'.format(
                    seat, has_cards, int(mse), bb[-1]))
                if has_cards:
                    participants.append(seat)

        self.logger.info('participants {}'.format(participants))
        return participants

    def parse_balances(self, img, coords, participants):
        """parses the balances on the screenshot"""
        balances = {}
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

    def parse_board(self, img, coords):
        """Parses board for cards
        Checks bg first to exit quickly
        Has to loop over all cards"""
        cto = coords['board']['to']
        self.logger.info(cto)
        cfrom = coords['board']['from']
        self.logger.info(cfrom)
        output_size = (
            cto['br'][0] - cto['tl'][0],
            cto['br'][1] - cto['tl'][1],
        )
        self.logger.info('output size = {}'.format(img.size))
        coeffs = self.find_coeffs(list(cto.values()), list(cfrom.values()))
        table = img.transform(img.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        table.save(os.path.join(self.DEBUG_PATH, 'table.png'))

        board = []
        for i, bb in coords['board']['cards'].items():
            self.logger.debug('parsing board for card {}'.format(i))

            # crop pocket
            box = table.crop(bb[0:4])
            box_data = np.array(box)
            self.logger.debug('board box {} from {}'.format(box, bb[:4]))
            box.save(os.path.join(self.DEBUG_PATH, 'board_{}.png'.format(i)))

            # test background
            bg = self.img['board_{}_bg'.format(i)]
            bg_data = np.array(bg)
            self.logger.debug('loaded board bg template {}'.format(bg))
            bg.save(os.path.join(self.DEBUG_PATH, 'board_{}_bg.png'.format(i)))
            mse = self.mse_from_counts(bg_data, box_data)
            no_card = mse < bb[-1]
            self.logger.info('{}: {} calculated from MSE = {} (<threshold {})'.format(
                i, no_card, int(mse), bb[-1]))
            if no_card:
                self.logger.info('no card on board at {}'.format(i))
                break

            card = self.match_card(box, threshold=bb[-1])
            board.append(card)

        self.logger.info('board {}'.format(board))
        return board

    def parse_cards_hero(self, img, coords):
        """Parses hero's cards
        Should always be visible"""
        cards = []
        for i, bb in enumerate(coords['cards'][5]):
            i += 1
            self.logger.debug('parsing card {} for hero within {}'.format(i, bb))

            # rotate for hand
            if i == 1:
                img_rot = img.rotate(-15, Image.BICUBIC)
            elif i == 2:
                img_rot = img.rotate(15, Image.BICUBIC)
            img_rot.save(os.path.join(self.DEBUG_PATH, 'hero_{}_rot.png'.format(i)))

            # crop pocket
            self.logger.info(img_rot.size)
            box = img_rot.crop(bb[0:4])
            self.logger.debug('hero box {} from {}'.format(box, bb[:4]))
            box.save(os.path.join(self.DEBUG_PATH, 'hero_{}.png'.format(i)))

            card = self.match_card(box, bb[-1])
            cards.append(card)

        self.logger.info('cards {}'.format(cards))
        return cards

    def parse_cards_foes(self, img, coords):
        """Parses to see who have cards and is playing
        Template will be blank background"""
        cards = {}
        for seat, bbs in coords['cards'].items():
            if seat == 5:
                self.logger.info('hero is parsed separately')
                continue

            foe_cards = []
            for i, bb in enumerate(bbs):
                i += 1
                self.logger.debug('parsing seat {} card {} for cards within {}'.format(seat, i, bb))

                # crop pocket
                box = img.crop(bb[0:4])
                self.logger.debug('pocket box {} from {}'.format(box, bb[:4]))
                box.save(os.path.join(self.DEBUG_PATH, 'card_{}_{}.png'.format(seat, i)))
                card = self.match_card(box, bb[-1])
                foe_cards.append(card)

            cards[seat] = foe_cards
        self.logger.info('foes cards {}'.format(json.dumps(cards, indent=4, default=str)))
        return cards
