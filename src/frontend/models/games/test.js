import { expect } from 'chai'
import { SET_FB_STATUS, FB_STATUSES, setFacebookStatus } from './actions'
import * as reducers from './reducers'


const games = () => {
    describe('games', () => {

        //describe('actions', () => {
        //    it('setFacebookStatus to done', () => {
        //        expect(setFacebookStatus(FB_STATUSES.DONE)).to.eql({
        //            type: SET_FB_STATUS,
        //            status: FB_STATUSES.DONE,
        //        })
        //    })
        //})

        describe('reducers', () => {
            it('has initial state as empty array', () => {
                expect(reducers.games(undefined, {})).to.eql([])
            })
            //it('set status', () => {
            //    expect(facebook_status(undefined, {
            //        type: SET_FB_STATUS,
            //        status: FB_STATUSES.DONE,
            //    })).to.equal(FB_STATUSES.DONE)
            //})
        })
    })
}

export default games
