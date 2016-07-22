import { CREATE_NEW_GAME } from './actions'


export const games = (state = [], action) => {
    switch (action.type) {
        case CREATE_NEW_GAME:
            state.push({
                id: 'foo',
                started_at: new Date(),
            })
            return state
        default:
            return state
    }
}
