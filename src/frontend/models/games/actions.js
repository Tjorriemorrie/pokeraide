/**
 * Action types
 */
export const CREATE_NEW_GAME = 'CREATE_NEW_GAME'
export const ACTIVATE_GAME = 'ACTIVATE_GAME'


/**
 * Action creators
 */

export const activateGame = (game) => {
    console.info('activating game...', game)
    return {
        type: ACTIVATE_GAME,
        game: game,
    }
}

export const startGame = () => {
    // console.info('startGame action creator')
    return (dispatch, getState) => {
        // console.info('thunk started')
        return fetch('game/new')
            .then(r => r.json())
            .then(r => {
                // console.info('res', r)
                return dispatch({
                    type: CREATE_NEW_GAME,
                    game: r,
                })
            })
    }
}
