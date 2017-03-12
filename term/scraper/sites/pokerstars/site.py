from collections import deque, Counter
import hashlib
import logging
import numpy as np
import os.path

from scraper.sites.base import BaseSite, SiteException, NoDealerButtonError


class PokerStars(BaseSite):

    NAME = 'PokerStars'
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

    def parse_names(self, img):
        """Parses names. OCR is not necessary, just use the hash of the image as
        foe name. Hero will always be centered."""
        names = self.coords['names']
        self.logger.info('parsing names with {}'.format(names))
        for s, name_loc in names['locs'].items():
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

    def parse_dealer(self, img):
        """Parses for dealer button. If no button raise exception.
        Check if button in same place."""
        btn = self.coords['button']
        self.logger.info('parsing dealer button with {}'.format(btn))

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
                if seat_loc == list(btn_loc):
                    self.btn_seat = s
                    break
            if not self.btn_seat:
                raise NoDealerButtonError('No seat for dealer button loc {}'.format(btn_loc))

        self.logger.info('player {} is dealer'.format(self.btn_seat))
        return self.btn_seat
