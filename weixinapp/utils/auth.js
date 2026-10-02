/**
 * 登录会话管理。
 *
 * 只保存后端签发的 Access Token 与用户信息。本地存在 Token 不等于已登录，
 * 最终以 /api/user/profile 的后端校验结果为准（见 request.js 与首页 verifySession）。
 */
const TOKEN_KEY = 'tld_access_token'
const USER_ID_KEY = 'tld_user_id'
const PROFILE_KEY = 'tld_user_profile'

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || ''
}

function getUserId() {
  return wx.getStorageSync(USER_ID_KEY) || null
}

function getProfile() {
  return wx.getStorageSync(PROFILE_KEY) || null
}

/**
 * 保存登录会话。
 * @param {Object} tokenData 后端登录返回：{ access_token, token_type, user_id }
 */
function saveSession(tokenData) {
  if (!tokenData || !tokenData.access_token) return false
  wx.setStorageSync(TOKEN_KEY, tokenData.access_token)
  wx.setStorageSync(USER_ID_KEY, tokenData.user_id)
  return true
}

function saveProfile(profile) {
  if (profile) {
    wx.setStorageSync(PROFILE_KEY, profile)
  }
}

function clearSession() {
  wx.removeStorageSync(TOKEN_KEY)
  wx.removeStorageSync(USER_ID_KEY)
  wx.removeStorageSync(PROFILE_KEY)
  wx.removeStorageSync('tld_active_mission')
  wx.removeStorageSync('tld_mission_requests')
}

function hasToken() {
  return !!getToken()
}

module.exports = {
  getToken,
  getUserId,
  getProfile,
  saveSession,
  saveProfile,
  clearSession,
  hasToken,
}
