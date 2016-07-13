import React, { Component, PropTypes } from 'react'
import { IndexLink, Link } from 'react-router'


class Navigation extends Component {

    render() {
        console.info('[Navigation] render');
        return <nav>
            <div><IndexLink activeClassName="active" to="/">Home</IndexLink></div>
        </nav>
    }

}

Navigation.propTypes = {

}

export default Navigation
