import app from './app/test'
import navigation from './navigation/test'
import home from './home/test'
import play from './play/test'


const views = () => {
    describe('views', () => {
        app(),
        navigation(),
        home(),
        play()
    })
}

export default views
