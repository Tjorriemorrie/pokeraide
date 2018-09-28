from collections import deque, Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import logging
from operator import itemgetter
from queue import Queue, Empty, PriorityQueue
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor

import retrace
import shelve
import time

import sys
from treelib import Tree
import uuid

from engine.engine import Engine, ACTIONS_TO_ABBR
from es.es import ES
from pe.pe import PE


logger = logging.getLogger(__name__)


class MonteCarlo:
    N_THREADS = 1
    PERCENTILE = 100

    def __init__(self, engine=None, hero=None):
        # self.last_ev = 0
        # self.rolling_10 = deque(maxlen=10)
        # self.rolling_40 = deque(maxlen=40)
        self.ev_history = {}
        self.time_start = None
        self.duration = None
        self.queue = None
        self.leaf_path = None

        if not engine:
            # logger.info('engine not given, loading from file...')
            self.engine_checksum = None
            self.load_engine(hero)
        else:
            # logger.info('engine given')
            self.init(engine, hero)

    @property
    def current_actions(self):
        return [(c.data['action'], c.data['ev'], c.data['traversed'])
                for c in self.tree.children(self.tree.root)]

    def is_time_left(self):
        return time.time() - self.time_start < self.duration

    @retrace.retry(on_exception=(EOFError, KeyError), interval=0.1, limit=None)
    def load_engine(self, hero):
        with shelve.open(Engine.FILE) as shlv:
            if shlv['hash'] != self.engine_checksum:
                # logger.info('loading engine from file...')
                self.engine_checksum = shlv['hash']
                self.init(shlv['engine'], hero)

    def init(self, engine, hero):
        # logger.info('init state')
        self.engine = engine
        self.hero = hero or self.engine.q[0][0]
        self.hero_pocket = self.engine.data[self.hero]['hand']
        for s in self.engine.data:
            self.ev_history[s] = deque(maxlen=50)
        # logger.info('HERO is at seat {} with {}'.format(self.hero, self.hero_pocket))

        self.watched = False
        self.init_tree()

    def init_tree(self):
        """create the tree. Add a root; available action will add the first level of children"""
        # self.traversed_ceiling = 1
        self.tree = Tree()
        root = self.tree.create_node('root', identifier='root', data={'traversed': 0, 'ev': 0, 'stats': 1, 'cum_stats': 1})
        # # logger.info('tree:\n{}'.format(self.tree.show()))
        # input('new tree')

    def watch(self):
        """Runs when engine file changes. Just kicks off run for 3s sprints"""
        # logger.info('Monte Carlo watching every {}s...'.format(self.timeout))
        while True:

            # loads new engine file if checksum changed
            self.load_engine()

            # do not analyze if game finished
            if self.engine.phase in [self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG]:
                if not self.watched:
                    # logger.error('game is finished')
                    self.watched = True
                time.sleep(3)
                continue

            # do not analyze if hero does not have pocket
            if self.hero_pocket in [['__', '__'], ['  ', '  ']]:
                if not self.watched:
                    # logger.error('hero does not have a pocket')
                    self.watched = True
                time.sleep(0.5)
                continue

            # do not analyze if hero is not to play
            if self.hero != self.engine.q[0][0]:
                if not self.watched:
                    # logger.error('hero is not to act')
                    self.watched = True
                time.sleep(0.5)
                continue

            if self.is_complete:
                if not self.watched:
                    # logger.error('mc is complete')
                    self.watched = True
                time.sleep(2)
                continue

            # run a few sims
            # logger.debug('running now with timeout {}'.format(self.timeout))
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
        # logger.info('Monte Carlo started')
        total_traversions_start = sum(a[2] for a in self.current_actions)

        # cannot run if engine in showdown or gg
        if self.engine.phase in [self.engine.PHASE_SHOWDOWN, self.engine.PHASE_GG]:
            logger.warning('cannot run mc with no actions')
            return

        self.duration = duration
        self.time_start = time.time()

        self.queue = PriorityQueue()
        # threads = []
        # for _ in range(self.N_THREADS):
        #     t = MCWorker(self)
        #     # t.start()
        #     threads.append(t)

        # self.traversed_focus = 0
        leaves = self.tree.paths_to_leaves()
        # logger.debug('leaves from tree: {}'.format(len(leaves)))
        # leaves.sort(key=lambda lp: len(lp) + sum(int(lpn.split('_')[0]) for lpn in lp), reverse=True)
        # # logger.debug('{} leaves are now sorted by formula'.format(len(leaves)))
        # logger.debug('{}'.format(json.dumps(leaves[:3], indent=4, default=str)))
        # leaves.sort(key=len)
        # logger.debug('{} leaves are now sorted by length'.format(len(leaves)))
        # logger.debug('{}'.format(json.dumps(leaves[:3], indent=4, default=str)))
        # leaves.sort(key=lambda lp: int(lp[-1][:3]), reverse=True)
        # logger.debug('{} leaves are now sorted by rank'.format(len(leaves)))
        # logger.error(json.dumps(leaves, indent=4, default=str))
        # input('>>')
        for leaf_path in leaves:
            node = self.tree[leaf_path[-1]]
            item = (
                1 - node.data['cum_stats'],
                leaf_path,
            )
            self.queue.put(item)

        # for t in threads:
        #     t.start()
        #
        # for t in threads:
        #     t.join()
        #     if t.error:
        #         raise Exception().with_traceback(t.error[2])

        while self.is_time_left() and not self.queue.empty():
            priority, self.leaf_path = self.queue.get_nowait()
            self.run_item(self.leaf_path)

        if self.queue.empty():
            logger.info(f'Everything was processed in queue!')

        total_traversions_end = sum(a[2] for a in self.current_actions)
        if total_traversions_end <= total_traversions_start:
            logger.warning(f'No new traversion added to {total_traversions_start}')

    def run_item(self, path):
        # logger.debug('running this path: {}'.format(path))
        e = deepcopy(self.engine)
        e.mc = True
        """To calculate the investment for the loss EV, the total amounts used till end is required. Cannot
         use final player balance on engine as that might have winnings allocated to it by the engine. Instead
         the difference from all the new matched bets from the current matched bets will be used.
         Need to add current contrib
        """
        e.matched_start = e.data[self.hero]['matched'] + e.data[self.hero]['contrib']
        # logger.info('hero starting with matched = {} from {} + {}'.format(
        #     e.matched_start, e.data[self.hero]['matched'], e.data[self.hero]['contrib']))

        # self.tree.show()
        self.fast_forward(e, path)
        # logger.info('{}'.format('-' * 200))
        # input('check item')

    def show_best_action(self):
        """Calculates best action on root"""
        # logger.error("\n\n")
        sum_traversed = 0
        delta = 0
        max_ev = float('-inf')
        action = None
        amount = None
        for nid in self.tree[self.tree.root].fpointer:
            child = self.tree[nid]
            # logger.debug('{} {}'.format(child.tag, child.data))
            dat = child.data
            sum_traversed += dat['traversed']
            # logger.error('{} @{} => {}'.format(dat['action'], dat['traversed'], round(dat['ev'], 4)))

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
        # # logger.error('deq: {}'.format(list(self.convergence['deq'])))

        # logger.error('')
        # logger.error('Timeout: {}'.format(round(self.timeout, 1)))
        # logger.error('Traversed: {}'.format(sum_traversed))
        deq_cnts = Counter(list(self.convergence['deq']))
        # # logger.error('deq: {}'.format(deq_cnts.most_common()))

        # logger.error('{}% for {}'.format(
            # 100 * sum(dq == deq_list[-1] for dq in deq_list[:-1]) // (len(deq_list) - 1)
            # 100 * (deq_cnts.most_common()[0][1] - deq_cnts.most_common()[1][1]) // self.convergence_size
            # if len(deq_cnts) > 1 else 100 * len(self.convergence['deq']) // self.convergence_size,
            # deq_cnts.most_common()[0][0]
        # ))

    def fast_forward(self, e, path):
        """Do actions on engine till the leaf is reached. Need to do available_actions before
        every DO

        First check if the leave is already processed, then skip this path. When the leaf is reached
        then process from that node.

        Remember to send through only the first letter for the action.

        Then update the nodes from this leaf back up the tree
        """
        # logger.info('Fast forwarding {} nodes'.format(len(path)))

        if len(path) == 1:
            # logger.info('processing root for first time')
            self.process_node(e, self.tree[path[0]])
            return

        leaf_node = self.tree[path[-1]]
        # logger.debug('checking if last node has been processed:')
        # logger.debug('last node leaf {} has node data {}'.format(leaf_node.tag, leaf_node.data))
        if leaf_node.data['traversed']:
            # logger.info('This leaf node ({}) above focus level {}'.format(leaf_node.tag, self.traversed_focus))
            # can happen as all actions are added, but then one was chosen to continue on
            # and that path for that action wasn't removed from the queue
            return

        for nid in path[1:]:
            node = self.tree[nid]
            # logger.debug('fast forwarding action for node {}'.format(node.tag))
            e.available_actions()
            cmd = [node.data['action'][0]]
            if 'amount' in node.data:
                cmd.append(node.data['amount'])
                # logger.debug('Adding bet value of {}'.format(node.data['amount']))
            # logger.debug('Executing path action {} for {}'.format(cmd, node.tag))
            # logger.debug('Executing path action {} with data {}'.format(cmd, node.data))
            e.do(cmd)

            if node.is_leaf():
                # logger.debug('{} is a leaf node, processing next...'.format(node.tag))
                self.process_node(e, node)

                logger.info('nodes processed, now updating nodes that were fast forwarded')
                for processed_nid in reversed(path[1:]):
                    processed_node = self.tree[processed_nid]
                    self.update_node(processed_node)

        self.ev_history[self.engine.s].append(sum(a[1] for a in self.current_actions))

    def process_node(self, e, n):
        """Process node
        Get actions available for node
        Pick action to traverse with UCT
        Process action selected
        Return EV
        """
        # logger.info('processing node {} with data {}'.format(n.tag, n.data))

        # this node is the hero folding (to prevent this being processed as leaf)
        # was created with other children (but not most probable at that time to be proc as child)
        # if hero folding, then make this node a leaf node with fold eq
        # exiting before adding children alleviates the need to remove the immediately again thereafter
        # bug: cannot use engine.q as it already rotated after taking action getting here
        if not n.is_root() and n.data['action'] == 'fold' and self.hero == n.data['seat']:
            winnings, losses = self.net(e)
            result = {
                'ev': losses,
                'traversed': 1,
            }
            # logger.info('hero has folded this node given: {}'.format(result))
            n.data.update(result)
            # logger.info('node data after fold: {}'.format(n.data))
            return

        # add the children of the node
        if not n.fpointer:
            self.add_actions(e, n)

        # this node is a leaf (no more actions to take!)
        # either the game finished and we have winner and pot
        # or we have to use pokereval.winners
        if n.is_leaf():
            # logger.info('node {} is the final action in the game'.format(n.tag))
            # winner given (easy resolution)
            if e.winner:
                # logger.debug('engine gave winner {}'.format(e.winner))
                winnings, losses = self.net(e)
                ev = winnings if self.hero in e.winner else losses
            # else if the winner is unknown
            # then calculate winners and use
            # percentage of hero as amt
            else:
                if 'in' not in e.data[self.hero]['status']:
                    # hero fold is handled before in method
                    # and thus for equities calc it is just 0
                    # logger.debug('Hero {} is not in game'.format(self.hero))
                    ev = 0
                else:
                    winnings, losses = self.net(e)
                    # equities = PE.showdown_equities(e)
                    equities = self.get_showdown_equities(e)
                    ev_pos = winnings * equities[self.hero]
                    # logger.debug('ev_pos = {} from winnings {} * eq {}'.format(ev_pos, winnings, equities[self.hero]))
                    ev_neg = losses * (1 - equities[self.hero])
                    # logger.debug('ev_neg = {} from losses {} * -eq {}'.format(ev_neg, losses, (1 - equities[self.hero])))
                    ev = ev_pos + ev_neg
                    logger.info('Net EV: {} from {} + {}'.format(ev, ev_pos, ev_neg))
            result = {
                'ev': ev,
                'traversed': 1,
            }
            # logger.info('{} leaf has result {}'.format(n.tag, result))
            n.data.update(result)
            return

        # node is all good (not leaf (has children) and not hero folding)
        # get child actions and process most probable action
        a_node = self.most_probable_action(n)
        action = a_node.data['action']
        # logger.info('taking next child node action {}'.format(action))

        # if it is hero and he folds,
        # it is not necessarily an immediate ZERO equity
        # since my previous contrib needs to be added to the pot (i.e. contribs after starting mc)
        # i.e. make this a leaf node implicitly
        # no child nodes to remove for fold
        if action == 'fold' and self.hero == a_node.data['seat']:
            winnings, losses = self.net(e)
            result = {
                'ev': losses,
                'traversed': 1,
            }
            # logger.info('hero has folded the child node selected: {}'.format(result))
            a_node.data.update(result)
            # logger.info('a_node data after: {}'.format(a_node.data))

        # else we must process the node
        else:
            # logger.info('taking action {} and processing that node'.format(action))
            cmd = [action[0]]
            if 'amount' in a_node.data:
                cmd.append(a_node.data['amount'])
                # logger.debug('Adding bet value of {}'.format(a_node.data['amount']))
            e.do(cmd)
            self.process_node(e, a_node)

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
        is_hero = node.data.get('seat') == self.hero
        # logger.debug('is hero? {}'.format(is_hero))

        # it will traverse back up to the root
        # root can be skipped
        if node.is_root():
            # input('hero {} node data {}'.format(self.hero, node.data.get('seat')))
            # if is_hero:
            #     self.rolling_10.append(abs(self.last_ev))
            #     self.rolling_40.append(abs(self.last_ev))
            #     logger.debug('Added {} ev to collection'.format(self.last_ev))
            #     input('Added {} ev to collection'.format(self.last_ev))
            # logger.debug('reached the root')
            # self.update_ev_change()
            return

        # fast forwarding will send here, just ignore node if leaf
        if node.is_leaf():
            # logger.debug('not updating {}: it is final game result (no leaf nodes)'.format(node.tag))
            # logger.debug('not updating {}: final data {}'.format(node.tag, node.data))
            return

        depth = self.tree.depth(node)
        # logger.info('updating node {} at depth {}'.format(node.tag, depth))
        # logger.info('node has {} before update'.format(node.data))

        if not len(node.fpointer):
            # logger.error('node {} with {} as no children...'.format(node.tag, node.data))
            raise Exception('not necessary to process leaves')
        # logger.debug('extracting data from {} children nodes...'.format(len(node.fpointer)))

        n_ev = float('-inf') if is_hero else 0
        n_traversed = 0
        for child_nid in node.fpointer:
            child_node = self.tree[child_nid]
            # logger.debug('child node {} has {}'.format(child_node.tag, child_node.data))
            dat = child_node.data
            if not dat['traversed']:
                # logger.debug('skipping untraversed {}'.format(child_node.tag))
                continue

            # get max for hero
            if is_hero:
                # todo is this +ev dampening necessary
                # todo this should be fixed when setting for hand range
                # equities = PE.showdown_equities(self.engine)
                # n_ev = max(n_ev, dat['ev'] * equities.get(self.hero, 0))
                n_ev = max(n_ev, dat['ev'])

            # get min for foe
            else:
                # ev_adj = dat['ev'] * dat['stats']
                # logger.debug('foe min between {} and {}'.format(n_ev, ev_adj))
                # n_ev = min(n_ev, ev_adj)
                n_ev += dat['ev'] * dat['stats'] / dat['divider']

            n_traversed += dat['traversed']
            # logger.debug('added {} traversed: now have {} so far'.format(dat['traversed'], n_traversed))

        self.last_ev = node.data['ev'] - n_ev
        node.data.update({
            'ev': n_ev,
            'traversed': n_traversed,
        })
        # logger.info('now node has {} ev~{} after {}'.format(node.tag, round(n_ev, 3), n_traversed))

        if not node.data['traversed']:
            raise Exception('node cannot be untraversed')

    def net(self, e):
        """Stored the balance at the start of sim.
        Now calculate difference as player total matched contrib.
        Winnings will be less initial starting contrib.
        """
        e.gather_the_money()
        p = e.players[self.hero]
        d = e.data[self.hero]

        matched_diff = d['matched'] - e.matched_start
        # logger.debug('matched diff = {} from {} - {}'.format(matched_diff, d['matched'], e.matched_start))

        winnings = int(e.pot - matched_diff)
        # logger.debug('winnings diff = {} from pot {} less matched {}'.format(winnings, e.pot, matched_diff))

        losses = int(-matched_diff)
        # logger.info('Winnings = {} and losses = {}'.format(winnings, losses))
        return winnings, losses

    def most_probable_action(self, parent):
        """All nodes will be processed once at least but it will never happen. Just return
        the most probable node for most accurate play. Using stats fields on data
        There should not be any untraversed nodes. So first get untraversed, then sort
        and pop first one"""
        # logger.info('getting most probable action after {}'.format(parent.tag))
        children = self.tree.children(parent.identifier)
        children = [c for c in children if not c.data['traversed']]
        if not children:
            raise MonteCarloError('Cannot choose most probable action when all nodes are traversed')
        children.sort(key=lambda c: c.data['stats'], reverse=True)
        child = children[0]
        # logger.debug('{} is untraversed, returning that node for actioning'.format(child.tag))
        self.leaf_path.append(child.identifier)
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
        # logger.info('adding actions to {}'.format(parent.tag))
        actions = e.available_actions()
        s, p = e.q[0]
        d = e.data[s]
        balance_left = p['balance'] - d['contrib']

        if not actions:
            # logger.warn('no actions to add to node')
            return

        if 'gg' in actions:
            # logger.debug('no actions available, got gg')
            return

        actions.remove('hand')

        # remove fold if player can check
        if 'check' in actions:
            actions.remove('fold')
            # # logger.debug('removed fold when check available')

        # remove fold for hero
        # if s == self.hero and 'fold' in actions:
        #     actions.remove('fold')
        #     # logger.debug('removed fold from hero')

        # remove raise if player has already been aggressive
        if 'raise' in actions and any(pa['action'] in 'br' for pa in d[e.phase]):
            actions.remove('raise')
            # # logger.debug('removed raise as player has already been aggressive')

        # remove allin, but add it later with final stats (if increased from bet/raised)
        if 'allin' in actions:
            actions.remove('allin')
        # logger.debug('removed allin by default')

        # load stats (codes with counts)
        stats = ES.player_stats(e, s)
        max_contrib = max(pd['contrib'] for pd in e.data.values())
        # contrib_short = max_contrib - d['contrib']

        # allin needs to be the doc count
        # where bets and raises result in allin, add those prob dists to this
        # that will give proper probability
        go_allin = stats['actions'].get('a', 0)

        # # logger.info('filtered actions: {}'.format(actions))
        # ev 0 instead of none because of root node sum when not all traversed it gives error
        action_nodes = []
        for a in actions:
            node_data = {
                'stats': stats['actions'].get(ACTIONS_TO_ABBR[a], 0.01),
                'divider': 1,
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

                # for preflop only do 2x and 3x
                if e.phase == e.PHASE_PREFLOP:
                    btps_and_amts.append(('double', e.bb_amt * 2))
                    btps_and_amts.append(('triple', e.bb_amt * 3))
                # else do half and full pots
                else:
                    btps_and_amts.append(('half_pot', total_pot * 0.50))
                    btps_and_amts.append(('full_pot', total_pot * 1.00))
                    # round bets up to a BB
                    # btps_and_amts = [(btp, -(amt // -e.bb_amt) * e.bb_amt)
                    #                  for btp, amt in btps_and_amts]

                betting_info = []
                amts_seen = []
                for btp, amt in btps_and_amts:
                    if amt in amts_seen:
                        # logger.debug('already using {}, skipping duplicate'.format(amt))
                        continue
                    if a == 'bet' and amt < e.bb_amt:
                        # logger.debug('bet cannot be less than BB {}'.format(e.bb_amt))
                        continue
                    if a == 'raise' and amt < (max_contrib * 2):
                        # logger.debug('raise cannot be less than 2x contrib  of {}'.format(max_contrib * 2))
                        continue
                    betting_info.append((btp, amt))
                    amts_seen.append(amt)

                # change raises that cause allin
                betting_info_final = []
                for btp, amt in betting_info:
                    # if amt is more than player balance, it is an allin
                    if amt >= balance_left:
                        go_allin += node_data['stats'] / len(betting_info)
                    else:
                        betting_info_final.append((btp, amt))

                # all good, can have this bet as option
                for btp, amt in betting_info_final:
                    node_data_copy = deepcopy(node_data)
                    node_data_copy['divider'] = len(betting_info_final)
                    node_data_copy['action'] = f'{a}_{btp}'
                    node_data_copy['amount'] = amt
                    action_nodes.append(node_data_copy)

            else:
                action_nodes.append(node_data)

        # allin will have doc counts (from stat, maybe from bets, maybe from raise)
        if go_allin:
            node_data = {
                'stats': go_allin,
                'divider': 1,
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
        # Also, certain actions like fold can be removed, and the total stats is not 1
        total_stats = sum(an['stats'] / an['divider'] for an in action_nodes)
        for action_node in action_nodes:
            action_node['stats'] = max(0.01, action_node['stats'] / action_node['divider'] / total_stats)
            action_node['cum_stats'] = parent.data['cum_stats'] * action_node['stats']
            node_tag = f'{action_node["action"]}_{s}_{e.phase}'
            identifier = f'{node_tag}_{str(uuid.uuid4())[:8]}'
            self.tree.create_node(identifier=identifier, tag=node_tag, parent=parent.identifier, data=action_node)
            # logger.debug('new {} for {} with data {}'.format(node_tag, s, action_node))
            item = (
                1 - action_node['cum_stats'],
                self.leaf_path + [identifier]
            )
            self.queue.put(item)
            # logger.debug('new {} for {} with data {}'.format(node_tag, s, action_node))
        # logger.info('{} node actions added'.format(len(action_nodes)))

    def analyze_tree(self):
        """Analyze tree to inspect best action from ev"""
        # self.tree.show()

        # check all finished paths
        for path in self.tree.paths_to_leaves():

            # skip untraversed end
            last_node = self.tree[path[-1]]
            if not last_node.data['traversed']:
                logger.debug('skipping untraversed endpoint {}'.format(last_node.tag))
                continue

            # show all actions
            for nid in path:
                node = self.tree[nid]
                d = node.data
                logger.info('Node: {} ev={}'.format(node.tag, d['ev']))


        0/0
        input('$ check tree')

    def get_showdown_equities(self, e):
        """instead of using pokereval, use hs from se"""
        hss = {}
        for s, d in e.data.items():
            if 'in' in d['status']:
                hss[s] = ES.showdown_hs(e, s, percentile=self.PERCENTILE)
        # calculate for hero
        if self.hero in hss:
            d = e.data[self.hero]
            hss[self.hero] = PE.hand_strength(d['hand'], e.board, e.rivals)
        # normalize
        total = sum(hs for hs in hss.values())
        equities = {s: hs / total for s, hs in hss.items()}
        return equities


class MonteCarloError(Exception):
    """Exception raised by MC"""


# class MCWorker(Thread):
#
#     def __init__(self, mc):
#         Thread.__init__(self)
#         self.mc = mc
#         self.error = None
#         self.path = None
#         self.priority = None
#         self.leaf_path = None
#
#     def run(self):
#         try:
#             while self.mc.is_time_left() and not self.mc.queue.empty():
#                 try:
#                     self.priority, self.leaf_path = self.mc.queue.get_nowait()
#                 except Empty:
#                     return
#                 e = deepcopy(self.mc.engine)
#                 e.mc = True
#                 e.matched_start = e.data[self.mc.hero]['matched'] + e.data[self.mc.hero]['contrib']
#                 self.fast_forward(e, self.leaf_path)
#         except Exception as exc:
#             self.error = sys.exc_info()
#         logger.info(f'Thread {self} finished')
#
#     def fast_forward(self, e, path):
#         if len(path) == 1:
#             self.process_node(e, self.mc.tree[path[0]])
#             return
#
#         leaf_node = self.mc.tree[path[-1]]
#         if leaf_node.data['traversed']:
#             return
#
#         for nid in path[1:]:
#             node = self.mc.tree[nid]
#             e.available_actions()
#             cmd = [node.data['action'][0]]
#             if 'amount' in node.data:
#                 cmd.append(node.data['amount'])
#             e.do(cmd)
#
#             if node.is_leaf():
#                 self.process_node(e, node)
#                 for processed_nid in reversed(path[1:]):
#                     processed_node = self.mc.tree[processed_nid]
#                     self.update_node(processed_node)
#
#     def process_node(self, e, n):
#         # hero folded
#         if not n.is_root() and n.data['action'] == 'fold' and self.mc.hero == n.data['seat']:
#             winnings, losses = self.net(e)
#             result = {
#                 'ev': losses,
#                 'traversed': 1,
#             }
#             n.data.update(result)
#             return
#
#         # add the children of the node
#         if not n.fpointer:
#             self.add_actions(e, n)
#
#         # this node is a leaf (no more actions to take!)
#         # either the game finished and we have winner and pot
#         # or we have to use pokereval.winners
#         if n.is_leaf():
#             # logger.info('node {} is the final action in the game'.format(n.tag))
#             # winner given (easy resolution)
#             if e.winner:
#                 # logger.debug('engine gave winner {}'.format(e.winner))
#                 winnings, losses = self.net(e)
#                 ev = winnings if self.mc.hero in e.winner else losses
#             # else if the winner is unknown
#             # then calculate winners and use
#             # percentage of hero as amt
#             else:
#                 if 'in' not in e.data[self.mc.hero]['status']:
#                     # hero fold is handled before in method
#                     # and thus for equities calc it is just 0
#                     # logger.debug('Hero {} is not in game'.format(self.hero))
#                     ev = 0
#                 else:
#                     equities = PE.showdown_equities(e)
#                     # logger.debug('pokereval equities: {}'.format(equities))
#                     winnings, losses = self.net(e)
#                     ev_pos = winnings * equities[self.mc.hero]
#                     # logger.debug('ev_pos = {} from winnings {} * eq {}'.format(ev_pos, winnings, equities[self.hero]))
#                     ev_neg = losses * (1 - equities[self.mc.hero])
#                     # logger.debug('ev_neg = {} from losses {} * -eq {}'.format(ev_neg, losses, (1 - equities[self.hero])))
#                     ev = ev_pos + ev_neg
#                     # logger.info('Net EV: {} from {} + {}'.format(ev, ev_pos, ev_neg))
#             result = {
#                 'ev': ev,
#                 'traversed': 1,
#             }
#             # logger.info('{} leaf has result {}'.format(n.tag, result))
#             n.data.update(result)
#             return
#
#         # node is all good (not leaf (has children) and not hero folding)
#         # get child actions and process most probable action
#         a_node = self.most_probable_action(n)
#         action = a_node.data['action']
#         # logger.info('taking next child node action {}'.format(action))
#
#         # if it is hero and he folds,
#         # it is not necessarily an immediate ZERO equity
#         # since my previous contrib needs to be added to the pot (i.e. contribs after starting mc)
#         # i.e. make this a leaf node implicitly
#         # no child nodes to remove for fold
#         if action == 'fold' and self.mc.hero == a_node.data['seat']:
#             winnings, losses = self.net(e)
#             result = {
#                 'ev': losses,
#                 'traversed': 1,
#             }
#             # logger.info('hero has folded the child node selected: {}'.format(result))
#             a_node.data.update(result)
#             # logger.info('a_node data after: {}'.format(a_node.data))
#
#         # else we must process the node
#         else:
#             # logger.info('taking action {} and processing that node'.format(action))
#             cmd = [action[0]]
#             if 'amount' in a_node.data:
#                 cmd.append(a_node.data['amount'])
#                 # logger.debug('Adding bet value of {}'.format(a_node.data['amount']))
#             e.do(cmd)
#             self.process_node(e, a_node)
#
#         # action node has been processed, now update node
#         self.update_node(n)
#
#     def update_node(self, node):
#         """Update the node's data
#
#         If leaf, then it was already calculated during processing, and now
#         do not change it: the ev is the ev
#
#         Minimax applied, hero pick best and foe picks min after p
#
#         Traversed will stay the traversed_focus level for leaves, but for parent nodes
#         the traversed will be the number of leaves reached from that node.
#         """
#         is_hero = node.data.get('seat') == self.mc.hero
#         # logger.debug('is hero? {}'.format(is_hero))
#
#         # it will traverse back up to the root
#         # root can be skipped
#         if node.is_root():
#             # input('hero {} node data {}'.format(self.hero, node.data.get('seat')))
#             # if is_hero:
#             #     self.rolling_10.append(abs(self.last_ev))
#             #     self.rolling_40.append(abs(self.last_ev))
#             #     logger.debug('Added {} ev to collection'.format(self.last_ev))
#             #     input('Added {} ev to collection'.format(self.last_ev))
#             # logger.debug('reached the root')
#             return
#
#         # fast forwarding will send here, just ignore node if leaf
#         if node.is_leaf():
#             # logger.debug('not updating {}: it is final game result (no leaf nodes)'.format(node.tag))
#             # logger.debug('not updating {}: final data {}'.format(node.tag, node.data))
#             return
#
#         depth = self.mc.tree.depth(node)
#         # logger.info('updating node {} at depth {}'.format(node.tag, depth))
#         # logger.info('node has {} before update'.format(node.data))
#
#         if not len(node.fpointer):
#             # logger.error('node {} with {} as no children...'.format(node.tag, node.data))
#             raise Exception('not necessary to process leaves')
#         # logger.debug('extracting data from {} children nodes...'.format(len(node.fpointer)))
#
#         n_ev = float('-inf') if is_hero else 0
#         n_traversed = 0
#         for child_nid in node.fpointer:
#             child_node = self.mc.tree[child_nid]
#             # logger.debug('child node {} has {}'.format(child_node.tag, child_node.data))
#             dat = child_node.data
#             if not dat['traversed']:
#                 # logger.debug('skipping untraversed {}'.format(child_node.tag))
#                 continue
#
#             # get max for hero
#             if is_hero:
#                 # todo is this +ev dampening necessary
#                 # todo this should be fixed when setting for hand range
#                 # equities = PE.showdown_equities(self.engine)
#                 # n_ev = max(n_ev, dat['ev'] * equities.get(self.hero, 0))
#                 n_ev = max(n_ev, dat['ev'])
#                 # logger.debug('hero ev of {}'.format(n_ev))
#
#             # get min for foe
#             else:
#                 # ev_adj = dat['ev'] * dat['stats']
#                 # # # logger.debug('foe min between {} and {}'.format(n_ev, ev_adj))
#                 # n_ev = min(n_ev, ev_adj)
#                 n_ev += dat['ev'] * dat['stats']
#                 # logger.debug('foe node ev = {} from {} * {}'.format(n_ev, dat['ev'], dat['stats']))
#
#             n_traversed += dat['traversed']
#             # logger.debug('added {} traversed: now have {} so far'.format(dat['traversed'], n_traversed))
#
#         # self.last_ev = node.data['ev'] - n_ev
#         node.data.update({
#             'ev': n_ev,
#             'traversed': n_traversed,
#         })
#         # logger.info('now node has {} ev~{} after {}'.format(node.tag, round(n_ev, 3), n_traversed))
#
#         if not node.data['traversed']:
#             raise Exception('node cannot be untraversed')
#
#     def net(self, e):
#         e.gather_the_money()
#         p = e.players[self.mc.hero]
#         d = e.data[self.mc.hero]
#
#         matched_diff = d['matched'] - e.matched_start
#         winnings = int(e.pot - matched_diff)
#         losses = int(-matched_diff)
#         return winnings, losses
#
#     def most_probable_action(self, parent):
#         """All nodes will be processed once at least but it will never happen. Just return
#         the most probable node for most accurate play. Using stats fields on data
#         There should not be any untraversed nodes. So first get untraversed, then sort
#         and pop first one"""
#         # logger.info('getting most probable action after {}'.format(parent.tag))
#         children = self.mc.tree.children(parent.identifier)
#         children = [c for c in children if not c.data['traversed']]
#         if not children:
#             raise MonteCarloError('Cannot choose most probable action when all nodes are traversed')
#         children.sort(key=lambda c: c.data['stats'], reverse=True)
#         child = children[0]
#         # logger.debug('{} is untraversed, returning that node for actioning'.format(child.tag))
#         self.leaf_path.append(child.identifier)
#         return child
#
#     def add_actions(self, e, parent):
#         actions = e.available_actions()
#         s, p = e.q[0]
#         d = e.data[s]
#         balance_left = p['balance'] - d['contrib']
#
#         if not actions:
#             return
#
#         if 'gg' in actions:
#             return
#
#         actions.remove('hand')
#
#         # remove fold if player can check
#         if 'check' in actions:
#             actions.remove('fold')
#
#         # remove raise if player has already been aggressive
#         if 'raise' in actions and any(pa['action'] in 'br' for pa in d[e.phase]):
#             actions.remove('raise')
#
#         # leave allin only for river
#         # if 'allin' in actions:
#         #     actions.remove('allin')
#
#         # load stats (codes with counts)
#         stats = ES.player_stats(e, s)
#         max_contrib = max(pd['contrib'] for pd in e.data.values())
#         contrib_short = max_contrib - d['contrib']
#
#         # allin needs to be the doc count
#         # where bets and raises result in allin, add those prob dists to this
#         # that will give proper probability
#         go_allin = stats['actions'].get('allin', 0.01) if e.phase == e.PHASE_RIVER else 0
#
#         # # logger.info('filtered actions: {}'.format(actions))
#         # ev 0 instead of none because of root node sum when not all traversed it gives error
#         action_nodes = []
#         for a in actions:
#             node_data = {
#                 'stats': stats['actions'].get(a[0], 0.001),
#                 'action': a,
#                 'phase': e.phase,
#                 'seat': s,
#                 'name': p['name'],
#                 'traversed': 0,
#                 'ev': 0,
#             }
#
#             if a in ['bet', 'raise']:
#                 btps_and_amts = []
#                 total_pot = sum(pd['contrib'] for pd in e.data.values()) + e.pot
#                 # logger.debug('pot amount for btp calcs is {}'.format(total_pot))
#
#                 # add min bet
#                 # todo only valid if action = 'bet', how to skip raise amount if bet
#                 # btps_and_amts.append(('min', contrib_short + self.engine.bb_amt))
#                 # # logger.debug('added minimum bet of {}'.format(btps_and_amts[-1]))
#
#                 # add half pot bet
#                 btps_and_amts.append(('half_pot', total_pot * 0.50))
#                 # logger.debug('added half pot bet of {}'.format(btps_and_amts[-1]))
#
#                 # add pot bet
#                 btps_and_amts.append(('full_pot', total_pot * 1.00))
#                 # logger.debug('added pot bet of {}'.format(btps_and_amts[-1]))
#
#                 # add double pot bet
#                 # todo rather recreate tree than have doublepot
#                 # btps_and_amts.append(('double_pot', total_pot * 2.00))
#                 # logger.debug('added double pot bet of {}'.format(btps_and_amts[-1]))
#
#                 # # logger.debug('stats for btp calcs is {}'.format(stats['btps'].values()))
#                 # todo skipping bet to percentiles
#                 # btps_and_amts = [(btp, int(total_pot * btp)) for btp in stats['btps'].values()]
#                 # # logger.debug('btps_and_amts {}'.format(btps_and_amts))
#
#                 # todo skipping balance betting
#                 # foes balances
#                 # balances = [pp['balance'] - pd['contrib'] for pp, pd in zip(e.players.values(), e.data.values())
#                 #     if pd['status'] == 'in' and pp['name'] != p['name'] and pp['balance'] - pd['contrib'] > 0]
#
#                 # bet to maximise other stacks if hero is exactly 'in'
#                 # if balances and d['status'] == 'in':
#                 #     # minimum balance of all (incl hero)
#                 #     min_balance = min(balance_left, *balances)
#                 #     min_bal_btp = ('minbal', int(min_balance / e.rounds_left ** 2))
#                 #     btps_and_amts.insert(0, min_bal_btp)
#                 #     # # logger.debug('minimum stack bet = {} for minbal {}'.format(min_bal_btp, min_balance))
#                 #
#                 #     # maximum balance of foes (but not more than hero)
#                 #     max_balance = min(balance_left, max(balances))
#                 #     max_bal_btp = ('maxbal', int(max_balance / e.rounds_left ** 2))
#                 #     btps_and_amts.insert(1, max_bal_btp)
#                 #     # # logger.debug('maximum stack bet = {} for maxbal {}'.format(max_bal_btp, max_balance))
#
#                 # round bets up to a BB
#                 btps_and_amts = [(btp, -(amt // -e.bb_amt) * e.bb_amt)
#                                  for btp, amt in btps_and_amts]
#
#                 betting_info = []
#                 amts = []
#                 for btp, amt in btps_and_amts:
#                     if amt in amts:
#                         # logger.debug('already using {}, skipping duplicate'.format(amt))
#                         continue
#                     if a == 'bet' and amt < e.bb_amt:
#                         # logger.debug('bet cannot be less than BB {}'.format(e.bb_amt))
#                         continue
#                     if a == 'raise' and amt < (max_contrib * 2):
#                         # logger.debug('raise cannot be less than 2x contrib  of {}'.format(max_contrib * 2))
#                         continue
#                     betting_info.append((btp, amt))
#                     amts.append(amt)
#
#                 # logger.debug('betting info = {}'.format(betting_info))
#                 for btp, amt in betting_info:
#                     # if amt is more than player balance, it is an allin
#                     if amt >= balance_left:
#                         go_allin += node_data['stats'] / len(btps_and_amts)
#                         # logger.debug('not enough money to raise, going allin {} vs {}'.format(amt, balance_left))
#                         continue
#
#                     # all good, can have this bet as option (just dist its stat)
#                     node_data_copy = deepcopy(node_data)
#                     node_data_copy['stats'] /= len(btps_and_amts)
#                     node_data_copy['action'] = '{}_{}'.format(a, btp)
#                     node_data_copy['amount'] = amt
#                     action_nodes.append(node_data_copy)
#                     amt_prev = amt
#                     # logger.debug('{} for {} <= {} * {}%'.format(a, amt, total_pot, btp))
#
#             else:
#                 action_nodes.append(node_data)
#
#         # allin will have doc counts (from stat, maybe from bets, maybe from raise)
#         if go_allin:
#             node_data = {
#                 'stats': go_allin,
#                 'action': 'allin',
#                 'phase': e.phase,
#                 'seat': s,
#                 'name': p['name'],
#                 'traversed': 0,
#                 'ev': 0,
#                 'amount': balance_left,
#             }
#             action_nodes.append(node_data)
#             # logger.debug('added allin to actions with stat {}'.format(node_data['stats']))
#
#         # scale the stats (it is currently term counts aka histogram) and it is required to be
#         # a probability distribution (p~1)
#         total_stats = sum(an['stats'] for an in action_nodes if an['action'] != 'fold')
#         # the distribution will be fixed within the non-fold equities
#         non_fold_equity = 1 - stats['actions'].get('fold', 0)
#         # logger.debug('total stats equity = {} and non_fold_equity = {}'.format(total_stats, non_fold_equity))
#         for action_node in action_nodes:
#             if action_node['action'] != 'fold':
#                 action_node['stats'] = max(0.01, action_node['stats'] / total_stats * non_fold_equity)
#             action_node['cum_stats'] = parent.data['cum_stats'] * action_node['stats']
#             node_tag = f'{action_node["action"]}_{s}_{e.phase}'
#             identifier = f'{node_tag}_{str(uuid.uuid4())[:8]}'
#             self.mc.tree.create_node(identifier=identifier, tag=node_tag, parent=parent.identifier, data=action_node)
#             # logger.debug('new {} for {} with data {}'.format(node_tag, s, action_node))
#             item = (
#                 1 - action_node['cum_stats'],
#                 self.leaf_path + [identifier]
#             )
#             self.mc.queue.put(item)
#         # logger.info('{} node actions added'.format(len(action_nodes)))
