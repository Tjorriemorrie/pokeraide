import React, { Component, PropTypes } from 'react'
import { IndexLink, Link } from 'react-router'
require("./styles.less")


class Navigation extends Component {

    render() {
        return <nav>
            <div><IndexLink activeClassName="active" to="/">Home</IndexLink></div>
            <div><Link activeClassName="active" to="play">Play</Link></div>
        </nav>
    }

}

Navigation.propTypes = {

}

export default Navigation
