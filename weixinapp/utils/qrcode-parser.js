/**
 * TLD 二维码解析与格式校验。
 * 格式正确不等于云端身份验证成功，Token 状态必须由确认接口判定。
 */
const PAIRING_TYPE = 'tld_device_pairing'
const WEB_LOGIN_TYPE = 'tld_web_login'
const PAIRING_VERSION = '2.0'
const WEB_LOGIN_VERSION = '1.0'
const SUPPORTED_VERSIONS = [PAIRING_VERSION]
const MAX_RAW_LENGTH = 4096
const LIMITS = {
  type: 64,
  version: 16,
  device_id: 128,
  pairing_session_id: 128,
  pairing_token: 512,
  login_session_id: 128,
  scan_token: 512,
  expires_at: 64,
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0
}

function readString(obj, field, label) {
  const value = obj[field]
  if (!isNonEmptyString(value)) {
    return { ok: false, error: '缺少' + label + '（' + field + '）' }
  }
  const normalized = value.trim()
  if (normalized.length > LIMITS[field]) {
    return { ok: false, error: label + '长度超出限制' }
  }
  return { ok: true, value: normalized }
}

function readExpiry(obj, nowMs) {
  const field = readString(obj, 'expires_at', '有效期')
  if (!field.ok) return field
  const timestamp = Date.parse(field.value)
  if (!Number.isFinite(timestamp)) {
    return { ok: false, error: '有效期（expires_at）格式无效' }
  }
  return {
    ok: true,
    value: field.value,
    expiresAtMs: timestamp,
    isExpired: timestamp <= (typeof nowMs === 'number' ? nowMs : Date.now()),
  }
}

function validateDevicePairing(obj, nowMs) {
  if (obj.version !== PAIRING_VERSION) {
    return { ok: false, error: '不支持的设备配对协议版本：' + (obj.version || '缺失') }
  }
  const deviceId = readString(obj, 'device_id', '设备 ID')
  if (!deviceId.ok) return deviceId
  const sessionId = readString(obj, 'pairing_session_id', '配对会话 ID')
  if (!sessionId.ok) return sessionId
  const token = readString(obj, 'pairing_token', '配对凭证')
  if (!token.ok) return token
  const expiry = readExpiry(obj, nowMs)
  if (!expiry.ok) return expiry
  return {
    ok: true,
    data: {
      kind: 'device_pairing',
      type: PAIRING_TYPE,
      version: PAIRING_VERSION,
      device_id: deviceId.value,
      pairing_session_id: sessionId.value,
      pairing_token: token.value,
      expires_at: expiry.value,
      expires_at_ms: expiry.expiresAtMs,
      is_expired: expiry.isExpired,
      format_valid: true,
    },
  }
}

function validateWebLogin(obj, nowMs) {
  if (obj.version !== WEB_LOGIN_VERSION) {
    return { ok: false, error: '不支持的 Web 登录协议版本：' + (obj.version || '缺失') }
  }
  const sessionId = readString(obj, 'login_session_id', '登录会话 ID')
  if (!sessionId.ok) return sessionId
  const token = readString(obj, 'scan_token', '扫码凭证')
  if (!token.ok) return token
  const expiry = readExpiry(obj, nowMs)
  if (!expiry.ok) return expiry
  return {
    ok: true,
    data: {
      kind: 'web_login',
      type: WEB_LOGIN_TYPE,
      version: WEB_LOGIN_VERSION,
      login_session_id: sessionId.value,
      scan_token: token.value,
      expires_at: expiry.value,
      expires_at_ms: expiry.expiresAtMs,
      is_expired: expiry.isExpired,
      format_valid: true,
    },
  }
}

function validateQrData(obj, nowMs) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return { ok: false, error: '二维码内容不是有效的 TLD 信息' }
  }
  const type = readString(obj, 'type', '类型')
  if (!type.ok) return type
  if (type.value === PAIRING_TYPE) return validateDevicePairing(obj, nowMs)
  if (type.value === WEB_LOGIN_TYPE) return validateWebLogin(obj, nowMs)
  return { ok: false, error: '不是受支持的 TLD 二维码' }
}

function validatePairingData(obj, nowMs) {
  if (!obj || obj.type !== PAIRING_TYPE) {
    return { ok: false, error: '不是 TLD 设备配对二维码' }
  }
  return validateDevicePairing(obj, nowMs)
}

function parseQrContent(raw, nowMs) {
  if (typeof raw !== 'string' || !raw.trim()) {
    return { ok: false, error: '扫码内容为空' }
  }
  const text = raw.trim()
  if (text.length > MAX_RAW_LENGTH) {
    return { ok: false, error: '二维码内容过长，无法解析' }
  }
  let obj
  try {
    obj = JSON.parse(text)
  } catch (e) {
    return { ok: false, error: '二维码内容不是合法 JSON' }
  }
  return validateQrData(obj, nowMs)
}

function parseScene() {
  return { ok: false, error: '官方小程序码 scene 解析尚未接入' }
}

module.exports = {
  PAIRING_TYPE,
  WEB_LOGIN_TYPE,
  PAIRING_VERSION,
  WEB_LOGIN_VERSION,
  SUPPORTED_VERSIONS,
  parseQrContent,
  parseScene,
  validateQrData,
  validatePairingData,
}
