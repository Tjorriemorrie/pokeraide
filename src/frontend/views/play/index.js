import React, { Component, PropTypes } from 'react'
import { connect } from 'react-redux'
require("./styles.less")
import { isEmpty, range } from 'lodash'
import {
    startGame, addPlayer, removePlayer, setBalance, setSitOut, setStatus, setCards, setDealer
} from './../../models/games/actions'



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
                            <span key={game.id}>{game.id}</span>
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

        console.info('renderMain', game)
        let game_body = <p>todo</p>
        if (game.status == 'setup') {
            game_body = this.renderSetup()
        } else if (game.status == 'preflop') {
            game_body = this.renderPreFlop()
        }

        return (
            <div className="main">
                <p><small>[{game.status}]</small>Game #{game.id}</p>
                {this.renderPlayers()}
                {game_body}
            </div>
        )
    }

    renderPlayers() {
        const { game, addPlayer, removePlayer, setBalance, setSitOut, setCards, setDealer } = this.props
        console.info('renderPlayers', game.players)

        let add_player = null
        if (game.status == 'setup') {
            add_player = <div>
                <form onSubmit={e => {e.preventDefault(); addPlayer(e.target)}}>
                    <p><input type="text" name="name" /></p>
                    <p><input type="number" name="balance" /></p>
                    <p><button type="submit">add player</button></p>
                </form>
            </div>
        }

        function renderBalance(game, player) {
            if (game.status == 'setup') {
                return <form onSubmit={e => {e.preventDefault(); setBalance(e.target)}}>
                    <input type="hidden" name="id" value={player.id} />
                    <p><input type="number" name="balance" defaultValue={player.balance} />c</p>
                </form>
            } else {
                return <p>{player.balance}c</p>
            }
        }

        function renderDealer(game, player) {
            if (game.status == 'setup') {
                if (player.is_dealer) {
                    return <span>dealer</span>
                } else {
                    return <button onClick={() => setDealer(player.id)}>make dealer</button>
                }

            }
        }

        function renderSitOut(game, player) {
            if (game.status == 'setup') {
                return <p>
                    {renderDealer(game, player)}
                    <br />
                    <button onClick={() => setSitOut(player.id, player.sit_out ? 0 : 1)}>{player.sit_out ? 'join' : 'sit out'}</button>
                    <button onClick={() => removePlayer(player.id)}>leave</button>
                </p>
            }
        }

        function renderHand(game, player) {
            if (game.status != 'setup') {
                return <form onSubmit={e => {e.preventDefault(); setCards(player.id, e.target)}}>
                    <p>
                        <input className="card" type="text" name="hold_1" maxLength="2" defaultValue={player.hold_1} />
                        <input className="card" type="text" name="hold_2" maxLength="2" defaultValue={player.hold_2} />
                    </p>
                    <p><input type="submit" /></p>
                </form>
            }
        }

        return (
            <div className="flexrow">
                {game.players.map((player, i) => {
                    return (
                        <div key={player.id}>
                            <p>Seat #{i}</p>
                            <p><small>[{player.id}]</small> {player.name}</p>
                            {renderBalance(game, player)}
                            {renderSitOut(game, player)}
                            {renderHand(game, player)}
                        </div>
                    )
                })}
                {add_player}
            </div>
        )
    }

    renderSetup() {
        const { game, setStatus } = this.props
        console.info('renderSetup')
        return (
            <div id="setup">
                <p>
                    Actions:
                    <button onClick={() => setStatus('preflop')}>deal preflop</button>
                </p>
            </div>
        )
    }

    renderPreFlop() {
        const { game, setStatus } = this.props
        console.info('renderPreFlop')
        return (
            <div id="preflop">
                <p>
                    Actions:
                    <button onClick={() => setStatus('flop')}>deal flop</button>
                    <button onClick={() => setStatus('setup')}>back to setup</button>
                </p>
            </div>
        )
    }

}

Play.propTypes = {
    game: PropTypes.object,
    games: PropTypes.array.isRequired,
    startGame: PropTypes.func.isRequired,
    addPlayer: PropTypes.func,
    removePlayer: PropTypes.func,
    setBalance: PropTypes.func,
    setSitOut: PropTypes.func,
    setStatus: PropTypes.func,
    setCards: PropTypes.func,
    setDealer: PropTypes.func,
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
        addPlayer: form => dispatch(addPlayer(form)),
        removePlayer: id => dispatch(removePlayer(id)),
        setBalance: form => dispatch(setBalance(form)),
        setSitOut: (id, sit_out) => dispatch(setSitOut(id, sit_out)),
        setStatus: status => dispatch(setStatus(status)),
        setCards: (id, form) => dispatch(setCards(id, form)),
        setDealer: id => dispatch(setDealer(id)),
    }
}

export default connect(mapStateToProps, mapDispatchToProps)(Play)
