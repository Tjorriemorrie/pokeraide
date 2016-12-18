import tarfile
from pprint import pprint
import os

# extract
data = {'players': {}}
with tarfile.open("tourney.199505.tgz") as t:
	for name in t.getnames():
		if 'pdb/pdb.' in name:
			data['players'][name.split('.')[-1]] = t.extractfile(t.getmember(name)).read().strip().split('\n')
	data['hdb'] = t.extractfile(t.getmember('tourney/199505/hdb')).read().strip().split('\n')
	data['hroster'] = t.extractfile(t.getmember('tourney/199505/hroster')).read().strip().split('\n')
# pprint(data)

# build
builds = []
for row in data['hdb']:
	pprint(row)
	timestamp, dealer, hand_num, num_play, flop, turn, river, showdn = row.split()[:8]
	board = row.split()[8:]
	# pprint(board)

	# find roster
	for _ in data['hroster']:
		if timestamp in _:
			roster = _
			break
	timestamp, num_players = roster.split()[:2]
	player_names = roster.split()[2:]
	pprint(player_names)

	# find players
	players = []
	for player in player_names:
		for _ in data['players'][player]:
			if timestamp in _:
				print _
				players.append(_.split())
				break
	players.sort(lambda x, y: 1 if x[3] > y[3] else -1)
	pprint(players)

	item = {
		'timestamp': int(timestamp),
		'players': player_names,
		'game_num': hand_num,
		'rounds': {},
	}

	# preflop
	item['rounds']['preflop'] = {
		'num_players': int(num_play),
		'pot_start': 0.,
		'actions': [],
	}
	r = 0
	o = 0
	n = item['rounds']['preflop']['num_players']
	while o < n:
		for i in range(n):
			actions = players[i][4]
			# pprint(len(actions))
			if len(actions) <= r:
				o += 1
			else:
				o = 0
				# pprint('actions {} r {}'.format(actions, r))
				action = actions[r]
				item['rounds']['preflop']['actions'].append(action)
		r += 1

	# flop
	item['rounds']['flop'] = {
		'num_players': int(flop.split('/')[0]),
		'pot_start': float(flop.split('/')[1]),
		'actions': [],
	}
	r = 0
	o = 0
	n = item['rounds']['flop']['num_players']
	while o < n:
		for i in range(n):
			actions = players[i][5]
			# pprint(len(actions))
			if len(actions) <= r:
				o += 1
			else:
				o = 0
				# pprint('actions {} r {}'.format(actions, r))
				action = actions[r]
				item['rounds']['flop']['actions'].append(action)
		r += 1

	# turn
	item['rounds']['turn'] = {
		'num_players': int(turn.split('/')[0]),
		'pot_start': float(turn.split('/')[1]),
		'actions': [],
	}
	r = 0
	o = 0
	n = item['rounds']['turn']['num_players']
	while o < n:
		for i in range(n):
			actions = players[i][6]
			# pprint(len(actions))
			if len(actions) <= r:
				o += 1
			else:
				o = 0
				# pprint('actions {} r {}'.format(actions, r))
				action = actions[r]
				item['rounds']['turn']['actions'].append(action)
		r += 1

	# river
	item['rounds']['river'] = {
		'num_players': int(river.split('/')[0]),
		'pot_start': float(river.split('/')[1]),
		'actions': [],
	}
	r = 0
	o = 0
	n = item['rounds']['river']['num_players']
	while o < n:
		for i in range(n):
			actions = players[i][7]
			# pprint(len(actions))
			if len(actions) <= r:
				o += 1
			else:
				o = 0
				# pprint('actions {} r {}'.format(actions, r))
				action = actions[r]
				item['rounds']['river']['actions'].append(action)
		r += 1

	# showdn
	item['rounds']['showdn'] = {
		'num_players': int(showdn.split('/')[0]),
		'pot_start': float(showdn.split('/')[1]),
	}

	builds.append(item)

	if len(builds) > 0:
		break

pprint(builds)
