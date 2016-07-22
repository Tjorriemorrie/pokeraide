import React, { Component, PropTypes } from 'react'
import { connect } from 'react-redux'
require("./styles.less")
import { startGame } from './../../models/games/actions'


export class Play extends Component {

    render() {
        return (
            <div className="play flexcol">
                {this.renderStrip()}
                {this.renderMain()}
            </div>
        )
    }

    renderStrip() {
        let { games, startGame } = this.props

        return (
            <div className="strip">
                <p>
                    <button onClick={() => startGame()}>New Game</button>
                    <span className="count">{games.length} games</span>
                    {games.map(game => {
                        return (
                            <span>game!</span>
                        )
                    })}
                </p>
            </div>
        )
    }

    renderMain() {
        return (
            <div className="main">
                <p>main</p>
            </div>
        )
    }

}

Play.propTypes = {
    games: PropTypes.array.isRequired,
    startGame: PropTypes.func.isRequired,
}


const mapStateToProps = (state, ownProps) => {
    return {
        games: state.games,
    }
}

const mapDispatchToProps = (dispatch, ownProps) => {
    return {
        startGame: () => dispatch(startGame()),
    }
}

export default connect(mapStateToProps, mapDispatchToProps)(Play)
