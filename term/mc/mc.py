from collections import deque, Counter
from copy import deepcopy
import hashlib
import json
import logging
from operator import itemgetter
import retrace
import shelve
import time
from treelib import Tree
import uuid

from engine.engine import Engine
from es.es import ES
from pe.pe import PE


logger = logging.getLogger(__name__)


class MonteCarlo:

    def __init__(self, engine=None, timeout=None, hero=None):
        if not engine:
            logger.info('engine not given, loading from file...')
            self.engine_checksum = None
            self.load_engine(hero)
        else:
            logger.info('engine given')
            self.init(engine, hero)
        self.timeout = timeout or 1

    @retrace.retry(on_exception=(EOFError, KeyError), interval=0.1, limit=None)
    def load_engine(self, hero):
        with shelve.open(Engine.FILE) as shlv:
            if shlv['hash'] != self.engine_checksum:
                logger.info('loading engine from file...')
                self.engine_checksum = shlv['hash']
                self.init(shlv['engine'], hero)

    def init(self, engine, hero):
        logger.info('init state')
        self.engine = engine
        self.hero = hero or self.engine.q[0][0]
        self.hero_pocket = self.engine.data[self.hero]['hand']
        logger.info('HERO is at seat {} with {}'.format(self.hero, self.hero_pocket))

        self.is_complete = False
        self.convergence_size = 11
        self.watched = False
        self.init_tree()

    def init_tree(self):
        """create the tree. Add a root; available action will add the first level of children"""
        self.traversed_ceiling = 1
        self.tree = Tree()
        root = self.tree.create_node('root', identifier='000_root', data={'traversed': 0, 'ev': 0})
        # logger.info('tree:\n{}'.format(self.tree.show()))
        self.convergence = {
            'deq': deque(maxlen=self.convergence_size),
        }
        # input('new tree')

    def watch(self):
        """Runs when engine file changes. Just kicks off run for 3s sprints"""
        logger.info('Monte Carlo watching every {}s...'.format(self.timeout))
        while True:

            # loads new engine file if checksum changed
            self.load_engine()

            # do not analyze if game finished
            if self.engine.phase in [self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG]:
                if not self.watched:
                    logger.error('game is finished')
                    self.watched = True
                time.sleep(3)
                continue

            # do not analyze if hero does not have pocket
            if self.hero_pocket in [['__', '__'], ['  ', '  ']]:
                if not self.watched:
                    logger.error('hero does not have a pocket')
                    self.watched = True
                time.sleep(0.5)
                continue

            # do not analyze if hero is not to play
            if self.hero != self.engine.q[0][0]:
                if not self.watched:
                    logger.error('hero is not to act')
                    self.watched = True
                time.sleep(0.5)
                continue

            if self.is_complete:
                if not self.watched:
                    logger.error('mc is complete')
                    self.watched = True
                time.sleep(2)
                continue

            # run a few sims
            logger.debug('running now with timeout {}'.format(self.timeout))
            self.run()
            self.timeout += 0.1

    def run(self, duration):
        """Run simulations
        For x:
         - clone engine
         - start at root
          -- iterate and find next unprocessed node
          -- action engine to that node parent
          -- process that node
         - keep processing
         - with return EV

         Levelling:
            extremely huge iterations when many players. So
            do the most probably actions only till all done.

        Handling close action approximations:
        """
        logger.info('Monte Carlo started')
        self.traversed_focus = 0
        time_start = time.time()
        while self.traversed_focus < self.traversed_ceiling and time.time() - time_start < self.timeout:
            self.is_complete = True
            leaves = self.tree.paths_to_leaves()
            logger.debug('leaves from tree: {}'.format(len(leaves)))
            # leaves.sort(key=lambda lp: len(lp) + sum(int(lpn.split('_')[0]) for lpn in lp), reverse=True)
            # logger.debug('{} leaves are now sorted by formula'.format(len(leaves)))
            # logger.error(json.dumps(leaves, indent=4, default=str))
            # input('>>')
            leaves.sort(key=lambda lp: lp[-1][:3], reverse=True)
            logger.debug('{} leaves are now sorted by rank'.format(len(leaves)))
            # logger.debug('{}'.format(json.dumps(leaves[:3], indent=4, default=str)))
            leaves.sort(key=len)
            logger.debug('{} leaves are now sorted by length'.format(len(leaves)))
            # logger.debug('{}'.format(json.dumps(leaves[:3], indent=4, default=str)))
            for leaf in leaves:
                self.run_item(leaf)
                # self.show_best_action()
                # input('>>')
                # if random.random() < 0.001:
                #     input('random check')
                if time.time() - time_start >= self.timeout:
                    logger.info('time is up for processing!')
                    self.is_complete = False
                    break
            if self.is_complete:
                logger.info('Tree level {} fully traversed, levelling up to ceiling {}'.format(
                    self.traversed_focus, self.traversed_ceiling))
                self.traversed_focus += 1
        duration = time.time() - time_start
        # self.show_best_action()
        logger.warn('Monte Carlo ended after taking {}s'.format(int(duration)))

    def run_item(self, path):
        logger.debug('running this path: {}'.format(path))
        e = deepcopy(self.engine)
        e.mc = True
        """To calculate the investment for the loss EV, the total amounts used till end is required. Cannot
         use final player balance on engine as that might have winnings allocated to it by the engine. Instead
         the difference from all the new matched bets from the current matched bets will be used.
         Need to add current contrib
        """
        e.matched_start = e.data[self.hero]['matched'] + e.data[self.hero]['contrib']
        logger.info('hero starting with matched = {} from {} + {}'.format(
            e.matched_start, e.data[self.hero]['matched'], e.data[self.hero]['contrib']))

        # self.tree.show()
        self.fast_forward(e, path)
        logger.info('{}'.format('-' * 200))
        # input('check item')

    def show_best_action(self):
        """Calculates best action on root"""
        logger.error("\n\n")
        sum_traversed = 0
        delta = 0
        max_ev = float('-inf')
        action = None
        amount = None
        for nid in self.tree[self.tree.root].fpointer:
            child = self.tree[nid]
            logger.debug('{} {}'.format(child.tag, child.data))
            dat = child.data
            sum_traversed += dat['traversed']
            logger.error('{} @{} => {}'.format(dat['action'], dat['traversed'], round(dat['ev'], 4)))

            # delta += abs(1 - (self.convergence.get(dat['action'], 1) / dat['ev'] if dat['ev'] else 1))
            # self.convergence[dat['action']] = dat['ev']

            if dat['ev'] > max_ev:
                max_ev = dat['ev']
                action = dat['action']
                if action.startswith('bet') or action.startswith('raise') or action.startswith('allin'):
                    amount = dat['amount']

        best_action = '{}{}'.format(action, ' with {}'.format(amount) if amount else '')

        # self.convergence['deq'].append(round(delta, 1))
        self.convergence['deq'].append(best_action)
        # logger.error('deq: {}'.format(list(self.convergence['deq'])))

        logger.error('')
        logger.error('Timeout: {}'.format(round(self.timeout, 1)))
        logger.error('Traversed: {}'.format(sum_traversed))
        deq_cnts = Counter(list(self.convergence['deq']))
        # logger.error('deq: {}'.format(deq_cnts.most_common()))

        logger.error('{}% for {}'.format(
            # 100 * sum(dq == deq_list[-1] for dq in deq_list[:-1]) // (len(deq_list) - 1)
            100 * (deq_cnts.most_common()[0][1] - deq_cnts.most_common()[1][1]) // self.convergence_size
            if len(deq_cnts) > 1 else 100 * len(self.convergence['deq']) // self.convergence_size,
            deq_cnts.most_common()[0][0]
        ))

    def fast_forward(self, e, path):
        """Do actions on engine till the leaf is reached. Need to do available_actions before
        every DO

        First check if the leave is already processed, then skip this path. When the leaf is reached
        then process from that node.

        Remember to send through only the first letter for the action.

        Then update the nodes from this leaf back up the tree
        """
        logger.info('Fast forwarding {} nodes'.format(len(path)))

        if len(path) == 1:
            logger.info('processing root for first time')
            self.process_node(e, self.tree[path[0]])
            self.is_complete = False
            return

        leaf_node = self.tree[path[-1]]
        logger.debug('checking if last node has been processed:')
        logger.debug('last node leaf {} has node data {}'.format(leaf_node.tag, leaf_node.data))
        if leaf_node.data['traversed'] > self.traversed_focus:
            logger.info('This leaf node ({}) above focus level {}'.format(leaf_node.tag, self.traversed_focus))
            return

        for nid in path[1:]:
            node = self.tree[nid]
            logger.debug('fast forwarding action for node {}'.format(node.tag))
            e.available_actions()
            cmd = [node.data['action'][0]]
            if 'amount' in node.data:
                cmd.append(node.data['amount'])
                logger.debug('Adding bet value of {}'.format(node.data['amount']))
            logger.debug('Executing path action {} for {}'.format(cmd, node.tag))
            logger.debug('Executing path action {} with data {}'.format(cmd, node.data))
            e.do(cmd)

            if node.is_leaf():
                logger.debug('{} is a leaf node, processing next...'.format(node.tag))
                self.process_node(e, node)
                logger.info('nodes processed, now updating nodes that were fast forwarded')
                for processed_nid in reversed(path[1:]):
                    processed_node = self.tree[processed_nid]
                    self.update_node(processed_node)

        logger.info('all nodes in path processed')
        self.is_complete = False

    def process_node(self, e, n):
        """Process node
        Get actions available for node
        Pick action to traverse with UCT
        Process action selected
        Return EV
        """
        logger.info('processing node {} with data {}'.format(n.tag, n.data))

        # this node is the hero folding
        # was created with other children (but not most probable at that time to be proc as child)
        # if hero folding, then make this node a leaf node with fold eq
        # exiting before adding children alleviates the need to remove the immediately again thereafter
        # bug: cannot use engine.q as it already rotated after taking action getting here
        if not n.is_root() and n.data['action'] == 'fold' and self.hero == n.data['seat']:
            winnings, losses = self.net(e)
            result = {
                'ev': losses,
                'traversed': self.traversed_focus + 1,
            }
            logger.info('hero has folded this node given: {}'.format(result))
            n.data.update(result)
            logger.info('node data after fold: {}'.format(n.data))
            return

        # add the children of the node
        if not n.fpointer:
            self.add_actions(e, n)

        # this node is a leaf (no more actions to take!)
        # either the game finished and we have winner and pot
        # or we have to use pokereval.winners
        if n.is_leaf():
            logger.info('node {} is the final action in the game'.format(n.tag))
            # winner given (easy resolution)
            if e.winner:
                logger.debug('engine gave winner {}'.format(e.winner))
                net_results = self.net(e)
                ev = net_results[0] if self.hero in e.winner else net_results[1]
            # else if the winner is unknown
            # then calculate winners and use
            # percentage of hero as amt
            else:
                equities = PE.showdown_equities(e)
                logger.debug('pokereval equities: {}'.format(equities))
                winnings, losses = self.net(e)
                ev_pos = winnings * equities.get(self.hero, 0)
                logger.debug('ev_pos = {} from winnings {} * eq {}'.format(ev_pos, winnings, equities.get(self.hero, 0)))
                ev_neg = losses * (1 - equities.get(self.hero, 0))
                logger.debug('ev_neg = {} from losses {} * -eq {}'.format(ev_neg, losses, (1 - equities.get(self.hero, 0))))
                ev = ev_pos + ev_neg
                logger.info('Net EV: {} from {} + {}'.format(ev, ev_pos, ev_neg))
            result = {
                'ev': ev,
                'traversed': self.traversed_focus + 1,
            }
            logger.info('{} leaf has result {}'.format(n.tag, result))
            n.data.update(result)
            return

        # node is all good (not leaf (has children) and not hero folding)
        # get child actions and process most probable action
        a_node = self.most_probable_action(n)
        action = a_node.data['action']
        logger.info('taking next child node action {}'.format(action))

        # if it is hero and he folds,
        # it is not necessarily an immediate ZERO equity
        # since my previous contrib needs to be added to the pot (i.e. contribs after starting mc)
        # i.e. make this a leaf node implicitly
        # no child nodes to remove for fold
        if action == 'fold' and self.hero == a_node.data['seat']:
            winnings, losses = self.net(e)
            result = {
                'ev': losses,
                'traversed': self.traversed_focus + 1,
            }
            logger.info('hero has folded the child node selected: {}'.format(result))
            a_node.data.update(result)
            logger.info('a_node data after: {}'.format(a_node.data))

        # else we must process the node
        else:
            logger.info('taking action {} and processing that node'.format(action))
            cmd = [action[0]]
            if 'amount' in a_node.data:
                cmd.append(a_node.data['amount'])
                logger.debug('Adding bet value of {}'.format(a_node.data['amount']))
            e.do(cmd)
            self.process_node(e, a_node)

        # it will traverse back up to the root
        # root can be skipped
        if n.is_root():
            logger.debug('reached the root')
            return

        # action node has been processed, now update node
        self.update_node(n)

    def update_node(self, node):
        """Update the node's data

        If leaf, then it was already calculated during processing, and now
        do not change it: the ev is the ev

        Minimax applied, hero pick best and foe picks min after p

        Traversed will stay the traversed_focus level for leaves, but for parent nodes
        the traversed will be the number of leaves reached from that node.
        """
        # fast forwarding will send here, just ignore node if leaf
        if node.is_leaf():
            logger.debug('not updating {}: it is final game result (no leaf nodes)'.format(node.tag))
            logger.debug('not updating {}: final data {}'.format(node.tag, node.data))
            return

        depth = self.tree.depth(node)
        logger.info('updating node {} at depth {}'.format(node.tag, depth))
        logger.info('node has {} before update'.format(node.data))

        is_hero = node.data['seat'] == self.hero
        # logger.debug('is hero? {}'.format(is_hero))

        if not len(node.fpointer):
            logger.error('node {} with {} as no children...'.format(node.tag, node.data))
            raise Exception('not necessary to process leaves')
        logger.debug('extracting data from {} children nodes...'.format(len(node.fpointer)))

        n_ev = float('-inf') if is_hero else 0
        n_traversed = 0
        for child_nid in node.fpointer:
            child_node = self.tree[child_nid]
            logger.debug('child node {} has {}'.format(child_node.tag, child_node.data))
            dat = child_node.data
            if not dat['traversed']:
                logger.debug('{} skipping untraversed'.format(child_node.tag))
                continue

            # get max for hero
            if is_hero:
                equities = PE.showdown_equities(self.engine)
                n_ev = max(n_ev, dat['ev'] * equities.get(self.hero, 0))
                # n_ev = max(n_ev, dat['ev'])
                logger.debug('hero ev of {}'.format(n_ev))

            # get min for foe
            else:
                # ev_adj = dat['ev'] * dat['stats']
                # logger.debug('foe min between {} and {}'.format(n_ev, ev_adj))
                # n_ev = min(n_ev, ev_adj)
                n_ev += dat['ev'] * dat['stats']
                logger.debug('foe node ev = {} from {} * {}'.format(n_ev, dat['ev'], dat['stats']))

            n_traversed += 1

        node.data.update({
            'ev': n_ev,
            'traversed': n_traversed
        })
        logger.info('now node has {} ev~{} after {}'.format(
            node.tag, round(n_ev, 3), n_traversed))

        if not node.data['traversed']:
            raise Exception('node cannot be untraversed')


    def net(self, e):
        """Stored the balance at the start of sim.
        Now calculate difference as player total contrib
        Winnings will be less total contrib

        if player is SB/BB then the blinds gets added to neg ev, which
          is probably wrong.
        """
        e.gather_the_money()
        p = e.players[self.hero]
        d = e.data[self.hero]

        matched_diff = d['matched'] - e.matched_start
        logger.debug('matched diff = {} from {} - {}'.format(matched_diff, d['matched'], e.matched_start))

        winnings = int(e.pot - matched_diff)
        logger.debug('winnings diff = {} from pot {} less matched {}'.format(winnings, e.pot, matched_diff))

        losses = int(-matched_diff)
        logger.info('Winnings = {} and losses = {}'.format(winnings, losses))
        return winnings, losses

    def most_probable_action(self, parent):
        """All nodes will be processed once at least but it will never happen. Just return
        the most probable node for most accurate play. Using stats fields on data
        There should not be any untraversed nodes. So first get untraversed, then short
        and pop first one"""
        logger.info('getting most probable action after {}'.format(parent.tag))
        children = self.tree.children(parent.identifier)
        children = [c for c in children if not c.data['traversed']]
        if not children:
            raise MonteCarloError('Cannot choose most probable action when all nodes are traversed')
        children.sort(key=lambda c: c.data['stats'], reverse=True)
        child = children[0]
        logger.debug('{} is untraversed, returning that node for actioning'.format(child.tag))
        return child

    def add_actions(self, e, parent):
        """Add actions available to this node
        If in GG phase then no actions possible, ever.
        Remove 'hand'
        Bets:
            - preflop are 2-4x BB
            - postflop are 40-100% pot
        Raise:
            - always double
        Allin:
            - only on river
            - if out of money then converted to allin

        Scale non-fold probabilities even though it should not have an effect.
        """
        logger.info('adding actions to {}'.format(parent.tag))
        actions = e.available_actions()
        s, p = e.q[0]
        d = e.data[s]
        balance_left = p['balance'] - d['contrib']

        if not actions:
            logger.warn('no actions to add to node')
            return

        if 'gg' in actions:
            logger.debug('no actions available, got gg')
            return

        actions.remove('hand')

        # remove fold if player can check
        if 'check' in actions:
            actions.remove('fold')
            # logger.debug('removed fold when check available')

        # remove fold for hero
        # if s == self.hero and 'fold' in actions:
        #     actions.remove('fold')
        #     logger.debug('removed fold from hero')

        # remove raise if player has already been aggressive
        if 'raise' in actions and any(pa['action'] in 'br' for pa in d[e.phase]):
            actions.remove('raise')
            # logger.debug('removed raise as player has already been aggressive')

        # leave allin only for river
        if 'allin' in actions:
            actions.remove('allin')
            # logger.debug('removed allin by default')

        # load stats (codes with counts)
        stats = ES.player_stats(e, s)
        max_contrib = max(pd['contrib'] for pd in e.data.values())
        contrib_short = max_contrib - d['contrib']

        # allin needs to be the doc count
        # where bets and raises result in allin, add those prob dists to this
        # that will give proper probability
        go_allin = stats['actions'].get('allin', 0.01) if e.phase == e.PHASE_RIVER else 0

        # logger.info('filtered actions: {}'.format(actions))
        # ev 0 instead of none because of root node sum when not all traversed it gives error
        action_nodes = []
        for a in actions:
            node_data = {
                'stats': stats['actions'].get(a[0], 0.01),
                'action': a,
                'phase': e.phase,
                'seat': s,
                'name': p['name'],
                'traversed': 0,
                'ev': 0,
            }

            if a in ['bet', 'raise']:
                btps_and_amts = []
                total_pot = sum(pd['contrib'] for pd in e.data.values()) + e.pot
                logger.debug('pot amount for btp calcs is {}'.format(total_pot))

                # add min bet
                # todo only valid if action = 'bet', how to skip raise amount if bet
                # btps_and_amts.append(('min', contrib_short + self.engine.bb_amt))
                # logger.debug('added minimum bet of {}'.format(btps_and_amts[-1]))

                # add half pot bet
                btps_and_amts.append(('half_pot', total_pot * 0.50))
                logger.debug('added half pot bet of {}'.format(btps_and_amts[-1]))

                # add pot bet
                btps_and_amts.append(('full_pot', total_pot * 1.00))
                logger.debug('added pot bet of {}'.format(btps_and_amts[-1]))

                # add double pot bet
                btps_and_amts.append(('double_pot', total_pot * 2.00))
                logger.debug('added double pot bet of {}'.format(btps_and_amts[-1]))

                # logger.debug('stats for btp calcs is {}'.format(stats['btps'].values()))
                # todo skipping bet to percentiles
                # btps_and_amts = [(btp, int(total_pot * btp)) for btp in stats['btps'].values()]
                # logger.debug('btps_and_amts {}'.format(btps_and_amts))

                # todo skipping balance betting
                # foes balances
                # balances = [pp['balance'] - pd['contrib'] for pp, pd in zip(e.players.values(), e.data.values())
                #     if pd['status'] == 'in' and pp['name'] != p['name'] and pp['balance'] - pd['contrib'] > 0]

                # bet to maximise other stacks if hero is exactly 'in'
                if False and balances and d['status'] == 'in':
                    # minimum balance of all (incl hero)
                    min_balance = min(balance_left, *balances)
                    min_bal_btp = ('minbal', int(min_balance / e.rounds_left ** 2))
                    btps_and_amts.insert(0, min_bal_btp)
                    # logger.debug('minimum stack bet = {} for minbal {}'.format(min_bal_btp, min_balance))

                    # maximum balance of foes (but not more than hero)
                    max_balance = min(balance_left, max(balances))
                    max_bal_btp = ('maxbal', int(max_balance / e.rounds_left ** 2))
                    btps_and_amts.insert(1, max_bal_btp)
                    # logger.debug('maximum stack bet = {} for maxbal {}'.format(max_bal_btp, max_balance))

                # round bets up to a BB
                btps_and_amts = [(btp, -(amt // -self.engine.bb_amt) * self.engine.bb_amt)
                                 for btp, amt in btps_and_amts]

                betting_info = []
                amts = []
                for btp, amt in btps_and_amts:
                    if amt in amts:
                        # logger.debug('already using {}, skipping duplicate'.format(amt))
                        continue
                    if a == 'bet' and amt < e.bb_amt:
                        # logger.debug('bet cannot be less than BB {}'.format(e.bb_amt))
                        continue
                    if a == 'raise' and amt < (max_contrib * 2):
                        # logger.debug('raise cannot be less than 2x contrib  of {}'.format(max_contrib * 2))
                        continue
                    betting_info.append((btp, amt))
                    amts.append(amt)

                # logger.debug('betting info = {}'.format(betting_info))
                for btp, amt in betting_info:
                    # if amt is more than player balance, it is an allin
                    if amt >= balance_left:
                        go_allin += node_data['stats'] / len(btps_and_amts)
                        # logger.debug('not enough money to raise, going allin {} vs {}'.format(amt, balance_left))
                        continue

                    # all good, can have this bet as option (just dist its stat)
                    node_data_copy = deepcopy(node_data)
                    node_data_copy['stats'] /= len(btps_and_amts)
                    node_data_copy['action'] = '{}_{}'.format(a, btp)
                    node_data_copy['amount'] = amt
                    action_nodes.append(node_data_copy)
                    amt_prev = amt
                    # logger.debug('{} for {} <= {} * {}%'.format(a, amt, total_pot, btp))

            else:
                action_nodes.append(node_data)

        # allin will have doc counts (from stat, maybe from bets, maybe from raise)
        if go_allin:
            node_data = {
                'stats': go_allin,
                'action': 'allin',
                'phase': e.phase,
                'seat': s,
                'name': p['name'],
                'traversed': 0,
                'ev': 0,
                'amount': balance_left,
            }
            action_nodes.append(node_data)
            # logger.debug('added allin to actions with stat {}'.format(node_data['stats']))

        # scale the stats (it is currently term counts aka histogram) and it is required to be
        # a probability distribution (p~1)
        total_stats = sum(an['stats'] for an in action_nodes if an['action'] != 'fold')
        # the distribution will be fixed within the non-fold equities
        non_fold_equity = 1 - stats['actions'].get('fold', 0)
        # logger.debug('total stats equity = {} and non_fold_equity = {}'.format(total_stats, non_fold_equity))
        for action_node in action_nodes:
            identifier = '{:03d}_{}'.format(int(action_node['stats'] * 100), uuid.uuid4())
            node_tag = '{}_{}_{}'.format(action_node['action'], s, e.phase)
            if action_node['action'] != 'fold':
                action_node['stats'] = max(0.01, action_node['stats'] / total_stats * non_fold_equity)
            self.tree.create_node(identifier=identifier, tag=node_tag, parent=parent.identifier, data=action_node)
            logger.debug('new {} for {} with data {}'.format(node_tag, s, action_node))
        logger.info('{} node actions added'.format(len(action_nodes)))


class MonteCarloError(Exception):
    """Exception raised by MC"""
