/** 云端接口集中封装，路径与当前 FastAPI 路由保持一致。 */
const request = require('./request')

function buildSendCodeParams(phone) { return { phone } }
function buildPhoneLoginParams(phone, code) { return { phone, code } }
function buildPhonePasswordParams(phone, password) { return { phone, password } }
function buildSetPasswordParams(phone, code, newPassword) {
  return { phone, code, new_password: newPassword }
}
function buildDevicePairingParams(data) {
  return {
    device_id: data.device_id,
    pairing_session_id: data.pairing_session_id,
    pairing_token: data.pairing_token,
  }
}
function buildWebLoginConfirmParams(data) { return { scan_token: data.scan_token } }
function buildUnbindParams(deviceId) { return { device_id: deviceId } }
function buildStartInspectionParams(fieldId, deviceId, name, clientRequestId, runMode) {
  const data = { field_id: fieldId, device_id: deviceId, client_request_id: clientRequestId }
  if (String(name || '').trim()) data.name = String(name).trim()
  if (runMode) data.run_mode = runMode
  return data
}
function buildEndInspectionParams(clientRequestId) { return { client_request_id: clientRequestId } }

const api = {
  health() { return request.request({ url: '/health', method: 'GET', timeout: 8000, auth: false }) },
  healthAt(url) { return request.request({ url, method: 'GET', timeout: 8000, auth: false }) },
  sendPhoneCode(phone) { return request.post('/auth/send-phone-code', buildSendCodeParams(phone)) },
  loginByPhone(phone, code) { return request.post('/auth/login-phone', buildPhoneLoginParams(phone, code)) },
  loginByPassword(phone, password) {
    return request.post('/auth/login-phone-password', buildPhonePasswordParams(phone, password))
  },
  sendPhonePasswordCode(phone) {
    return request.post('/auth/phone-password/send-code', buildSendCodeParams(phone))
  },
  setPassword(phone, code, newPassword) {
    return request.post('/auth/phone-password/set', buildSetPasswordParams(phone, code, newPassword))
  },
  resetPassword(phone, code, newPassword) {
    return request.post('/auth/phone-password/reset', buildSetPasswordParams(phone, code, newPassword))
  },
  getProfile() { return request.get('/user/profile') },

  confirmDevicePairing(data) {
    return request.post('/device/pairing/confirm', buildDevicePairingParams(data))
  },
  confirmWebLogin(data) {
    return request.post('/auth/qr-sessions/' + encodeURIComponent(data.login_session_id) + '/confirm', buildWebLoginConfirmParams(data))
  },
  listDevices() { return request.get('/device/list') },
  unbindDevice(deviceId) { return request.post('/device/unbind', buildUnbindParams(deviceId)) },

  // 烟田读取路径需要 Web V0.2 实现；集中在此处，业务页面不拼 URL。
  listFields() { return request.get('/fields', {}, { retries: 1 }) },
  getField(fieldId) { return request.get('/fields/' + encodeURIComponent(fieldId)) },
  createFieldMetadata(data) { return request.post('/fields', data) },

  startInspection(fieldId, deviceId, name, clientRequestId, runMode) {
    return request.request({
      url: '/inspections/start', method: 'POST',
      data: buildStartInspectionParams(fieldId, deviceId, name, clientRequestId, runMode),
      header: { 'Idempotency-Key': clientRequestId },
    })
  },
  endInspection(inspectionId, clientRequestId) {
    return request.request({
      url: '/inspections/' + encodeURIComponent(inspectionId) + '/end', method: 'POST',
      data: buildEndInspectionParams(clientRequestId),
      header: { 'Idempotency-Key': clientRequestId },
    })
  },
  getCurrentInspection() { return request.get('/inspections/current') },
  getInspection(inspectionId) { return request.get('/inspections/' + encodeURIComponent(inspectionId)) },
  getInspectionLive(inspectionId) { return request.get('/inspections/' + encodeURIComponent(inspectionId) + '/live', {}, { retries: 0 }) },
  getInspectionSpatial(inspectionId) { return request.get('/inspections/' + encodeURIComponent(inspectionId) + '/spatial', {}, { retries: 0 }) },

  listInspectionEvents(params) { return request.get('/platform/events', params || {}) },
  getInspectionEvent(inspectionId) {
    return request.get('/platform/events/' + encodeURIComponent(inspectionId))
  },
  listInspectionRecords(params) { return request.get('/inspection/list', params || {}) },
  getInspectionRecord(dataId) { return request.get('/inspection/' + encodeURIComponent(dataId)) },
  downloadImage(path) { return request.downloadAuthenticated(path) },
}

module.exports = api
module.exports.buildParams = {
  buildSendCodeParams,
  buildPhoneLoginParams,
  buildPhonePasswordParams,
  buildSetPasswordParams,
  buildDevicePairingParams,
  buildWebLoginConfirmParams,
  buildUnbindParams,
  buildStartInspectionParams,
  buildEndInspectionParams,
}
