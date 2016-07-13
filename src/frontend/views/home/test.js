import React from 'react'
import chai from 'chai'
import chaiEnzyme from 'chai-enzyme'
import { shallow } from 'enzyme'
import sinon from 'sinon'

chai.use(chaiEnzyme())
const expect = chai.expect

import Home from '.'


const home = () => {
    describe('<Home />', () => {
        let wrapper
        beforeEach(() => {
            wrapper = shallow(<Home />)
        })

        it('renders foo', () => {
            expect(wrapper).to.have.className('home')
        })

    })
}

export default home
