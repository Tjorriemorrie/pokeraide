/**
 * Action types
 */
export const CREATE_NEW_GAME = 'CREATE_NEW_GAME'


/**
 * Action creators
 */

export const startGame = () => {
    return {
        type: CREATE_NEW_GAME,
    }
}
