import React from 'react';
import ReactDOM from 'react-dom';
import {Router, Route, IndexRoute, browserHistory} from 'react-router';
import rootRoute from './views'


ReactDOM.render(
    <Router routes={rootRoute} history={browserHistory} />,
    document.getElementById('app')
);
