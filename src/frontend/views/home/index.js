import React, { Component, PropTypes } from 'react'
import { Link } from 'react-router'


class Home extends Component {

    render() {
        console.info('[Home] render')

        let foo = 'bar'

        return <div className="home">
            <p>you are {foo}</p>
        </div>
    }

}

Home.propTypes = {

}

export default Home
