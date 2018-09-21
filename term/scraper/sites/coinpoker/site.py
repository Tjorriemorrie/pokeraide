import logging
import os.path
import re
from collections import deque, Counter
from itertools import product
from operator import itemgetter, add, sub

import numpy as np

from scraper.sites.base import BaseSite, SiteException, NoDealerButtonError, PocketError, ThinkingPlayerError, \
    BoardError, PlayerActionError

logger = logging.getLogger(__name__)


SITE_ACTION_MAP = {
    'ante': 'ante',
    'small blind': 'sb',
    'small blimi': 'sb',
    'srriall blinti': 'sb',
    'big blind': 'bb',
    'big blimi': 'bb',
    'biq blinti': 'bb',
    'big blinti': 'bb',
    'biq blin': 'bb',
    'fold': 'fold',
    'fol': 'fold',
    'folri': 'fold',
    'folti': 'fold',
    'foch': 'fold',
    'check': 'check',
    'checit': 'check',
    'bet': 'bet',
    'raise': 'raise',
    'muck': 'muck',
    'mucit': 'muck',
    'call': 'call',
    'allin': 'allin',
    'sit out': 'sit out',
    'sit oiit': 'sit out',
}


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
                raise NoDealerButtonError(f'No seat for dealer button at {btn_loc}')

        logger.info(f'player {self.btn_seat} is dealer')
        return self.btn_seat

    def parse_names(self, img, filter_seat=None):
        """Parses names. OCR is not necessary, just use the hash of the image as
        foe name. Hero will always be centered."""
        coords = self.coords['names']
        logger.info(f'parsing names with {coords}')
        for s, name_loc in coords['seats'].items():
            if filter_seat and filter_seat != s:
                continue
            name_box = (
                name_loc[0],
                name_loc[1],
                name_loc[0] + coords['shape'][0],
                name_loc[1] + coords['shape'][1]
            )
            img_name = img.crop(name_box)
            img_name = img_name.point(lambda p: 0 if p > coords['th_ocr'] else 255)
            if self.debug:
                img_name.save(os.path.join(self.PWD, 'name_{}.png'.format(s)))
            name = self.ocr_text(img_name, lang=self.LANG)
            name = re.sub('[^ a-zA-Z0-9]', '', name).strip()
            # name = re.sub('( i| 1)$', '', name)
            logger.debug(f'Player {s} name: {name}')
            self.__names[s].append(name)

        if filter_seat:
            if not self.__names[filter_seat]:
                return
            name = Counter(self.__names[filter_seat]).most_common()[0][0]
            return name

        common_names = {
            s: Counter(q).most_common()[0][0]
            for s, q in self.__names.items()
        }

        logger.info(f'Names {common_names}')
        return common_names

    def parse_balances(self, img, filter_seat=None, return_txt=False):
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
            txt = re.sub(r'[^ a-z]+', '', txt.lower()).strip()
            if txt:
                logger.info(f'Player {s} balance is text {txt}')
                if txt not in SITE_ACTION_MAP:
                    # can be chat overlay or bad detection of money
                    logger.warning(f'Could not figure out what {txt} is')
                elif return_txt:
                    return SITE_ACTION_MAP[txt]
                continue
            if return_txt:
                return
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
        """Parses the cards on the board. Parse it one by one.
        """
        coords = self.coords['board']
        logger.debug(f'Parsing board with coords {coords}')
        board_card_shape = coords['card_shape']
        logger.info(f'Parsing board with card shape {board_card_shape}')
        board = []
        # todo only need to continue off from last card
        for i, loc_board in coords['cards'].items():
            loc = (
                loc_board[0],
                loc_board[1],
                loc_board[0] + board_card_shape[0],
                loc_board[1] + board_card_shape[1]
            )
            img_board = img.crop(loc)
            if self.debug:
                img_board.save(os.path.join(self.PWD, 'board_{}.png'.format(i)))
            loc_card = self.match_template(self.img['cards_map'], img_board, coords['th_tpl'])
            logger.debug(f'loc_card = {loc_card}')
            if not loc_card:
                if self.debug:
                    self.parse_board_region(img)
                # cannot raise due to notifications (e.g. slow connection) covers board
                # raise BoardError('fooboard')
                continue
            card_name = self.cards_map.get('{},{}'.format(*loc_card))
            if not card_name:
                if self.debug:
                    self.parse_board_region(img)
                raise BoardError(f'Why is card name {loc_card} not found?')
            logger.debug(f'Identified card {card_name} at board pos {i}')
            if card_name.startswith('board'):
                logger.debug(f'no card at that board position {i}')
                break
            board.append(card_name)

        # if only first card found then it breaks on BOARD_SITE_MAP
        # also happens that not whole flop loaded during screenshot
        if len(board) < 3:
            board = []

        logger.debug(f'Board = {board}')
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
            logger.info(f'Player {s} has no pocket back')
            if self.debug:
                self.parse_pocket_region(img, s, 'back')
            return False
        return True

    def parse_pocket_cards(self, img, s):
        """Parses pocket for facing cards"""
        card_shape = self.coords['card_shape']
        pocket = []
        coords = self.coords['pocket_cards']
        board_card_shape = self.coords['board']['card_shape']
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
            img_resized = img_pocket.resize(board_card_shape)
            if self.debug:
                # img_pocket.save(os.path.join(self.PWD, 'pocket_{}_{}.png'.format(s, i)))
                img_resized.save(os.path.join(self.PWD, 'pocket_{}_{}.png'.format(s, i)))
            loc_card = self.match_template(self.img['cards_map'], img_resized, coords['th_tpl'])
            if not loc_card:
                logger.warning(f'Player {s} pocket card {i} not identified on cards_map image')
                if self.debug:
                    self.parse_pocket_region(img, s, 'cards')
                continue
            logger.debug(f'Player {s} pocket matched loc: {loc_card}')
            card_name = self.find_card_name_by_loc(loc_card, 2)
            if not card_name:
                logger.warning(f'Player {s} card {i} name not found at {loc_card}')
                if self.debug:
                    self.parse_pocket_region(img, s, 'cards')
                # cannot raise otherwise taking action will fold player when he clearly has cards
                return self.HOLE_CARDS
            if len(card_name) != 2:
                raise PocketError(f'Card incorrectly identified on map as {card_name}')
            logger.debug(f'Player {s} card {i} identified as {card_name}')
            pocket.append(card_name)

        if len(pocket) == 1:
            logger.error(f'Incorrect number of cards identified: {len(pocket)}')
            return self.HOLE_CARDS

        logger.info(f'Player {s} pocket = {pocket}')
        return pocket

    def find_card_name_by_loc(self, loc_card, x_offset=0, y_offset=0):
        for y in range(y_offset + 1):
            for x in range(x_offset + 1):
                for op in [add, sub]:
                    card_name = self.cards_map.get(f'{op(loc_card[0], x)},{op(loc_card[1], y)}')
                    if card_name:
                        return card_name

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
            ratio = self.coords['ratio']
            resize_target = (
                round(coords['shape'][0] * ratio),
                round(coords['shape'][1] * ratio)
            )
            logger.debug(f'Resizing card region to {resize_target} from ratio {ratio}')
            img_resized = img_region.resize(resize_target)
            if self.debug:
                img_resized.save(os.path.join(self.PWD, 'region_{}_resized.png'.format(s)))
            cards = self.match_cards(img_resized, coords['th_tpl'])
            errors = []
            if cards:
                for card_name, loc_region in cards.items():
                    loc_card = [
                        pt_s[0] + round(loc_region[0] / ratio),
                        pt_s[1] + round(loc_region[1] / ratio)
                    ]
                    logger.info(f'Player {s} parsed region gives: {card_name} at {loc_card}')
                    errors.append(f'Player {s} parsed region gives: {card_name} at {loc_card}')
                raise Exception(' - '.join(errors))

        elif target == 'back':
            loc_back = self.match_pocket(img_region, coords['th_tpl'])
            if loc_back:
                loc_found = [
                    loc_s[0] + loc_back[0],
                    loc_s[1] + loc_back[1]
                ]
                logger.info(f'Player {s} parsed region gives pocket back at {loc_found}')
        else:
            logger.error(f'target {target} not supported')

    def parse_board_region(self, img):
        """Parses the pocket region to identify the loc of the card"""
        logger.info('Parsing board region')
        coords = self.coords['board']
        logger.debug(f'coords: {coords}')
        img_region = img.crop(coords['region'])
        if self.debug:
            img_region.save(os.path.join(self.PWD, 'region_board.png'))
        cards = self.match_cards(img_region, coords['th_tpl'])
        if cards:
            for card_name, loc_region in cards.items():
                loc_card = [
                    coords['region'][0] + loc_region[0],
                    coords['region'][1] + loc_region[1]
                ]
                logger.info(f'Board parsed region gives: {card_name} at {loc_card}')

    def check_blind_structure(self, ante):
        """Get SB and BB from known structure"""
        structures = self.coords['structure']
        sb, bb = structures[ante]
        logger.info('Structure for ante {} is SB {} and BB {}'.format(ante, sb, bb))

    def infer_player_action(self, img, s, phase, pocket, contrib, engine, current_pot, board_moved, expected):
        cmd = None
        d = engine.data[s]
        balance = self.parse_balances(img, s, True)

        if balance == 'muck':
            # during river showdown, state is not gg for `check_showdown`, thus
            # thus check if player mucked, which means foe called
            if 'check' in expected:
                return ['k']
            elif 'call' in expected:
                return ['c']
            else:
                raise PlayerActionError('Could not call or check on muck?')

        if not pocket:
            # when foe has no cards, he folded, but check muck first
            return ['f']

        # balance is string with action taken
        if isinstance(balance, str):
            if balance not in expected:
                raise PlayerActionError(f'Action {balance} is not in expected {expected}')
            # can confirm fold with empty pocket
            if balance == 'fold':
                if pocket:
                    raise PlayerActionError(f'Player {s} has pocket {pocket} but balance has {balance}?')
                cmd = ['f']
            # check confirmed with still having pocket
            elif balance == 'check':
                if not pocket:
                    raise PlayerActionError(f'Player {s} has no pocket {pocket} but {balance}?')
                cmd = ['k']
            # bet confirmed with contrib
            elif balance == 'bet':
                if contrib:
                    # the amount raised would be with how much our contrib changed
                    amt = contrib - d['contrib']
                else:
                    # others might have folded, check if pot and total is the same
                    pot, total = self.parse_pot_and_total(img)
                    if pot != total:
                        raise PlayerActionError(f'Player {s} bet but no contrib?')
                    amt = total - current_pot
                cmd = ['b', amt]
            # can confirm and should have contrib
            elif balance == 'raise':
                if contrib:
                    # the amount raised would be with how much our contrib changed
                    amt = contrib - d['contrib']
                else:
                    # others might have folded, check if pot and total is the same
                    pot, total = self.parse_pot_and_total(img)
                    if pot != total:
                        raise PlayerActionError(f'Player {s} raised but no contrib?')
                    amt = total - current_pot
                cmd = ['r', amt]
            # can confirm and should have contrib
            elif balance == 'call':
                # could check for contrib, but can catch animation where contribs going to pot
                cmd = ['c']
            elif balance == 'allin':
                # todo check if contrib, otherwise allin was in previous action, and balance should be 0
                cmd = ['a']
            if not cmd:
                raise PlayerActionError(f'Could not infer what player {s} did with {balance}')

        # balance changed
        if not cmd:
            contrib_diff = contrib - d['contrib']
            logger.debug(f'contrib diff= {contrib_diff} (scr {contrib} - trib {d["contrib"]})')

            # check
            if not contrib_diff:
                if 'k' not in expected:
                    raise PlayerActionError(f'No contrib but also cannot check!')
                logger.debug('No change in contrib and can check')
                cmd = ['k']

            # chips moved
            else:
                cmd = ['b', contrib_diff]

        logger.debug(f'Inferred player {s} did {cmd}')
        return cmd

    def calc_board_to_pocket_ratio(self):
        results = []
        spc = self.img['small_pocket_card']
        board_3h = self.img['3h']
        board_3h.show()
        best_fit = (None, 0)
        for px in range(board_3h.size[0], board_3h.size[0] * 3):
            # print(f'current x-axis px is {width}')
            ratio = px / spc.size[0]
            width = round(spc.size[0] * ratio)
            height = round(spc.size[1] * ratio)
            spc_resized = spc.resize((width, height))
            mml = self.match_template(spc_resized, board_3h, 0, mml=True)
            if not mml:
                continue
            results.append((ratio, mml[1]))
            print(f'Ratio {ratio} has mml max of {mml[1]}')
            if mml[1] > best_fit[1]:
                best_fit = (spc_resized, mml[1])
        results.sort(key=itemgetter(1), reverse=True)
        print(f'Top ratios {results[:4]}')
        best_fit[0].show()

