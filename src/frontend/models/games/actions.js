/**
 * Action types
 */
export const SET_GAME = 'SET_GAME'
export const SET_PLAYERS = 'SET_PLAYERS'


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
    console.info('startGame action creator')
    return (dispatch, getState) => {
        return fetch('game', {
            method: 'post'
        })
            .then(r => r.json())
            .then(r => {
                return dispatch({
                    type: SET_GAME,
                    game: r,
                })
            })
    }
}

export const addPlayer = form => {
    console.info('addPlayer', form)
    return (dispatch, getState) => {
        console.info('thunk started')
        return fetch('game/player', {
            method: 'post',
        	body: new FormData(form)
        })
            .then(r => r.json())
            .then(r => {
                console.info('res', r)
                return dispatch({
                    type: SET_PLAYERS,
                    players: r,
                })
            })
    }
}

export const removePlayer = id => {
    console.info('removePlayer action creator', id)
    return (dispatch, getState) => {
        console.info('thunk started')
        return fetch('game/player/' + id, {
            method: 'delete',
        })
            .then(r => r.json())
            .then(r => {
                console.info('res', r)
                return dispatch({
                    type: SET_PLAYERS,
                    players: r,
                })
            })
    }
}

export const setBalance = form => {
    console.info('setBalance', form)
    return (dispatch, getState) => {
        console.info('thunk started')
        return fetch('game/player/' + form.id.value, {
            method: 'patch',
        	body: new FormData(form)
        })
            .then(r => r.json())
            .then(r => {
                console.info('res', r)
                return dispatch({
                    type: SET_PLAYERS,
                    players: r,
                })
            })
    }
}

export const setSitOut = (id, sit_out) => {
    console.info('setSitOut', id, sit_out)
    return (dispatch, getState) => {
        console.info('thunk started')
        let fd = new FormData()
        fd.append('sit_out', sit_out)
        return fetch('game/player/' + id, {
            method: 'patch',
        	body: fd,
        })
            .then(r => r.json())
            .then(r => {
                console.info('res', r)
                return dispatch({
                    type: SET_PLAYERS,
                    players: r,
                })
            })
    }
}

export const setStatus = status => {
    console.info('setStatus', status)
    return (dispatch, getState) => {
        console.info('thunk started')
        let fd = new FormData()
        fd.append('status', status)
        return fetch('game/status', {
            method: 'post',
        	body: fd,
        })
            .then(r => r.json())
            .then(r => {
                console.info('res', r)
                return dispatch({
                    type: SET_GAME,
                    game: r,
                })
            })
    }
}

export const setCards = (id, form) => {
    console.info('setCards', id, form)
    return (dispatch, getState) => {
        console.info('thunk started')
        return fetch('game/player/' + id, {
            method: 'patch',
        	body: new FormData(form),
        })
            .then(r => r.json())
            .then(r => {
                console.info('res', r)
                return dispatch({
                    type: SET_PLAYERS,
                    players: r,
                })
            })
    }
}

export const setDealer = id => {
    console.info('set dealer', id)
    return (dispatch, getState) => {
        console.info('thunk started')
        return fetch('game/player/dealer/' + id, {
            method: 'POST'
        })
            .then(r => r.json())
            .then(r => {
                console.info('res', r)
                return dispatch({
                    type: SET_PLAYERS,
                    players: r,
                })
            })
    }
}
