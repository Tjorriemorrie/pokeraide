import App from './app'
import Home from './home'
import play from './play/route'
require('normalize-css')


const route = {
    path: '/',
    component: App,
    indexRoute: {
        component: Home
    },
    childRoutes: [
        play,
    ]
}

export default route
