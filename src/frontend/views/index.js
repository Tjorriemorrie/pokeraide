import App from './app'
import Home from './home'
//import aboutRoute from './about'
//import servicesRoute from './services'
//import coursesRoute from './courses'
//import resourcesRoute from './resources'
//import contactRoute from './contact'
require('normalize-css')


const route = {
    path: '/',
    component: App,
    indexRoute: {
        component: Home
    },
    childRoutes: [
    ]
}

export default route
