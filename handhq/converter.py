import argparse
import arrow
import logging
import os

logger = logging.getLogger()
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s')


def main(dir):
	logger.info('start')

	dir = os.path.abspath(os.path.join(os.path.dirname(__file__), dir))
	logger.info('dir = {}'.format(dir))
	if not os.path.isdir(dir):
		raise Exception('{} is not a directory'.format(dir))

	for currentDir, subDirs, files in os.walk(dir):
		logger.info('Scanning {} files in {}'.format(len(files), currentDir))
		for df in files:
			logger.info('File found: {}'.format(df))
			with open(os.path.join(currentDir, df), 'rb') as f:
				games = f.read().strip().split('\r\n\r\n\r\n\r\n')
				parseGames(games)
			break
		break
	logger.info('end')


def parseGames(games):
	logger.info('{} games found'.format(len(games)))
	data = []
	for game in games:
		item = {
			'players': [],
			'events': [],
		}
		for row in game.split('\r\n'):
			logger.debug(row)

			# meta
			# Stage #3017243630: Holdem  No Limit $10, $2.50 ante - 2009-07-01 00:00:26 (ET)
			if row.startswith('Stage'):
				meta, timestamp = row.split(' - ')
				metas = filter(None, meta.replace(':', '').split(' '))
				item['id'] = metas[1]
				item['type'] = ' '.join(metas[2:5])
				item['blind'] = metas[5]
				if len(metas) >= 7:
					item['ante'] = metas[6]
				item['timestamp'] = arrow.get(timestamp).timestamp
				item['currency'] = {
					'symbol': '$',
					'code': 'USD',
				}
				logger.info('metas: {}'.format(metas))

			# table data
			# Table: CLEO AVE (Real Money) Seat #2 is the dealer
			elif row.startswith('Table'):
				logger.info('ignoring: {}'.format(row))
				pass

			# seats
			# Seat 2 - XrM1XlN29RxmLx3oZHhG0w ($1,515 in chips)
			elif row.startswith('Seat') and not item['events']:
				seat_info = row.replace('(', '').replace(',', '').replace('$', '').split(' ')
				player = {
					'seat': seat_info[1],
					'name': seat_info[3],
					'stack': seat_info[4],
				}
				if not len(item['players']):
					player['is_dealer'] = True
				item['players'].append(player)
				logger.info('player added: {}'.format(player))

			elif row.startswith('Total Pot'):
				rake = 0
				if ' | ' in row:
					for seg in row.split(' | '):
						if 'Rake' in seg:
							rake += float(seg.split(' ')[-1].replace('(', '').replace(')', '').replace('$', ''))
				winnings_action = next((e for e in item['events'] if e['type'] == 'winnings'), None)
				winnings_action['rake'] = rake
				logger.info('end of game (rake = {})'.format(rake))
				break

			else:
				action_item = {}

				# turns
				if '***' in row:
					if 'POCKET' in row:
						action_item['type'] = 'pockets'
					elif 'FLOP' in row:
						action_item['type'] = 'flop'
						action_item['cards'] = row.replace('[', '').replace(']', '').split(' ')[-3:]
						action_item['board'] = action_item['cards']
					elif 'TURN' in row:
						action_item['type'] = 'turn'
						action_item['cards'] = row.replace('[', '').replace(']', '').split(' ')[-1:]
						action_item['board'] = row.replace('[', '').replace(']', '').split(' ')[-4:]
					elif 'RIVER' in row:
						action_item['type'] = 'river'
						action_item['cards'] = row.replace('[', '').replace(']', '').split(' ')[-1:]
						action_item['board'] = row.replace('[', '').replace(']', '').split(' ')[-5:]
					elif 'SHOW' in row:
						action_item['type'] = 'showdown'
					else:
						continue

				# collects
				if 'Collect' in row:
					action_item['type'] = 'winnings'
					action_item['amount'] = float(row.split(' ')[2].replace('$', '').replace(',', ''))
					action_item['player_name'] = row.split(' ')[0]

				elif ' - ' in row:
					name, detail = row.split(' - ')
					action_item['player_name'] = name
					details = detail.split(' ')

					# ignore (done in sitout)
					if detail.startswith('Ante returned') or detail.startswith('return'):
						logger.info('Ignoring: {}'.format(row))
						continue

					# ante
					elif detail.startswith('Ante'):
						action_item['type'] = details[0].lower()
						action_item['amount'] = details[-1].replace('$', '')

					# fix sitout
					elif detail.startswith('sitout'):
						# fix ante made
						ante_action = next((e for e in item['events'] if e['player_name'] == name), None)
						item['events'].remove(ante_action)
						# fix player status
						player_item = next((p for p in item['players'] if p['name'] == name), None)
						player_item['is_sitting_out'] = True
						logger.info('player status fixed')
						continue

					# posts
					elif detail.startswith('Posts'):
						# small blind
						if 'small blind' in detail:
							action_item['type'] = 'sb'
							action_item['amount'] = details[-1].replace(',', '').replace('$', '')
						# big blind
						elif 'big blind' in detail:
							action_item['type'] = 'bb'
							action_item['amount'] = details[-1].replace(',', '').replace('$', '')

					# folding
					elif 'Fold' in detail:
						action_item['type'] = 'fold'

					# bets
					elif 'Bet' in detail:
						action_item['type'] = 'bet'
						action_item['amount'] = details[-1].replace(',', '').replace('$', '')

					# raises
					elif 'Raise' in detail:
						action_item['type'] = 'raise'
						action_item['amount'] = details[-3].replace(',', '').replace('$', '')
						logger.warn(row)

					# calls
					elif 'Call' in detail:
						action_item['type'] = 'call'
						action_item['amount'] = details[-1].replace(',', '').replace('$', '')

					# checks
					elif 'Check' in detail:
						action_item['type'] = 'check'

					# all-in
					elif 'All-In' in detail:
						action_item['type'] = 'all-in'
						action_item['amount'] = details[-1].replace(',', '').replace('$', '')

					# showdown
					elif 'Does not show' in detail:
						action_item['type'] = 'show'
						action_item['pocket'] = None

					# shows
					elif 'Show' in detail:
						action_item['type'] = 'show'
						action_item['pocket'] = [
							details[1].replace('[', ''),
							details[2].replace(']', ''),
						]

					# mucks
					elif 'Muck' in detail:
						action_item['type'] = 'muck'
						action_item['pocket'] = None

					else:
						raise Exception('unknown type')

				item['events'].append(action_item)
				logger.info('action: {}'.format(action_item))

		# build pots
		pots = {
			'main': {
				'called': 0,
				'uncalled': 0,
				'total': 0,
			}
		}
		for event in item['events']:
			if event['type'] in ['bet', 'raise', 'all-in']:
				pots['main']['uncalled'] += float(event['amount'])
			elif event['type'] in ['ante', 'sb', 'bb', 'call']:
				pots['main']['uncalled'] += float(event['amount'])
				pots['main']['called'] += pots['main']['uncalled']
				pots['main']['uncalled'] = 0
			elif event['type'] in ['pockets', 'flop', 'turn', 'river', 'showdown']:
				pots['main']['uncalled'] = 0
			pots['main']['total'] = pots['main']['called'] + pots['main']['uncalled']
			event['pots'] = pots
			logger.info('{}: {} => {}'.format(event['type'], event['amount'] if 'amount' in event else '-', pots))

		# logger.info('item = {}'.format(item))
		data.append(item)

		if len(data) > 15:
			break

	logger.info('{} data items'.format(len(data)))


if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-d', '--dir')
	args = parser.parse_args()
	main(**vars(args))
