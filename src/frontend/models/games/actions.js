/**
 * Action types
 */
export const SET_FB_STATUS = 'SET_FB_STATUS'


export const FB_STATUSES = {
    LOADING: 'loading',
    DONE: 'done',
}

/**
 * Action creators
 */

export const setFacebookStatus = (text) => {
    return {
        type: SET_FB_STATUS,
        status: text,
    }
}
