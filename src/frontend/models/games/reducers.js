import { CREATE_NEW_GAME, ACTIVATE_GAME } from './actions'


export const games = (state = [], action) => {
    switch (action.type) {
        case CREATE_NEW_GAME:
            state.push(action.game)
            return state
        default:
            return state
    }
}

export const game = (state = {}, action) => {
    switch (action.type) {
        case CREATE_NEW_GAME:
            return action.game
        default:
            return state
    }
}