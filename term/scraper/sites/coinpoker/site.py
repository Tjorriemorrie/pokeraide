import logging
import os.path
import re
from collections import deque, Counter
from operator import xor

import numpy as np

from scraper.errors import PlayerBalanceIsTextError, NoPotInBalancesError
from scraper.sites.base import BaseSite, SiteException, NoDealerButtonError, PocketError, BalancesError, ContribError, \
    ThinkingPlayerError, BoardError

logger = logging.getLogger(__name__)


class CoinPoker(BaseSite):
    """Game settings:

    Virtualbox: bottom right corner, screen resolution 1024x768
    Font: identify font on Identifont. Seems like Museo Sans (not certain). 'y' is off.

    Background: create background 1006x700 and thumbnail 100x70 of color 252837. Copy to gfx folder,
        prepend with next number and select in settings.
    Cards:
        - front: choose the 3rd deck: the 4 suit and class in corner
        - back: choose the 3rd color: reddish
    Disable animation.
    Hide observer chat.
    """

    NAME = 'CoinPoker'
    HERO = 1
    PWD = os.path.dirname(os.path.realpath(__file__))
    PATH_IMAGES = os.path.join(PWD, 'img')
    PATH_CHIPS = os.path.join(PWD, 'chips')
    FILE_COORDS = os.path.join(PWD, 'coords.yml')
    FILE_CARDS_MAP = os.path.join(PWD, 'cards_map.yml')
    HOLE_CARDS = ['__', '__']
    LANG = 'museosans'

    def __init__(self, *args, **kwargs):
        """TLC box is crop box coords"""
        super().__init__(*args, **kwargs)

        # top left corner data
        self.wdw_box = None
        self.tlc_box = None

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
        logger.info(f'parsing top left corner with {tlc}')

        if self.tlc_box:
            img_tlc = img.crop(self.tlc_box)
            if self.debug:
                img_tlc.save(os.path.join(self.PWD, 'top_left_corner.png'))
            mse = self.mse_from_counts(np.array(self.img['top_left_corner']), np.array(img_tlc))
            if mse > tlc['th_mse']:
                self.wdw_box = None
                self.tlc_box = None
                logger.warning(f'Top left corner moved (mse {mse} > {tlc["th_mse"]})')

        if not self.tlc_box:
            tlc_loc = self.match_template(img, self.img['top_left_corner'], tlc['th_tpl'])
            if not tlc_loc:
                raise SiteException('Could not locate top left corner')
            self.tlc_box = (tlc_loc[0], tlc_loc[1], tlc_loc[0] + tlc['shape'][0], tlc_loc[1] + tlc['shape'][1])
            logger.debug(f'tlc box = {self.tlc_box}')

            wdw_shape = self.coords['window']['shape']
            # tlc position needs to go left with required size of the window
            top_right_corner_x = tlc_loc[0] + tlc['shape'][0]
            self.wdw_box = (
                top_right_corner_x - wdw_shape[0], tlc_loc[1],
                top_right_corner_x, tlc_loc[1] + wdw_shape[1])
            logger.debug(f'window box = {self.wdw_box}')

        img_wdw = img.crop(self.wdw_box)
        if self.debug:
            img_wdw.save(os.path.join(self.PWD, 'window.png'))
        logger.info(f'window located at {self.wdw_box}')
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
                logger.warning('Dealer button moved (mse {} > {})'.format(mse, btn['th_mse']))

        if not self.btn_box:
            logger.debug('searching for dealer button with template...')
            btn_loc = self.match_template(img, self.img['dealer_button'], btn['th_tpl'])
            if not btn_loc:
                self.btn_box = None
                raise NoDealerButtonError('Could not match dealer button template')
            self.btn_box = (btn_loc[0], btn_loc[1], btn_loc[0] + btn['shape'][0], btn_loc[1] + btn['shape'][1])
            logger.debug(f'button box = {self.btn_box}')
            for s, seat_loc in btn['seats'].items():
                if seat_loc == btn_loc:
                    self.btn_seat = s
                    break
            if not self.btn_seat:
                self.btn_box = None
                raise NoDealerButtonError('No seat for dealer button loc {}'.format(btn_loc))

        logger.info(f'player {self.btn_seat} is dealer')
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
            name = self.ocr_text(img_name, lang=self.LANG)
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
        """Parses balances. Requires OCR. The location of all the amounts are known. Every seat will
        be parsed unless a filter_seat is passed in. Since the OCR only matches digits and returns
        None if nothing found, it is hard to address the text that can be shown.
        """
        coords = self.coords['amounts']
        logger.info(f'parsing balances with {coords}')
        balances = {}
        for s, seat_loc in coords['balances'].items():
            if filter_seat and s != filter_seat:
                # logger.debug('looking for {}: skipping {}...'.format(filter_seat, s))
                continue
            loc = (
                seat_loc[0],
                seat_loc[1],
                seat_loc[0] + coords['shape'][0],
                seat_loc[1] + coords['shape'][1]
            )
            img_bal = img.crop(loc)
            img_bal = img_bal.point(lambda p: 0 if p > coords['th_ocr'] else 255)
            if self.debug:
                img_bal.save(os.path.join(self.PWD, 'balance_{}.png'.format(s)))

            # have to check if words are on top balance
            txt = self.ocr_text(img_bal, lang=self.LANG)
            if any(p in txt.lower() for p in ['ante', 'fold', 'muck', 'sit', 'out', 'blind', 'small', 'big', 'all', 'allin', 'in']):
                # detected: srnall Blinü
                logger.info(f'Player {s} balance is text {txt}')
                continue
            balance = self.ocr_number(img_bal, lang=self.LANG)
            if balance:
                balances[s] = balance
                logger.debug(f'Player {s} balance = {balance}')

        if filter_seat:
            return balances.get(filter_seat)

        logger.info(f'Balances are {balances}')
        return balances

    def parse_contribs(self, img, filter_seat=None):
        """Parses contribs. Exactly the same as parse_balances.
        """
        coords = self.coords['amounts']
        logger.info(f'parsing contribs with {coords}')

        contribs = {}
        for s, seat_loc in coords['contribs'].items():
            if filter_seat and filter_seat != s:
                continue
            loc = (
                seat_loc[0],
                seat_loc[1],
                seat_loc[0] + coords['shape'][0],
                seat_loc[1] + coords['shape'][1]
            )
            img_bal = img.crop(loc)
            img_bal = img_bal.point(lambda p: 0 if p > coords['th_ocr'] else 255)
            if self.debug:
                img_bal.save(os.path.join(self.PWD, 'contrib_{}.png'.format(s)))
            contrib = self.ocr_number(img_bal, lang=self.LANG)
            if contrib:
                logger.debug(f'Player {s} contrib = {contrib}')
                contribs[s] = contrib

        if filter_seat:
            logger.info(f'Player {filter_seat} contrib is {contribs.get(filter_seat)}')
            return contribs.get(filter_seat)

        logger.info(f'Contribs are {contribs}')
        return contribs

    def parse_pot_and_total(self, img):
        """Parses the pot amount and total"""
        coords = self.coords['amounts']
        logger.info(f'parsing pot and total with {coords}')

        items = []
        for item in ['pot', 'total']:
            table_loc = coords[item]
            loc = (
                table_loc[0],
                table_loc[1],
                table_loc[0] + coords['shape'][0],
                table_loc[1] + coords['shape'][1]
            )
            img_bal = img.crop(loc)
            img_bal = img_bal.point(lambda p: 0 if p > coords['th_ocr'] else 255)
            if self.debug:
                img_bal.save(os.path.join(self.PWD, f'amount_{item}.png'))
            amount = self.ocr_number(img_bal, lang=self.LANG)
            logger.debug(f'Parsed {item} as {amount}')
            items.append(amount)

        logger.info(f'Table amounts are {items}')
        return items

    def parse_thinking_player(self, img):
        """Parses board to see if player is thinking by looking at distinctive circle
        in bottom right corner showing time left"""
        coords = self.coords['thinking']
        logger.info(f'parsing think_bar with {coords}')
        template = self.img['thinking']
        threshold = coords['th_tpl']

        loc = self.match_template(img, template, threshold)
        if not loc:
            raise ThinkingPlayerError('Could not locate thinking')

        for s, seat_loc in coords['seats'].items():
            if seat_loc == loc:
                logger.info(f'{s} is currently thinking')
                return s
        raise ThinkingPlayerError('No player coord for thinking at {loc}')

    def parse_board(self, img):
        """Parses the cards on the board. Parse it one by one"""
        card_shape = self.coords['card_shape']
        logger.info('Parsing board with card shape {}'.format(card_shape))
        coords = self.coords['board']
        logger.debug(f'Parsing board with coords {coords}')
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
                logger.error(f'Board card {i} not identified on cards_map image')
                return board
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
        logger.info(f'parsing back of player {s} with {pt} [card shape = {coords["shape"]}')

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
            if self.debug:
                self.parse_pocket_region(img, s, 'back')
            return False
        return True

    def parse_pocket_cards(self, img, s):
        """Parses pocket for facing cards"""
        card_shape = self.coords['card_shape']
        pocket = []
        coords = self.coords['pocket_cards']
        logger.debug(f'parsing pocket of player {s} with {coords} [card shape = {card_shape}]')
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
            if loc_card == [0, 0]:
                logger.error(f'this fucking player {s} should not have this match')
                continue
            logger.debug(f'player {s} pocket matched loc: {loc_card}')
            if not loc_card:
                logger.warning(f'Player {s} pocket card {i} not identified on cards_map image')
                if self.debug:
                    self.parse_pocket_region(img, s, 'cards')
                continue
            card_name = self.cards_map[f'{loc_card[0]},{loc_card[1]}']
            logger.debug(f'Player {s} card {i} identified as {card_name}')
            if len(card_name) != 2:
                raise PocketError('Card incorrectly identified')
            pocket.append(card_name)

        if len(pocket) == 1:
            logger.error(f'Incorrect number of cards identified: {len(pocket)}')
            return []

        logger.info(f'Player {s} pocket = {pocket}')
        return pocket

    def parse_pocket_region(self, img, s, target):
        """Parses the pocket region to identify the loc of the card"""
        logger.info(f'Parsing player {s} region')
        coords = self.coords['pocket_regions']
        logger.debug(f'coords: {coords}')
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
        if target == 'cards':
            cards = self.match_cards(img_region, coords['th_tpl'])
            if cards:
                for card_name, loc_region in cards.items():
                    loc_card = [
                        loc_s[0] + loc_region[0],
                        loc_s[1] + loc_region[1]
                    ]
                    logger.info(f'Player {s} parsed region gives: {card_name} at {loc_card}')
        elif target == 'back':
            loc_back = self.match_pocket(img_region, coords['th_tpl'])
            if loc_back:
                loc_found = [
                    loc_s[0] + loc_back[0],
                    loc_s[1] + loc_back[1]
                ]
                logger.info(f'Player {s} parsed region gives pocket back at{loc_found}')
        else:
            logger.error(f'target {target} not supported')

    def check_blind_structure(self, ante):
        """Get SB and BB from known structure"""
        structures = self.coords['structure']
        sb, bb = structures[ante]
        logger.info('Structure for ante {} is SB {} and BB {}'.format(ante, sb, bb))


