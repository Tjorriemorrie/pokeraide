
## Nav:

### Day 1

 - list of recent played games.

### Day 2

 - should the games by replayable?


## Start a new game

 - at any time
 - dealer and BB should rotate auto, and players kept when 'new game' is pressed

## UI

 - show hero
 - add players
 - ignore ante

### pre-start

Requires min 2 players

Actions:

- set BB/SB
- set dealer/button
- add/remove players
- deal cards

### preflop

Hold cards get dealt to players.

Actions:

- bet/raise
- check
- fold
- afk

### flop

Board gets dealt

Actions:

- bet/raise
- check
- fold
- afk

### turn & river

Same actions as for turn & river as flop.

### showdown

If SD then handle payout, setting winner, etc


## General

- game should be marked as finished auto/manual?
- throughout play, estimates must be sent to the backend


## Hand History format

- id
- started at
- players and balances
- preflop
- flop
- turn
- river
- showdown
