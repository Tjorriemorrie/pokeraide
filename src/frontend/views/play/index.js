import React, { Component, PropTypes } from 'react'
import { connect } from 'react-redux'
require("./styles.less")
//import { FB_STATUSES } from './../../../models/facebook/actions'


export class Play extends Component {

    render() {
        let { games } = this.props

        return <div className="flexcol">
            <div>
                <p>{games.length} games</p>
            </div>
            <div>
                <p>main</p>
            </div>
        </div>
    }

}

Play.propTypes = {
    games: PropTypes.array.isRequired,
}


const mapStateToProps = (state, ownProps) => {
    return {
        games: state.games,
    }
}

const mapDispatchToProps = (dispatch, ownProps) => {
    return {
    }
}

export default connect(mapStateToProps, mapDispatchToProps)(Play)
