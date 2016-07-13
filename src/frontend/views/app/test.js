import React from 'react'
import chai from 'chai'
import chaiEnzyme from 'chai-enzyme'
import { shallow } from 'enzyme'
import sinon from 'sinon'

chai.use(chaiEnzyme())
const expect = chai.expect

import App from '.'


const app = () => {
    describe('<App />', () => {
        let wrapper
        beforeEach(() => {
            wrapper = shallow(<App />)
        })

        it('renders', () => {
            expect(wrapper).to.not.be.blank()
        })

    })
}

export default app
