import { applyMiddleware, createStore, combineReducers } from 'redux'
import thunk from 'redux-thunk'
import * as games from './games/reducers'


let middlewares = [thunk];

if (process.env.NODE_ENV !== 'production') {
    const createLogger = require(`redux-logger`);
    const logger = createLogger({
        level: 'log',
        //'log' | 'console' | 'warn' | 'error' | 'info',
        // console's level
        duration: true,
        //Boolean,
        // Print the duration of each action?
        timestamp: true,
        // Boolean,
        // Print the timestamp with each action?
        //colors: ColorsObject,
        // Object with color getters. See the ColorsObject interface.
        logger: console,
        // LoggerObject,
        // Implementation of the `console` API.
        logErrors: true,
        // Boolean,
        // Should the logger catch, log, and re-throw errors?
        //collapsed, // Takes labels boolean or optionally labels function that receives `getState` function for accessing current store state and `action` object as parameters. Returns `true` if the log group should be collapsed, `false` otherwise.
        //predicate, // If specified this function will be called before each action is processed with this middleware.
        //stateTransformer, // Transform state before print. Eg. convert Immutable object to plain JSON.
        //actionTransformer, // Transform state before print. Eg. convert Immutable object to plain JSON.
        //errorTransformer, // Transform state before print. Eg. convert Immutable object to plain JSON.
        diff: true,
        // Boolean,
        // Show diff between states.
        //diffPredicate
        // Filter function for showing states diff.'
    })
    middlewares.push(logger)
}

const reducers = {
    ...games
}

const rootReducer = combineReducers(reducers)

const store = createStore(
    rootReducer,
    applyMiddleware(...middlewares)
)

export default store
