import { combineReducers, createStore } from 'redux'


let reducer = combineReducers({ visibilityFilter, todos })
let store = createStore(reducer)

store.dispatch({
    type: 'BAZ',
    text: 'baz'
})


function alterFoo(state = 'bar', action) {
    switch (action.type) {
        default:
            return state
        case 'BAZ':
            return action.text
    }
}
