import React from 'react';
import Navigation from './navigation.jsx';
require("./../less/main.less");


class App extends React.Component {

    componentDidMount() {
        console.info('[App] componentDidMount');
    }

    render() {
        console.info('[App] render');

        return <div>
            <Navigation />
            {this.props.children}
        </div>;
    }
}

module.exports = App;
