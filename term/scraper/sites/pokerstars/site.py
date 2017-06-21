from collections import deque, Counter
import hashlib
import json
import logging
import numpy as np
from operator import xor
import os.path
from PIL import Image
import re
import time

from scraper.sites.base import BaseSite, SiteException, NoDealerButtonError, PocketError, BalancesError, ContribError, \
    ThinkingPlayerError, BoardError


logger = logging.getLogger(__name__)


class PokerStars(BaseSite):
    """Game settings:
    Font for scraping table is Lucida Grande. trained file in folder
    Game Settings -> Table appearance:
      -> Theme:
        Mercury theme:
          felt: green
          background: reflective
          front deck: rop right (colored cards, large rank)
          back deck: bottom red
      -> Table Display:
        o dim player not in the hand
        x show players images
        x display fold and watch (zoom)
        o highlight active player
        o show final table background
        x show time left to act
        x display bet amounts
        x show observer count
        x show chip shading (mercury theme)
        o show player info on hover
        o show more games button
      -> Cards:
        x four colored deck
        x show large opponent cards
        x show full hole cards
        o hide hole cards
        o display folded cards
      -> Animation:
        - disabled
      -> Chat:
        - defaults
      -> Preferred seat:
        - always auto-centre me
      -> Announcements:
        o message box on table
        x chat message

    Generate transaparent chips with command. Copy over to Pokerstars/GX/chips&deck/chips
    Do not use PokerstarsUpdate.exe to run as it checks and replaces all files.
    After an update you have to log out again to get settings back.
    """

    NAME = 'PokerStars'
    HERO = 5
    PWD = os.path.dirname(os.path.realpath(__file__))
    PATH_IMAGES = os.path.join(PWD, 'img')
    PATH_CHIPS = os.path.join(PWD, 'chips')
    FILE_COORDS = os.path.join(PWD, 'coords.yml')
    FILE_CARDS_MAP = os.path.join(PWD, 'cards_map.yml')
    HOLE_CARDS = ['__', '__']

    def __init__(self, *args, **kwargs):
        """TLC box is crop box coords"""
        super().__init__(*args, **kwargs)

        # top left corner data
        self.tlc_box = None
        self.wdw_box = None

        # names
        self.__names = {s: deque([], 5) for s in range(1, self.seats + 1)}

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
        logger.info('parsing top left corner with {}'.format(tlc))

        if self.tlc_box:
            img_tlc = img.crop(self.tlc_box)
            if self.debug:
                img_tlc.save(os.path.join(self.PWD, 'top_left_corner.png'))
            mse = self.mse_from_counts(np.array(self.img['top_left_corner']), np.array(img_tlc))
            if mse > tlc['th_mse']:
                self.tlc_box = None
                self.wdw_box = None
                logger.warn('Top left corner moved (mse {} > {})'.format(mse, tlc['th_mse']))

        if not self.tlc_box:
            tlc_loc = self.match_template(img, self.img['top_left_corner'], tlc['th_tpl'])
            if not tlc_loc:
                raise SiteException('Could not locate top left corner')
            self.tlc_box = (tlc_loc[0], tlc_loc[1], tlc_loc[0] + tlc['shape'][0], tlc_loc[1] + tlc['shape'][1])
            logger.debug('tlc box = {}'.format(self.tlc_box))

            wdw_shape = self.coords['window']['shape']
            self.wdw_box = (tlc_loc[0], tlc_loc[1], tlc_loc[0] + wdw_shape[0], tlc_loc[1] + wdw_shape[1])
            logger.debug('window box = {}'.format(self.wdw_box))

        img_wdw = img.crop(self.wdw_box)
        if self.debug:
            img_wdw.save(os.path.join(self.PWD, 'window.png'))
        logger.info('window located at {}'.format(self.wdw_box))
        return img_wdw

    def parse_dealer(self, img):
        """Parses for dealer button. If no button raise exception.
        Btnbox is where the previous button was located. first check if the button is on the same
            spot with mse. if btnbox is not set, locate it via template matching"""
        btn = self.coords['button']
        logger.info('parsing dealer button')

        if self.btn_box:
            logger.debug('checking if dealer button remained in place...')
            img_btn = img.crop(self.btn_box)
            if self.debug:
                img_btn.save(os.path.join(self.PWD, 'dealer_button.png'))
            mse = self.mse_from_counts(np.array(self.img['dealer_button']), np.array(img_btn))
            if mse > btn['th_mse']:
                self.btn_box = None
                self.btn_seat = None
                logger.warn('Dealer button moved (mse {} > {})'.format(mse, btn['th_mse']))

        if not self.btn_box:
            logger.debug('searching for dealer button with template...')
            btn_loc = self.match_template(img, self.img['dealer_button'], btn['th_tpl'])
            if not btn_loc:
                self.btn_box = None
                raise NoDealerButtonError('Could not match dealer button template')
            self.btn_box = (btn_loc[0], btn_loc[1], btn_loc[0] + btn['shape'][0], btn_loc[1] + btn['shape'][1])
            logger.debug('button box = {}'.format(self.btn_box))
            for s, seat_loc in btn['seats'].items():
                if seat_loc == btn_loc:
                    self.btn_seat = s
                    break
            if not self.btn_seat:
                self.btn_box = None
                raise NoDealerButtonError('No seat for dealer button loc {}'.format(btn_loc))

        logger.info('player {} is dealer'.format(self.btn_seat))
        return self.btn_seat

    def parse_names(self, img):
        """Parses names. OCR is not necessary, just use the hash of the image as
        foe name. Hero will always be centered."""
        coords = self.coords['names']
        logger.info('parsing names with {}'.format(coords))
        for s, name_loc in coords['seats'].items():
            name_box = (name_loc[0], name_loc[1], name_loc[0] + coords['shape'][0], name_loc[1] + coords['shape'][1])
            img_name = img.crop(name_box)
            img_name = img_name.point(lambda p: 0 if p > coords['th_ocr'] else 255)
            if self.debug:
                img_name.save(os.path.join(self.PWD, 'name_{}.png'.format(s)))
            name = self.ocr_text(img_name)
            name = re.sub('[^ a-zA-Z0-9]', '', name).strip()
            name = re.sub('( i| 1)$', '', name)
            logger.debug('Player {} name: {}'.format(s, name))
            self.__names[s].append(name)
        common_names = {
            s: Counter(q).most_common()[0][0]
            for s, q in self.__names.items()
        }
        logger.info('Names {}'.format(common_names))
        return common_names

    def parse_balances(self, img, filter_seat=None):
        """Parses balances. Requires OCR.
         - template match dollar
         - crop out where matched after dollar

        Can additionally only OCR for a specific seat
        """
        coords = self.coords['balances']
        logger.info('parsing balances with {}'.format(coords))
        template = self.img['dollar_balance']
        threshold = coords['th_tpl']
        locs = self.match_template(img, template, threshold, True)
        logger.debug('balances dollar locs: {}'.format(locs))
        if len(locs) < 2:
            raise BalancesError('less than 2 balances found')

        images = []
        balances = {}
        for loc_dollar in locs:
            found = False
            for s, seat_loc in coords['seats'].items():
                if filter_seat and s != filter_seat:
                    # logger.debug('looking for {}: skipping {}...'.format(filter_seat, s))
                    continue
                if seat_loc[1] == loc_dollar[1] and xor(seat_loc[0] < coords['th_div'], loc_dollar[0] > coords['th_div']):
                    logger.debug('y equals and both x is less than {}: s{} d{}'.format(coords['th_div'], seat_loc, loc_dollar))
                    found = True
                    # if s == 'pot':
                    #     logger.debug('ignoring total pot value')
                    #     continue
                    loc = (
                        loc_dollar[0] + coords['width'],
                        loc_dollar[1] - 4,
                        loc_dollar[0] + coords['width'] + coords['shape'][0],
                        loc_dollar[1] + coords['shape'][1]
                    )
                    img_bal = img.crop(loc)
                    img_bal = img_bal.point(lambda p: 0 if p > coords['th_ocr'] else 255)
                    if self.debug:
                        images.append(img_bal)
                        img_bal.save(os.path.join(self.PWD, 'balance_{}.png'.format(s)))

                    balance = self.ocr_number(img_bal)
                    if balance is None:
                        raise BalancesError('Amount at {} incorrectly parsed (found via $)'.format(s))
                    balances[s] = balance
                    logger.debug('Player {} balance = {}'.format(s, balance))
                    break
            if not found and not filter_seat:
                # raise BalancesError('loc {} not found for any player'.format(loc_dollar))
                # apparently $ can be in players' names. fml
                logger.warn('Balance loc {} not found for any player'.format(loc_dollar))
                continue
            if filter_seat and balances:
                logger.debug('found balance for player seeked')
                break

        if filter_seat:
            # player must always have balance
            if not balances:
                raise BalancesError('no amt/loc found for player {}'.format(filter_seat))

        logger.info('Found {} balances'.format(len(balances)))
        return balances

    def parse_contribs(self, img, filter_seat=None):
        """Parses contribs. Requires OCR.
         - template match dollar
         - crop out where matched after dollar
        """
        coords = self.coords['contribs']
        logger.info('parsing contribs with {}'.format(coords))
        template = self.img['dollar_contrib']
        threshold = coords['th_tpl']

        contribs = {}
        locs = self.match_template(img, template, threshold, True)
        # DONE
        # if self.debug:
        #     logger.debug(json.dumps(locs, indent=3, default=str))
        for loc_dollar in locs:
            found = False
            for s, seat_loc in coords['seats'].items():
                if filter_seat and s != filter_seat:
                    continue
                if seat_loc[1] == loc_dollar[1] and xor(seat_loc[0] < coords['th_div'], loc_dollar[0] > coords['th_div']):
                    logger.debug('y equals and both x is xor on {}: s={} d={}'.format(coords['th_div'], seat_loc, loc_dollar))
                    found = True
                    loc = (
                        loc_dollar[0] + coords['width'],
                        loc_dollar[1] + 1,
                        loc_dollar[0] + coords['width'] + coords['shape'][0],
                        loc_dollar[1] + coords['shape'][1]
                    )
                    img_bal = img.crop(loc)
                    img_bal = img_bal.point(lambda p: 0 if p > coords['th_ocr'] else 255)
                    if self.debug:
                        img_bal.save(os.path.join(self.PWD, 'contrib_{}.png'.format(s)))
                    contrib = self.ocr_number(img_bal)
                    if contrib is None:
                        raise ContribError('Amount at {} incorrectly parsed (found via $)'.format(s))
                    contribs[s] = contrib
                    logger.debug('Player {} contrib = {}'.format(s, contrib))
                    break
            if not found and not filter_seat:
                raise ContribError('loc {} not found for any player'.format(loc_dollar))
            if filter_seat and contribs:
                logger.debug('found contrib for player seeked')
                break

        # nothing on table if no contrib, default formatting to 0
        if filter_seat and not contribs:
            logger.warn('No contrib found for player {}'.format(filter_seat))
            contribs = {filter_seat: 0}

        logger.info('Found {} contribs: {}'.format(len(contribs), contribs))
        return contribs

    def parse_thinking_player(self, img):
        """Parses board to see if player is thinking by looking at timing bar. First check
        green bar then for red bar."""
        for color in ['green', 'red']:
            coords = self.coords['think_bar'][color]
            logger.info('parsing think_bar for {} with {}'.format(color, coords))
            template = self.img['think_bar_{}'.format(color)]
            threshold = coords['th_tpl']

            loc = self.match_template(img, template, threshold)
            if not loc:
                logger.info('Could not locate any {} think bar'.format(color))
                continue

            contribs = {}
            for s, seat_loc in coords['seats'].items():
                if seat_loc == loc:
                    logger.info('{} is currently thinking'.format(s))
                    return s
            raise ValueError('Unknown {} think bar at {}'.format(color, loc))

        if self.debug:
            input('really no think bar?')
        raise ThinkingPlayerError('Could not locate think bar')

    def parse_board(self, img):
        """Parses the cards on the board. Parse it one by one"""
        card_shape = self.coords['card_shape']
        logger.info('Parsing board with card shape {}'.format(card_shape))
        coords = self.coords['board']
        logger.debug('Parsing board with coords {}'.format(coords))
        board = []
        for i, loc_board in coords['cards'].items():
            loc = (
                loc_board[0],
                loc_board[1],
                loc_board[0] + card_shape[0],
                loc_board[1] + card_shape[1]
            )
            img_board = img.crop(loc)
            if self.debug:
                img_board.save(os.path.join(self.PWD, 'board_{}.png'.format(i)))
            loc_card = self.match_template(self.img['cards_map'], img_board, coords['th_tpl'])
            logger.debug('loc_card = {}'.format(loc_card))
            if not loc_card:
                raise BoardError('Board card {} not identified on cards_map image'.format(i))
            card_name = self.cards_map['{},{}'.format(*loc_card)]
            logger.debug('card_name = {}'.format(card_name))
            if card_name.startswith('board'):
                logger.debug('no card at that board position {}'.format(i))
                break
            board.append(card_name)
            logger.debug('Identified card {} at board pos {}'.format(card_name, i))

        logger.debug('Board = {}'.format(board))
        return board

    def parse_pocket_back(self, img, s):
        """Parses backside of pocket for player"""
        coords = self.coords['pocket_back']
        pt = coords['seats'][s]
        logger.info('parsing back of player {} with {} [card shape = {}]'.format(s, pt, coords['shape']))

        loc = (
            pt[0],
            pt[1],
            pt[0] + coords['shape'][0],
            pt[1] + coords['shape'][1]
        )
        img_back = img.crop(loc)
        if self.debug:
            img_back.save(os.path.join(self.PWD, 'pocket_back_{}.png'.format(s)))

        template = self.img['pocket_back']
        mse = self.mse_from_counts(np.array(template), np.array(img_back))
        if mse > coords['th_mse']:
            logger.info('Player {} has no pocket back'.format(s))
            # DONE
            # if self.debug:
            #     locs = self.match_template(img, self.img['pocket_back'], 0.99, True)
            #     logger.debug('Found the following pocket backs matching template: {}'.format(
            #         json.dumps(locs, indent=4, default=str)))
            #     input('$ player {} really no pocket back?'.format(s))
            return False
        return True

    def parse_pocket_cards(self, img, s):
        """Parses pocket for facing cards"""
        card_shape = self.coords['card_shape']
        pocket = []
        coords = self.coords['pocket_cards']
        logger.debug('parsing pocket of player {} with {} [card shape = {}]'.format(s, coords, card_shape))
        for _, pt_s in enumerate(coords['seats'][s]):
            i = _ + 1
            loc_pt = (
                pt_s[0],
                pt_s[1],
                pt_s[0] + card_shape[0],
                pt_s[1] + card_shape[1]
            )
            img_pocket = img.crop(loc_pt)
            if self.debug:
                img_pocket.save(os.path.join(self.PWD, 'pocket_{}_{}.png'.format(s, i)))

            loc_card = self.match_template(self.img['cards_map'], img_pocket, coords['th_tpl'])
            logger.debug('player {} pocket matched loc: {}'.format(s, loc_card))
            if not loc_card:
                logger.debug('Player {} pocket card {} not identified on cards_map image'.format(s, i))
                # DONE
                # if self.debug:
                #     if input('$ player {} no facing cards: debug? '.format(s)) == 'y':
                #         self.parse_pocket_region(img, s)
                break
            card_name = self.cards_map['{},{}'.format(*loc_card)]
            logger.debug('Player {} card {} identified as {}'.format(s, i, card_name))
            if len(card_name) != 2:
                raise PocketError('Card incorrectly identified')
            pocket.append(card_name)

        if len(pocket) == 1:
            logger.error('Incorrect number of cards identified: {}'.format(len(pocket)))
            return []

        logger.info('Player {} pocket = {}'.format(s, pocket))
        return pocket

    def parse_pocket_region(self, img, s):
        """Parses the pocket region to identify the loc of the card"""
        logger.info('Parsing player {} region'.format(s))
        coords = self.coords['pocket_regions']
        logger.debug('coords: {}'.format(coords))
        pt_s = coords['seats'][s]
        loc_s = (
            pt_s[0],
            pt_s[1],
            pt_s[0] + coords['shape'][0],
            pt_s[1] + coords['shape'][1]
        )
        img_region = img.crop(loc_s)
        if self.debug:
            img_region.save(os.path.join(self.PWD, 'region_{}.png'.format(s)))
        cards = self.match_cards(img_region, coords['th_tpl'])
        for card_name, loc_region in cards.items():
            loc_card = [
                loc_s[0] + loc_region[0],
                loc_s[1] + loc_region[1]
            ]
            logger.info('Player {} parsed region gives: {} at {}'.format(s, card_name, loc_card))
        input('$ continue')

    def check_blind_structure(self, ante):
        """Get SB and BB from known structure"""
        structures = self.coords['structure']
        sb, bb = structures[ante]
        logger.info('Structure for ante {} is SB {} and BB {}'.format(ante, sb, bb))


