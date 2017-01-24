var path = require('path');
var webpack = require('webpack');

module.exports = {
    entry: path.resolve(__dirname, 'frontend/index.js'),
    output: {
        path: path.resolve(__dirname, 'backend/static/build'),
        publicPath: 'http://localhost:9898/static/build',
        filename: '[name].js',
        chunkFilename: '[id].chunk.js'
    },
    module: {
        loaders: [
            {
                test: /\.jsx?$/,
                exclude: /(node_modules|bower_components)/,
                loaders: ['babel?cacheDirectory']
            },
            {
                test: /\.less$/,
                loader: 'style!css!less'
            }, // use ! to chain loaders
            {
                test: /\.css$/,
                loader: 'style!css'
            }
        ]
    },
    plugins: [
         new webpack.optimize.CommonsChunkPlugin({name:'commons'})
    ]
};
