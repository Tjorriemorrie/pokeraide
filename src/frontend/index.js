import React from 'react';
import ReactDOM from 'react-dom';
import {Router, Route, IndexRoute, browserHistory} from 'react-router';
import rootRoute from './views'
import { Provider } from 'react-redux'
import store from './models'


ReactDOM.render(
    <Provider store={store}>
        <Router routes={rootRoute} history={browserHistory} />
    </Provider>,
    document.getElementById('app')
);
