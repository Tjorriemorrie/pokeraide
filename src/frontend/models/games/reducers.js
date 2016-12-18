import { SET_GAME, SET_PLAYERS } from './actions'
import { find } from 'lodash'


export const games = (state = [], action) => {
    switch (action.type) {
        case SET_GAME:
            console.info('action game id:', action.game.id)
            const existing_game = find(state, {id: action.game.id})
            console.info('existing game:', existing_game)
            if (!existing_game) {
                console.info('adding game to games!')
                state.push(action.game)
            }
            return state
        default:
            return state
    }
}

export const game = (state = {}, action) => {
    switch (action.type) {
        case SET_GAME:
            return action.game
        case SET_PLAYERS:
            return {
                ...state,
                players: action.players
            }
        default:
            return state
    }
}