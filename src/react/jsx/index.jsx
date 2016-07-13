import React from 'react';
import ReactDOM from 'react-dom';
import {Router, Route, IndexRoute, browserHistory} from 'react-router';
import App from './app.jsx';
import Home from './home.jsx';


let routes = (
    <Router>
        <Route path="/" component={App}>
            <IndexRoute component={Home} />
        </Route>
    </Router>
);

ReactDOM.render(
    <Router
        routes={routes}
        history={browserHistory}
    />,
    document.getElementById('app')
);
