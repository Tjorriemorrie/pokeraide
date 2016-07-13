import React, { Component, PropTypes } from 'react'
import Navigation from './../navigation'
require("./styles.less");


class App extends Component {

    render() {
        let { children } = this.props

        return <div className="background">
            <Navigation />
            {children}
        </div>
    }
}

App.propTypes = {
    children: PropTypes.node.isRequired,
}

export default App
