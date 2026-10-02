/** 将地址配置与登录态清理组合成可测试的原子操作。 */
function applyServerChange(config, auth, host, port) {
  const current = config.getCurrentServerConfig()
  const next = config.buildServerConfig(host, port)
  if (!next.ok) return next
  const changed = current.origin !== next.origin
  const saved = config.saveServerConfig(next.host, next.port)
  if (!saved.ok) return saved
  if (changed) {
    auth.clearSession()
    config.clearHealthVerification()
    wx.removeStorageSync('tld_active_mission')
    wx.removeStorageSync('tld_mission_requests')
  }
  return Object.assign({}, saved, { changed, sessionCleared: changed })
}

function clearServerOverride(config, auth) {
  const current = config.getCurrentServerConfig()
  const changed = current.origin !== config.LAN_API_ORIGIN
  const fallback = config.clearServerConfig()
  if (changed) {
    auth.clearSession()
    wx.removeStorageSync('tld_active_mission')
    wx.removeStorageSync('tld_mission_requests')
  }
  return Object.assign({}, fallback, { changed, sessionCleared: changed })
}

module.exports = { applyServerChange, clearServerOverride }
