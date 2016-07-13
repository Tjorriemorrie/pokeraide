import app from './app/test'
import navigation from './navigation/test'
import home from './home/test'


const views = () => {
    describe('views', () => {
        app(),
        navigation(),
        home()
    })
}

export default views
