from collections import deque, Counter
from copy import deepcopy
from hashlib import md5
import json
import logging
from os.path import dirname, realpath, join
import shelve

from es.es import ES
from pe.pe import PE


logger = logging.getLogger()


class Engine:
    '''
    The engine requires various properties for the state
    - button location
    - players
    - data
        = status
        = cards
        = equity
    - board
    - pot
    - current phase
    - current player to act
    - all the turn data
        = preflop
        = flop
        = turn
        = river
        = showdown

    Must retain history per phase to establish who is next to play
    '''
    PHASE_PREFLOP = 'preflop'
    PHASE_FLOP = 'flop'
    PHASE_TURN = 'turn'
    PHASE_RIVER = 'river'
    PHASE_SHOWDOWN = 'showdown'
    PHASE_GG = 'gg'

    FILE = join(dirname(realpath(__file__)), 'engine')

    def __init__(self, button, players, sb, bb, **kwargs):
        logger.info('Engine button: {}'.format(button))
        logger.info('Engine players: {}'.format(len(players)))
        logger.info('Engine kwargs: {}'.format(kwargs))

        self.button = button
        self.players = players
        self.sb_amt = sb
        self.bb_amt = bb
        self.go_to_showdown = False
        self.mc = False

        if hasattr(kwargs, 'data'):
            self.data = kwargs['data']
        else:
            self.data = {s: {
                'status': 'in' if p.get('status') else 'out',
                'hand': [],
                'contrib': 0,
                'matched': 0,
                'preflop': [],
                'flop': [],
                'turn': [],
                'river': [],
                'showdown': [],  # for error at stats
            } for s, p in players.items()}
        self.vs = sum([1 if d['status'] == 'in' else 0 for d in self.data.values()])
        self.rivals = self.vs
        self.winner = None

        self.board = kwargs.get('board', [])
        self.pot = kwargs.get('pot', 0)
        self.phase = kwargs.get('phase', self.PHASE_PREFLOP)

        self.preflop = kwargs.get('preflop', {})
        self.flop = kwargs.get('flop', {})
        self.turn = kwargs.get('turn', {})
        self.river = kwargs.get('river', {})
        self.showdown = kwargs.get('showdown', {})

        self.q = None
        self.pe_equities = {}

        for s, d in self.data.items():
            if 'in' not in d['status']:
                continue
            self.data[s]['stats'] = ES.player_stats(self, s)
            self.players[s]['hand_range'] = ES.cut_hand_range(self.data[s]['stats'])
            self.data[s]['strength'] = 1

    def save(self):
        """saves game. this state should be threadsafe"""
        logger.info('saving engine state...')
        with shelve.open(self.FILE) as shlv:
            shlv['hash'] = json.dumps(self.data, sort_keys=True)
            shlv['engine'] = self
        logger.info('engine state saved to {}'.format(self.FILE))

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, deepcopy(v, memo))
        return result

    def __repr__(self):
        logger.debug('getting engine repr...')
        r = '{}:\n'.format(self.phase)

        r += 'Pot: {}\n'.format(self.pot)

        if self.board:
            r += 'Board: {}\n'.format(' '.join(self.board))

        # self.pe.equities(self.data, self.board)

        pta = self.q[0][0] if self.q else 0
        equities = PE.showdown_equities(self)
        logger.debug('got equities for repr')

        for s, p in self.players.items():
            d = self.data[s]
            if 'in' not in d['status']:
                continue

            # add player info
            pr = '{:>10.10} '.format(p.get('name', ''))
            pr += '{: 6d} '.format(p.get('balance', 0) - d.get('contrib', 0))

            status = '<--' if s == pta and self.phase != self.PHASE_SHOWDOWN else '   '
            pr += '{:>6} '.format(d.get('matched', 0) + d.get('contrib', 0) or '')
            pr += '{} '.format(' '.join(d['hand']))
            pr += '{:>3} '.format(s)
            pr += '{} '.format('[]' if self.button == s else '  ')
            pr += '{} '.format(status)
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['preflop']))
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['flop']))
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['turn']))
            pr += '{:3} '.format(''.join(pi['action'].upper() if pi['aggro'] else pi['action'] for pi in d['river']))
            pr += '{:>6} '.format(d['contrib'] or '')
                # pr += '{:10} '.format('*' * d['equity'])
            r += '{}\n'.format(pr)

            # add player stats
            if self.phase != self.PHASE_SHOWDOWN:
                d['stats'] = ES.player_stats(self, s)
                dist_stats = ES.dist_player_stats(d['stats']['actions'], d['strength'])
                r += '{:>40}%'.format(int(equities[s] * 100))
                r += '{:>21}\n\n'.format(dist_stats)

        return r

    def player_queue(self):
        """
        Returns deque of players starting with player after button/dealer
        normally the SB.

        Start at dealer and then rotate to next player that is still playing.
        """
        players_from_button = [(s, p) for s, p in self.players.items() if s >= self.button]
        # logger.debug('players_from_button {}'.format(players_from_button))
        players_rest = [(s, p) for s, p in self.players.items() if s < self.button]
        # logger.debug('players_rest {}'.format(players_rest))
        self.q = deque(players_from_button + players_rest)
        # logger.info('new deque created for this phase {}'.format(self.q))
        self.rotate()

        logger.debug('calculating player positions')
        pos = 1
        for s, q in self.q:
            self.data[s]['pos'] = pos
            # logger.info('player position {} for seat {}'.format(pos, s))
            pos += 1

    def rotate(self):
        ''' Rotates the queue till next action is required.

        Only 'in' status is allowed to action/rotate to next.

        Allin is not available for action, but if all remaining players
        are all 'allin', then to prevent infinite loop check for at least
        1 'in' status before beginning the rotation loop.
        '''
        statuses = Counter([d['status'] for d in self.data.values()])
        self.rivals = statuses['in'] + statuses['allin']
        if not statuses['in']:
            # logger.warn('No "in" statuses left to rotate to')
            return

        while True:
            # logger.debug('deque [{}]: {}'.format(len(list(self.q)), self.queue_display()))
            # logger.debug('rotate: player was seat {}'.format(self.q[0][0]))
            self.q.rotate(-1)
            # logger.debug('rotate: player now seat {}'.format(self.q[0][0]))
            d = self.data[self.q[0][0]]
            if d['status'] == 'in':
                logger.info('next player is {} {}'.format(self.q[0][0], self.q[0][1]['name']))
                break

    def queue_display(self):
        return ['#{}_s{}:{}'.format(_, qi[0], qi[1]['name']) for _, qi in enumerate(self.q)]

    def available_actions(self):
        '''
        Game status for finished is check so that we skip straight to showdown

        If init not done for every phase, then do the init first, e.g. dealing cards.

        If phase balances then set next phase. Next conditional will
        trigger. Do not use elifs

        Preflop will automatically set SB and BB. Cards defaulted to empty pockets
        and hands are set via Game or MC. Players should be updated via reference.

        Phase data holds:
        - Create phase_data list when starting
        - finishes of phase

        At start we check if game phase should skip ahead to showdown, e.g.
          all players are allin
        '''
        # logger.info('getting available actions from engine')
        self.check_game_finished()

        phase_data = getattr(self, self.phase)
        actions = ['hand']

        if self.phase == self.PHASE_PREFLOP:
            # logger.debug('adding preflop actions')
            if not phase_data.get('started'):
                # logger.debug('starting preflop')
                for s, p in self.players.items():
                    # logger.debug(p)
                    self.data[s]['hand'] = ['__', '__'] if bool(p.get('status')) else ['  ', '  ']
                self.player_queue()
                # for headsup the button posts SB
                if self.vs == 2:
                    self.rotate()
                self.do(['sb', self.sb_amt])
                self.do(['bb', self.bb_amt])
                phase_data['started'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_FLOP
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_FLOP:
            # logger.debug('adding flop actions')
            if not phase_data.get('started'):
                self.player_queue()
                phase_data['started'] = True
                self.board += ['__'] * 3 if self.mc else input('\n\nBoard? ').split(' ')
            if self.go_to_showdown:
                phase_data['finished'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_TURN
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_TURN:
            # logger.debug('adding turn actions')
            if not phase_data.get('started'):
                self.player_queue()
                phase_data['started'] = True
                self.board.append('__' if self.mc else input('\n\nTurn? '))
            if self.go_to_showdown:
                phase_data['finished'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_RIVER
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_RIVER:
            # logger.debug('adding river actions')
            if not phase_data.get('started'):
                self.player_queue()
                phase_data['started'] = True
                self.board.append('__' if self.mc else input('\n\nRiver? '))
            if self.go_to_showdown:
                phase_data['finished'] = True
            if phase_data.get('finished'):
                self.phase = self.PHASE_SHOWDOWN
                phase_data = getattr(self, self.phase)

        if self.phase == self.PHASE_SHOWDOWN:
            logger.debug('phase in showdown')
            if not phase_data.get('started'):
                logger.debug('showdown has not started')
                phase_data['started'] = True
            if not phase_data.get('finished'):
                logger.debug('showdown has not finished')
                statuses = Counter([d['status'] for d in self.data.values()])
                logger.debug('SD statuses = {}'.format(list(statuses)))
                if statuses['in'] + statuses['allin'] <= 1:
                    logger.info('SD is finished')
                    for s, d in self.data.items():
                        if 'in' in d['status']:
                            self.do(['gg', s])
                            break
                    phase_data['finished'] = True
                    logger.debug('showdown finished with 1 player')
                else:
                    actions.append('gg')
                    logger.debug('showdown not finished with n players')
            if phase_data.get('finished'):
                logger.debug('showdown finished')
                self.phase = self.PHASE_GG

        else:
            # can only fold when not at showdown
            actions.append('fold')

        # if end of game, then no more actions
        if self.phase == self.PHASE_GG:
            # logger.info('no actions for GG')
            actions = []
        # and if the phase is not showdown, then players
        # can act
        elif self.phase != self.PHASE_SHOWDOWN:
            # the status of the player so
            # that we can see what his
            # available actions are
            s, p = self.q[0]
            d = self.data[s]

            # if allin then you can do no more
            if d['status'] != 'allin':
                # special case to handle blinds during preflop
                contribs = [pd['contrib'] for pd in self.data.values()]
                # preflop special only matters if nobody has raised
                if self.phase == self.PHASE_PREFLOP and max(contribs) == self.bb_amt:
                    # BB only have to check (not call)
                    if 'is_BB' in d:
                        actions.append('check')
                    else:
                        actions.append('call')
                    # always add bet (since no one has acted)
                    # technically a 'raise' but special handling for betting at add_actions
                    actions.append('raise')
                # otherwise someone has set their intention
                elif any(contribs):
                    actions.extend(['call', 'raise'])
                # otherwise nothing has happened and initial aggression available
                else:
                    actions.extend(['check', 'bet'])
                #
                # actions_player = []
                # for action_player in self.data.values():
                #     actions_player.extend(action_player[self.phase])
                # # if b has been made, then only call/raise
                # if set(actions_player) & set(['b']):
                # else:
                #
                # action[0] = 'r' if set(['s', 'l', 'b']) & set(actions_player) else 'b'
                # contribs = Counter([d['contrib'] for d in self.data.values()])
                # # if there is already a contrib to the phase then
                # # you can only call or raise
                # # also, that is only applicable as well during
                # #   preflop has blinds has been placed
                # if self.phase == self.PHASE_PREFLOP or (len(list(contribs)) > 1 and d[self.phase] != ['l']):
                # # else if there has been no action then
                # # you can just check or start betting

        logger.info('available actions = {}'.format(actions))
        return actions

    def do(self, action):
        '''
        Take the action. First are general settings, like setting the hand, otherwise
        it is specific to the current player that is to act.

        If an action indicates the end of a phase, then set that phase finished attr. Also
        put all the contribs to the pot (since bets needs to be matched).
        Todo: move this to per pot contrib & matched

        GG gets winner and gives that player the pot

        A raise cannot be lower and/or equal to current highest contrib. The
         bb should also be a raise if only previous calls

        Update the hand strength with the strength of the action taken by adding
        a row to the player's data's hand_strengths

        Update
            - phase data
                - most phase data will have started and finished attr
            - player status (changed by folding/allin)
            - pot amount
            - player balance

        '''
        # logger.info('Player {} phase {} DO {}'.format(self.q[0][0], self.phase, action))

        if not action[0]:
            logger.warn('no action received')
            return

        if self.mc and action[0] not in ['a', 'b', 'f', 'c', 'r', 'gg']:
            raise Exception('bad action {} given to engine'.format(action))

        if action[0] == 'h':
            hand = [action[2], action[3]] if len(action) > 2 else ['__', '__']
            self.data[int(action[1])]['hand'] = hand
            logger.info('setting hand for player {} to {}'.format(action[1], hand))
            # nothing should change when setting hand
            return

        phase_data = getattr(self, self.phase)

        if action[0] == 'gg':
            logger.info('GG for player {}'.format(action[1]))
            if int(action[1]) < 0:
                logger.info('players draw!')
                # todo distribute monies correctly per pot
                statuses = Counter([d['status'] for d in self.data.values()])
                players_still_in = statuses['allin'] + statuses['in']
                cut = int(self.pot / players_still_in)
                self.winner = []
                for s, p in self.players.items():
                    if 'in' in self.data[s]['status']:
                        p['balance'] += cut
                        self.winner.append(s)
                        logger.info('GG winnings {} draw for = {}'.format(s, cut))
            else:
                p = self.players[int(action[1])]
                p['balance'] += self.pot
                self.winner = [int(action[1])]
                logger.info('GG winnings = {}'.format(self.pot))
            phase_data['finished'] = True
            return

        s, p = self.q[0]
        d = self.data[s]

        if action[0] == 'sb':
            d['is_SB'] = True
            d[self.phase].append({
                'action': 's',
                'aggro': False,
                'rvl': self.rivals,
            })
            if int(action[1]) >= p['balance']:
                action[0] = 'a'
                logger.warn('allin during SB')
            else:
                d['contrib'] += action[1]
                self.rotate()
                logger.debug('Did action SB')

        if action[0] == 'bb':
            d['is_BB'] = True
            d[self.phase].append({
                'action': 'l',
                'aggro': False,
                'rvl': self.rivals,
            })
            if int(action[1]) >= p['balance']:
                action[0] = 'a'
                logger.warn('allin during BB')
            else:
                d['contrib'] += action[1]
                self.rotate()
                logger.debug('Did action BB')

        contribs_all = [pd['contrib'] for pd in self.data.values()]
        total_contribs = sum(contribs_all)
        max_contrib = max(contribs_all)
        contrib_short = max_contrib - d['contrib']
        # logger.debug('total_contrib={} and max_contrib={} and contrib_short={}'.format(
        #     total_contribs, max_contrib, contrib_short))

        # facing_aggro if contrib_short AND not limping during preflop
        could_limp = True if self.phase == self.PHASE_PREFLOP and max_contrib == self.bb_amt else False
        faced_aggro = False
        pot_odds = None
        if contrib_short and not could_limp:
            balance_left = p['balance'] - d['contrib']
            faced_aggro = True
            pot_odds = min(balance_left, contrib_short) / (self.pot + total_contribs)
        logger.debug('faced_aggro? {}'.format(faced_aggro))

        if action[0] == 'f':
            d['status'] = 'fold'
            d[self.phase].append({
                'action': 'f',
                'aggro': faced_aggro,
                'pot_odds': pot_odds,
                'rvl': self.rivals,
            })
            d['hand'] = ['  ', '  ']
            logger.debug('Did action fold')
            self.rotate()

        if action[0] in ['b', 'r']:
            # cannot bet/raise less than required
            if int(action[1]) < max_contrib:
                raise ValueError('A raise {} cannot be less than the max contrib {}'.format(action[1], max_contrib))

            # player raising on BB gives error (since it is the same)
            if not int(action[1]) - contrib_short and 'is_BB' not in d and self.phase == self.PHASE_PREFLOP:
                # logger.warn('changed bet/raise that is equal to maxcontrib instead to a call')
                action[0] = 'c'

            # change to allin if it is all the money
            if int(action[1]) >= p['balance'] - d['contrib']:
                # logger.warn('changed b/r to allin as it is everything player has')
                action[0] = 'a'
            else:
                # cannot bet if you are required to put in (e.g. somebody else made bet)
                actions_player = []
                for action_player in self.data.values():
                    actions_player.extend(''.join(pa['action'] for pa in action_player[self.phase]))
                action[0] = 'r' if set(['s', 'l', 'b']) & set(actions_player) else 'b'
                action_name = 'raise' if action[0] == 'r' else 'bet'
                # logger.error('action is {} from {} & {}'.format(action[0], set(['s', 'l', 'b']), set(actions_player)))

                bet_to_pot = int(action[1]) / (self.pot + total_contribs)
                d[self.phase].append({
                    'action': action[0],
                    'aggro': faced_aggro,
                    'bet_to_pot': bet_to_pot,
                    'pot_odds': pot_odds,
                    'rvl': self.rivals,
                })
                d['contrib'] += int(action[1])
                logger.debug('Did action bet/raise {}'.format(action[0]))
                self.rotate()

        if action[0] in ['k', 'c']:
            # if amt to call is more than what player has, it is allin
            if contrib_short >= p['balance']:
                logger.warn('changed k/c to allin as player is out of money')
                action[0] = 'a'
            else:
                # cannot check if short
                if action[0] == 'k' and contrib_short:
                    action[0] = 'c'
                # fix call to check if nothing to match
                elif action[0] == 'c' and not contrib_short:
                    action[0] = 'k'

                d[self.phase].append({
                    'action': action[0],
                    'aggro': faced_aggro,
                    'pot_odds': pot_odds,
                    'rvl': self.rivals,
                })
                d['contrib'] += contrib_short
                logger.debug('Did action {} (contrib: {})'.format(action[0], contrib_short))
                self.rotate()

        if action[0] == 'a':
            # can be short, but still allin, therefore always use the balance for the amount
            d[self.phase].append({
                'action': 'a',
                'aggro': faced_aggro,
                'pot_odds': pot_odds,
                'rvl': self.rivals,
            })
            d['status'] = 'allin'
            d['contrib'] = p['balance']
            logger.debug('Did action allin')
            self.rotate()

        if self.is_round_finished():
            self.gather_the_money()
            phase_data['finished'] = True

        # adjust strength with current stats
        self.adjust_strength(s, d, action[0])

    def gather_the_money(self):
        """Gathering money from each player's contrib

        How to handle allin?

        Since gathering only happens when
        - round is finished
        - everybody goes allin
        - during MC when getting net EV

        Only the highest contrib of all players need to be reduced to
        the next highest contrib
        """
        contribs = [pd['contrib'] for pd in self.data.values()]
        max_first = contribs.pop(contribs.index(max(contribs)))
        max_second = contribs.pop(contribs.index(max(contribs)))
        returned = max_first - max_second
        for s, d in self.data.items():
            if returned and d['contrib'] == max_first:
                d['contrib'] -= returned
                logger.debug('Returned {} as unmatched for player {}'.format(returned, s))
            self.pot += d['contrib']
            self.players[s]['balance'] -= d['contrib']
            d['matched'] += d['contrib']
            # logger.info('player {} matched: {} (added {})'.format(s, d['matched'], d['contrib']))
            d['contrib'] = 0

    def is_round_finished(self):
        """
        This checks if the round is finished.
        - all players has had a chance to bet
        - money put in pot is the same for every 'in' player (ignoring allin)
        - in cannot be lower than allin (has to call with bigger pot)
        """
        is_bb_finished = True
        in_contribs = Counter()
        allin_contribs = Counter()
        for s, d in self.data.items():
            # logger.debug('{} is {}'.format(s, d))
            if d['status'] == 'in':
                if not d[self.phase]:
                    # logger.debug('#{} has not acted yet'.format(s))
                    return False
                elif self.phase == self.PHASE_PREFLOP and 'is_BB' in d and len(d[self.phase]) < 2:
                    is_bb_finished = False
                in_contribs.update([d['contrib']])
            elif d['status'] == 'allin':
                allin_contribs.update([d['contrib']])

        if len(list(in_contribs)) > 1:
            # logger.debug('bets are not equal')
            return False

        elif list(in_contribs) and len(list(allin_contribs)) and min(list(in_contribs)) < max(list(allin_contribs)):
            # logger.debug('still have to call allin')
            return False

        elif not is_bb_finished:
            # logger.debug('BB still has to act')
            return False

        logger.info('round is finished')

        """Helper to quickly check if all players are allin
        or if one player is allin and another called

        If one goes allin, and TWO players call, then they can still bet again.
          Check the todo
        """
        # Todo need to handle allin players creating sidepot
        statuses = Counter([d['status'] for d in self.data.values()])
        if statuses['allin'] and statuses['in'] <= 1:
            self.go_to_showdown = True
            logger.debug('go_to_showdown {} players are allin'.format(statuses['allin']))

        return True

    def check_game_finished(self):
        """
        If all players fold preflop then end the game. This will mark every phase as
        finished, except SD - which still need to do the distribution to winners. Then
        it will mark itself as finished, as it is basically just a post-process game
        ending.

        Phase gets set to SD so that phases do not deal cards to the board
        and cause misinformation in the storage.

        Default is False
        Conditions:
        - all folded, last one left
         * this includes allins
         ** allins still need to follow the river and showdown
        """
        if self.phase == self.PHASE_SHOWDOWN:
            logger.debug('Game already in showdown')
            return

        statuses = Counter([d['status'] for d in self.data.values()])
        # logger.debug('statuses {}'.format(statuses))
        if (statuses['in'] + statuses['allin']) <= 1:
            logger.info('Game finished with only 1 player left "in"')
            self.gather_the_money()
            self.phase = self.PHASE_SHOWDOWN
            return

    def adjust_strength(self, s, d, a):
        """Adjust the min/max tuple of strength based on action taken"""
        logger.info('adjusting strength for action {}'.format(a))

        if a in ['f', 'k', 'sb', 'bb']:
            logger.debug('no aggression faced')
            return

        stats = d['stats']['actions']
        logger.debug('p stats actions: {}'.format(stats))

        dist = ES.dist_player_stats(stats)
        logger.debug('p dist: {}'.format(dist))

        # find first available lower bound
        # from where action is met
        lower_bound = 0.50
        action_found = False
        for o in ['c', 'b', 'r', 'a']:
            if o == a:
                action_found = True
                logger.debug('action found')
            if not action_found:
                logger.debug('action not found yet...')
                continue
            dist_vals = [k for k, v in dist.items() if v == o]
            logger.debug('dist_vals {}'.format(dist_vals))
            if not dist_vals:
                logger.debug('no dist_vals...')
                continue
            lower_bound = min(dist_vals)
            logger.debug('lower bound = {} (with {})'.format(lower_bound, o))
            break

        # update strength to fold limit
        # 1111111111
        # fffffccccc
        # times first call of 50% during preflop
        # 1.00 * 50% = 0.50
        # 0000011111
        # ffffffffcc
        # times first call of 60% during flop
        # 0.50 * 20% = 0.10
        # 0000000001

        new_strength = d['strength'] * (1 - lower_bound)
        logger.debug('new strength = {} (old {} * {})'.format(new_strength, d['strength'], (1 - lower_bound)))
        d['strength'] = new_strength

    @property
    def rounds_left(self):
        if self.phase == self.PHASE_PREFLOP:
            return 4
        elif self.phase == self.PHASE_FLOP:
            return 3
        elif self.phase == self.PHASE_TURN:
            return 2
        elif self.phase == self.PHASE_RIVER:
            return 1
        else:
            return 0

