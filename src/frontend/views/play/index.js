import React, { Component, PropTypes } from 'react'
import { connect } from 'react-redux'
require("./styles.less")
import { isEmpty } from 'lodash'
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
                    {games.map((game, i) => {
                        return (
                            <span key={i}>game!</span>
                        )
                    })}
                </p>
            </div>
        )
    }

    renderMain() {
        const { game } = this.props
        if (isEmpty(game)) {
            return null
        }

        console.info('game', game)
        return (
            <div className="main">
                <p>ID: {game.id}</p>
                <p>
                    Actions:
                    <button>deal</button>
                    <button>add player</button>
                </p>
                {game.players.map((player, i) => {
                    return (
                        <p key={i}>player: {player.name}</p>
                    )
                })}
            </div>
        )
    }

}

Play.propTypes = {
    game: PropTypes.object,
    games: PropTypes.array.isRequired,
    startGame: PropTypes.func.isRequired,
}


const mapStateToProps = (state, ownProps) => {
    return {
        game: state.game,
        games: state.games,
    }
}

const mapDispatchToProps = (dispatch, ownProps) => {
    return {
        startGame: () => dispatch(startGame()),
    }
}

export default connect(mapStateToProps, mapDispatchToProps)(Play)
