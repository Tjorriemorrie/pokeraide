import React from 'react';
import shallowCompare from 'react-addons-shallow-compare';
import { IndexLink, Link } from 'react-router';


class Navigation extends React.Component {

    render() {
        console.info('[Navigation] render');
        return <nav>
            <div><IndexLink activeClassName="active" to="/">Home</IndexLink></div>
        </nav>;
    }

}

module.exports = Navigation;
