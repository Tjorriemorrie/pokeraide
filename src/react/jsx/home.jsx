import React from 'react';
import shallowCompare from 'react-addons-shallow-compare';
import { Link } from 'react-router';


class Home extends React.Component {

    componentDidMount() {
    }

    render() {
        console.info('[Home] render');

        let foo = 'bar';

        return <div className="home">
            <p>you are {foo}</p>
        </div>;
    }

}

module.exports = Home;
