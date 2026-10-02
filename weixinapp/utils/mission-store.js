const ACTIVE_KEY = 'tld_active_mission'
const REQUEST_KEY = 'tld_mission_requests'

function makeClientRequestId(prefix, nowMs, randomValue) {
  const now = typeof nowMs === 'number' ? nowMs : Date.now()
  const random = typeof randomValue === 'number' ? randomValue : Math.random()
  return String(prefix || 'REQ').toUpperCase() + '_' + now.toString(36) + '_' + Math.floor(random * 0xFFFFFF).toString(36).padStart(5, '0')
}

function getRequests() { return wx.getStorageSync(REQUEST_KEY) || {} }
function getOrCreateRequestId(key, prefix) {
  const requests = getRequests()
  if (requests[key]) return requests[key]
  requests[key] = makeClientRequestId(prefix)
  wx.setStorageSync(REQUEST_KEY, requests)
  return requests[key]
}
function clearRequestId(key) {
  const requests = getRequests()
  delete requests[key]
  wx.setStorageSync(REQUEST_KEY, requests)
}
function saveActive(mission) { if (mission && mission.inspection_id) wx.setStorageSync(ACTIVE_KEY, mission) }
function getActive() { return wx.getStorageSync(ACTIVE_KEY) || null }
function clearActive() { wx.removeStorageSync(ACTIVE_KEY) }

module.exports = { ACTIVE_KEY, REQUEST_KEY, makeClientRequestId, getOrCreateRequestId, clearRequestId, saveActive, getActive, clearActive }
