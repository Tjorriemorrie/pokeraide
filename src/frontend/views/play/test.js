import React from 'react'
import chai from 'chai'
import chaiEnzyme from 'chai-enzyme'
import { shallow } from 'enzyme'
import sinon from 'sinon'

chai.use(chaiEnzyme())
const expect = chai.expect

import { Play } from '.'


const play = () => {
    describe('<Play />', () => {
        let wrapper
        let props = {
            games: [],
        }
        beforeEach(() => {
            wrapper = shallow(<Play {...props} />)
        })

        it('renders initial state', () => {
            expect(wrapper).to.not.be.blank()
        })

    })
}

export default play
