import { expect } from 'chai'
import { CREATE_NEW_GAME, startGame } from './actions'
import * as reducers from './reducers'


const games = () => {
    describe('games', () => {

        describe('actions', () => {
            it('startGame', () => {
                expect(startGame()).to.eql({
                    type: CREATE_NEW_GAME,
                })
            })
        })

        describe('reducers', () => {
            it('has initial state as empty array', () => {
                expect(reducers.games(undefined, {})).to.eql([])
            })
            it('startGame adds new game', () => {
                expect(reducers.games(undefined, {
                    type: CREATE_NEW_GAME,
                })).to.have.length(1)
            })
        })
    })
}

export default games
