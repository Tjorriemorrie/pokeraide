import React, { Component, PropTypes } from 'react'
import { Link } from 'react-router'
require("./styles.less")


class Home extends Component {

    render() {
        let foo = 'bar'

        return <div className="home">
            <p>you are {foo}</p>
        </div>
    }

}

Home.propTypes = {

}

export default Home
