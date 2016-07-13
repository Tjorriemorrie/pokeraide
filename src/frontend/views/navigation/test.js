import React from 'react'
import chai from 'chai'
import chaiEnzyme from 'chai-enzyme'
import { shallow } from 'enzyme'
import sinon from 'sinon'

chai.use(chaiEnzyme())
const expect = chai.expect

import Navigation from '.'


const navigation = () => {
    describe('<Navigation />', () => {
        let wrapper
        beforeEach(() => {
            wrapper = shallow(<Navigation />)
        })

        it('renders nav', () => {
            expect(wrapper).to.have.tagName('nav')
        })

        it('renders 1 index link', () => {
            expect(wrapper.find('IndexLink')).to.have.length(1)
        })

        it('renders 1 links', () => {
            expect(wrapper).to.have.exactly(1).descendants('div')
        })

        it('has link home', () => {
            expect(wrapper.findWhere(n => n.prop('to') == '/')).to.have.length(1)
            expect(wrapper.findWhere(n => n.prop('to') == '/')).to.have.html('<a>Home</a>')
        })

    })
}

export default navigation
