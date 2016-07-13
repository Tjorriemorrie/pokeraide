const route = {
    path: 'play',
    getComponent(nextState, callback) {
        require.ensure([], (require) => {
            callback(null, require('.').default)
        })
    }
}

export default route
