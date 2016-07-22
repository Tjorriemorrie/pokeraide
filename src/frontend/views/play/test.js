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
            expect(wrapper).to.have.className('play')
            expect(wrapper).to.have.className('flexcol')
            expect(wrapper.find('.strip')).to.contain.text('0 games')
            expect(wrapper.find('.main')).to.contain.text('main')
        })

        it('renders strip', () => {
            const strip = wrapper.find('.strip')
            expect(strip).to.have.className('strip')
            expect(strip).to.have.descendants('p')
            expect(strip).to.have.descendants('button')
        })

    })
}

export default play
