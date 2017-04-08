from collections import deque, Counter
import hashlib
import logging
import numpy as np
from operator import xor
import os.path

from scraper.sites.base import BaseSite, SiteException, NoDealerButtonError, PocketError, BalancesError, ContribError, ThinkBarError


class PokerStars(BaseSite):

    NAME = 'PokerStars'
    HERO = 5
    PWD = os.path.dirname(os.path.realpath(__file__))
    PATH_IMAGES = os.path.join(PWD, 'img')
    FILE_COORDS = os.path.join(PWD, 'coords.yml')

    def __init__(self, *args, **kwargs):
        """TLC box is crop box coords"""
        super().__init__(*args, **kwargs)

        # top left corner data
        self.tlc_box = None
        self.wdw_box = None

        # names
        self.__names = {s: deque([], 11) for s in range(1, self.seats + 1)}

        # dealer button data
        self.btn_box = None
        self.btn_seat = None


    def parse_top_left_corner(self, img):
        """Parse the top left corner.

        If it has been parsed, the screen is unlikely to move. Use MSE to ensure it
        is still in place.

        If no tlc, then use match template to search for corner.

        Returns cropped window"""
        tlc = self.coords['top_left_corner']
        self.logger.info('parsing top left corner with {}'.format(tlc))

        if self.tlc_box:
            img_tlc = img.crop(self.tlc_box)
            if self.debug:
                img_tlc.save(os.path.join(self.PWD, 'top_left_corner.png'))
            mse = self.mse_from_counts(np.array(self.img['top_left_corner']), np.array(img_tlc))
            if mse > tlc['th_mse']:
                self.tlc_box = None
                self.wdw_box = None
                self.logger.warn('Top left corner moved (mse {} > {})'.format(mse, tlc['th_mse']))

        if not self.tlc_box:
            tlc_loc = self.match_template(img, self.img['top_left_corner'], tlc['th_tpl'])
            if not tlc_loc:
                raise SiteException('Could not locate top left corner')
            self.tlc_box = (tlc_loc[0], tlc_loc[1], tlc_loc[0] + tlc['shape'][0], tlc_loc[1] + tlc['shape'][1])
            self.logger.debug('tlc box = {}'.format(self.tlc_box))

            wdw_shape = self.coords['window']['shape']
            self.wdw_box = (tlc_loc[0], tlc_loc[1], tlc_loc[0] + wdw_shape[0], tlc_loc[1] + wdw_shape[1])
            self.logger.debug('window box = {}'.format(self.wdw_box))

        img_wdw = img.crop(self.wdw_box)
        if self.debug:
            img_wdw.save(os.path.join(self.PWD, 'window.png'))
        self.logger.info('window located at {}'.format(self.wdw_box))
        return img_wdw

    def parse_dealer(self, img):
        """Parses for dealer button. If no button raise exception."""
        btn = self.coords['button']
        self.logger.info('parsing dealer button')

        if self.btn_box:
            img_btn = img.crop(self.btn_box)
            if self.debug:
                img_btn.save(os.path.join(self.PWD, 'dealer_button.png'))
            mse = self.mse_from_counts(np.array(self.img['dealer_button']), np.array(img_btn))
            if mse > btn['th_mse']:
                self.btn_box = None
                self.btn_seat = None
                self.logger.warn('Dealer button moved (mse {} > {})'.format(mse, btn['th_mse']))

        if not self.btn_box:
            btn_loc = self.match_template(img, self.img['dealer_button'], btn['th_tpl'])
            if not btn_loc:
                raise NoDealerButtonError('Could not match dealer button template')
            self.btn_box = (btn_loc[0], btn_loc[1], btn_loc[0] + btn['shape'][0], btn_loc[1] + btn['shape'][1])
            self.logger.debug('btn box = {}'.format(self.btn_box))
            for s, seat_loc in btn['seats'].items():
                if seat_loc == btn_loc:
                    self.btn_seat = s
                    break
            if not self.btn_seat:
                raise NoDealerButtonError('No seat for dealer button loc {}'.format(btn_loc))

        self.logger.info('player {} is dealer'.format(self.btn_seat))
        return self.btn_seat

    def parse_pocket(self, img, s):
        """Parses the table to see who is playing"""
        self.logger.info('parsing pocket of player {}'.format(s))

        # todo auto return true for hero

        coords = self.coords['pockets']
        loc_s = coords['seats'][s]
        loc = (
            loc_s[0],
            loc_s[1],
            loc_s[0] + coords['shape'][0],
            loc_s[1] + coords['shape'][1]
        )
        img_pocket = img.crop(loc)
        if self.debug:
            img_pocket.save(os.path.join(self.PWD, 'pocket_{}.png'.format(s)))

        template = self.img['pocket_back']
        threshold = self.coords['pockets']['th_mse']
        mse = self.mse_from_counts(np.array(template), np.array(img_pocket))
        has_pocket = mse < threshold
        self.logger.info('player {} has pcoket? {}'.format(s, has_pocket))
        return has_pocket

    def parse_names(self, img):
        """Parses names. OCR is not necessary, just use the hash of the image as
        foe name. Hero will always be centered."""
        names = self.coords['names']
        self.logger.info('parsing names with {}'.format(names))
        for s, name_loc in names['seats'].items():
            name_box = (name_loc[0], name_loc[1], name_loc[0] + names['shape'][0], name_loc[1] + names['shape'][1])
            img_name = img.crop(name_box)
            if self.debug:
                img_name.save(os.path.join(self.PWD, 'name_{}.png'.format(s)))
            hash = hashlib.md5(img_name.tobytes()).hexdigest()
            self.logger.debug('#{} hashed name: {}'.format(s, hash))
            self.__names[s].append(hash)
        common_names = {
            s: Counter(q).most_common()[0][0]
            for s, q in self.__names.items()
        }
        self.logger.info('Names {}'.format(common_names))
        return common_names

    def parse_balances(self, img, filter_seat=None):
        """Parses balances. Requires OCR.
         - template match dollar
         - crop out where matched after dollar

        Can additionally only OCR for a specific seat
        """
        coords = self.coords['balances']
        self.logger.info('parsing balances with {}'.format(coords))
        template = self.img['dollar_balance']
        threshold = coords['th_tpl']
        locs = self.match_template(img, template, threshold, True)
        if len(locs) < 2:
            raise BalancesError('less than 2 balances found')

        balances = {}
        for loc_dollar in locs:
            found = False
            for s, seat_loc in coords['seats'].items():
                if filter_seat and s != filter_seat:
                    # self.logger.debug('looking for {}: skipping {}...'.format(filter_seat, s))
                    continue
                if seat_loc[1] == loc_dollar[1] and xor(seat_loc[0] < 850, loc_dollar[0] > 850):
                    self.logger.debug('y equals and both x is less than 800: s{} d{}'.format(seat_loc, loc_dollar))
                    found = True
                    # if s == 'pot':
                    #     self.logger.debug('ignoring total pot value')
                    #     continue
                    loc = (
                        loc_dollar[0] + coords['width'],
                        loc_dollar[1],
                        loc_dollar[0] + coords['width'] + coords['shape'][0],
                        loc_dollar[1] + coords['shape'][1]
                    )
                    img_bal = img.crop(loc)
                    img_bal = img_bal.point(lambda p: 0 if p > coords['th_ocr'] else 255)
                    if self.debug:
                        img_bal.save(os.path.join(self.PWD, 'balance_{}.png'.format(s)))

                    balance = self.ocr_number(img_bal)
                    balances[s] = balance
                    self.logger.debug('Player {} balance = {}'.format(s, balance))
                    break
            if not found and not filter_seat:
                raise BalancesError('loc {} not found for any player'.format(loc_dollar))
            if filter_seat and balances:
                self.logger.debug('found balance for player seeked')
                break

        # player must always have balance
        # todo effect of ragequit
        if filter_seat and not balances:
            raise BalancesError('no loc found for player {}'.format(filter_seat))

        self.logger.info('Found {} balances'.format(len(balances)))
        return balances

    def parse_contribs(self, img, filter_seat=None):
        """Parses contribs. Requires OCR.
         - template match dollar
         - crop out where matched after dollar
        """
        coords = self.coords['contribs']
        self.logger.info('parsing contribs with {}'.format(coords))
        template = self.img['dollar_contrib']
        threshold = coords['th_tpl']
        locs = self.match_template(img, template, threshold, True)

        contribs = {}
        for loc_dollar in locs:
            found = False
            for s, seat_loc in coords['seats'].items():

                # todo change when all contribs are found in config

                # if filter_seat and s != filter_seat:
                    # self.logger.debug('looking for {}: skipping {}...'.format(filter_seat, s))
                    # continue
                if seat_loc[1] == loc_dollar[1] and xor(seat_loc[0] < 860, loc_dollar[0] > 860):
                    self.logger.debug('y equals and both x is xor on 860: s={} d={}'.format(seat_loc, loc_dollar))
                    found = True
                    loc = (
                        loc_dollar[0] + coords['width'],
                        loc_dollar[1],
                        loc_dollar[0] + coords['width'] + coords['shape'][0],
                        loc_dollar[1] + coords['shape'][1]
                    )
                    img_bal = img.crop(loc)
                    img_bal = img_bal.point(lambda p: 0 if p > coords['th_ocr'] else 255)
                    if self.debug:
                        img_bal.save(os.path.join(self.PWD, 'contrib_{}.png'.format(s)))
                    contrib = self.ocr_number(img_bal)
                    contribs[s] = contrib
                    self.logger.debug('Player {} contrib = {}'.format(s, contrib))
                    break
            if not found:
                raise ContribError('loc {} not found for any player'.format(loc_dollar))
            if filter_seat and contribs:
                self.logger.debug('found contrib for player seeked')
                break

        # nothing on table if no contrib, default formatting to 0
        if filter_seat and not contribs:
            contribs = {filter_seat: 0}

        self.logger.info('Found {} contribs'.format(len(contribs)))
        return contribs

    def parse_thinking(self, img):
        """Parses board to see if player is thinking."""
        coords = self.coords['think_bar']
        self.logger.info('parsing think_bar with {}'.format(coords))
        template = self.img['think_bar']
        threshold = coords['th_tpl']

        loc = self.match_template(img, template, threshold)
        if not loc:
            raise ThinkBarError('Could not locate any think bar')

        contribs = {}
        for s, seat_loc in coords['seats'].items():
            if seat_loc == loc:
                self.logger.info('{} is currently thinking'.format(s))
                return s
        raise ValueError('Could not locate think bar (got {})'.format(loc))

    def parse_board(self, img):
