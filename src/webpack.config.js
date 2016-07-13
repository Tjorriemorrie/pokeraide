var path = require('path');
var webpack = require('webpack');

module.exports = {
    entry: path.resolve(__dirname, 'react/jsx/index.jsx'),
    output: {
        path: path.resolve(__dirname, 'static/build'),
        publicPath: 'http://localhost:9898/static/build',
        filename: 'pokeraide.js'
    },
    module: {
        loaders: [
            {
                test: /\.jsx?$/,
                exclude: /(node_modules|bower_components)/,
                loaders: ['react-hot', 'babel?cacheDirectory,presets[]=react,presets[]=es2015']
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
    }
};
