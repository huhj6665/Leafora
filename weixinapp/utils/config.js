/**
 * 后端 API 地址的唯一配置入口。
 *
 * 开发期允许用户在“云端连接”页保存电脑的局域网地址；正式发布仍必须
 * 使用小程序后台配置过的 HTTPS 合法域名。
 */
const DEFAULT_HOST = ''
const DEFAULT_PORT = 8000
const LAN_API_ORIGIN = ''
const ENVIRONMENTS = { devtools: LAN_API_ORIGIN, phone: LAN_API_ORIGIN }
const CURRENT_ENV = 'phone'
const API_PREFIX = '/api'
const SERVER_CONFIG_KEY = 'tld_api_server'
const LEGACY_OVERRIDE_KEY = 'api_base_url'
const VERIFIED_SERVER_KEY = 'tld_verified_server'

/** 接受 origin 或带 /api 的地址，统一归一化为不含 /api 的 origin。 */
function normalizeBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '').replace(/\/api$/i, '')
}

function normalizeHost(value) {
  return String(value || '').trim().toLowerCase().replace(/\.$/, '')
}

function parseIpv4(host) {
  if (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(host)) return null
  const parts = host.split('.').map(Number)
  if (parts.some((part) => part < 0 || part > 255)) return null
  return parts
}

function isPrivateIpv4(parts) {
  return parts[0] === 10 ||
    (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
    (parts[0] === 192 && parts[1] === 168)
}

function validateHost(value) {
  const host = normalizeHost(value)
  if (!host) return { ok: false, error: '请输入开发电脑的局域网 IPv4 或主机名' }
  if (host === 'localhost' || host === '0.0.0.0' || /^127\./.test(host)) {
    return { ok: false, error: '手机中的 localhost/127.0.0.1 指向手机自身，不能用于连接开发电脑' }
  }
  if (/^https?:\/\//i.test(host) || /[/:]/.test(host)) {
    return { ok: false, error: '这里只填写主机地址，不要包含 http://、端口或路径' }
  }

  const ipv4 = parseIpv4(host)
  if (ipv4) {
    if (!isPrivateIpv4(ipv4)) {
      return { ok: false, error: '开发调试仅接受常见私有 IPv4（10.x、172.16-31.x、192.168.x）' }
    }
    return { ok: true, value: ipv4.join('.'), kind: 'ipv4' }
  }

  // 允许 Windows 单标签主机名或 mDNS 的 .local 主机名；不接受公网域名。
  if (!/^\d+$/.test(host) && /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.local)?$/i.test(host)) {
    return { ok: true, value: host, kind: 'hostname' }
  }
  return { ok: false, error: '主机地址格式无效，请填写私有 IPv4、电脑主机名或 .local 主机名' }
}

function validatePort(value) {
  const text = String(value == null ? '' : value).trim()
  if (!/^\d+$/.test(text)) return { ok: false, error: '端口必须是 1 到 65535 的整数' }
  const port = Number(text)
  if (port < 1 || port > 65535) return { ok: false, error: '端口必须在 1 到 65535 之间' }
  return { ok: true, value: port }
}

function buildServerConfig(hostValue, portValue) {
  const hostResult = validateHost(hostValue)
  if (!hostResult.ok) return hostResult
  const portResult = validatePort(portValue)
  if (!portResult.ok) return portResult
  const origin = 'http://' + hostResult.value + ':' + portResult.value
  return {
    ok: true,
    host: hostResult.value,
    port: portResult.value,
    origin,
    apiBaseUrl: origin + API_PREFIX,
    healthUrl: origin + API_PREFIX + '/health',
  }
}

function parseBaseUrl(value) {
  const origin = normalizeBaseUrl(value)
  const match = /^(https?):\/\/([^/:]+)(?::(\d+))?$/i.exec(origin)
  if (!match) return null
  const defaultPort = match[1].toLowerCase() === 'https' ? 443 : 80
  return { host: match[2].toLowerCase(), port: Number(match[3] || defaultPort), origin }
}

function getCurrentServerConfig() {
  const saved = wx.getStorageSync(SERVER_CONFIG_KEY)
  if (saved && typeof saved === 'object') {
    const result = buildServerConfig(saved.host, saved.port)
    if (result.ok) return Object.assign(result, { source: 'storage', isDefault: result.origin === LAN_API_ORIGIN })
  }

  // 兼容旧版本开发者工具中手工写入的覆盖项，保存新配置后会移除。
  const legacy = wx.getStorageSync(LEGACY_OVERRIDE_KEY)
  const parsedLegacy = legacy && parseBaseUrl(legacy)
  if (parsedLegacy) {
    return Object.assign({ ok: true, apiBaseUrl: parsedLegacy.origin + API_PREFIX, healthUrl: parsedLegacy.origin + API_PREFIX + '/health' }, parsedLegacy, {
      source: 'legacy', isDefault: parsedLegacy.origin === LAN_API_ORIGIN,
    })
  }

  return {
    ok: false, host: DEFAULT_HOST, port: DEFAULT_PORT, origin: '', apiBaseUrl: '', healthUrl: '',
    source: 'default', isDefault: true, error: '尚未配置局域网服务器',
  }
}

function saveServerConfig(host, port) {
  const result = buildServerConfig(host, port)
  if (!result.ok) return result
  wx.setStorageSync(SERVER_CONFIG_KEY, { host: result.host, port: result.port })
  wx.removeStorageSync(LEGACY_OVERRIDE_KEY)
  return Object.assign(result, { source: 'storage', isDefault: result.origin === LAN_API_ORIGIN })
}

function clearServerConfig() {
  wx.removeStorageSync(SERVER_CONFIG_KEY)
  wx.removeStorageSync(LEGACY_OVERRIDE_KEY)
  wx.removeStorageSync(VERIFIED_SERVER_KEY)
  return getCurrentServerConfig()
}

function hasExplicitServerConfig() {
  const saved = wx.getStorageSync(SERVER_CONFIG_KEY)
  if (saved && typeof saved === 'object') return buildServerConfig(saved.host, saved.port).ok
  return !!parseBaseUrl(wx.getStorageSync(LEGACY_OVERRIDE_KEY))
}

function markHealthVerified(origin, nowMs) {
  wx.setStorageSync(VERIFIED_SERVER_KEY, {
    origin: normalizeBaseUrl(origin),
    verified_at: typeof nowMs === 'number' ? nowMs : Date.now(),
  })
}

function clearHealthVerification() {
  wx.removeStorageSync(VERIFIED_SERVER_KEY)
}

function isCurrentServerVerified() {
  const verified = wx.getStorageSync(VERIFIED_SERVER_KEY)
  return !!verified && normalizeBaseUrl(verified.origin) === getBaseUrl()
}

function getBaseUrl() {
  return normalizeBaseUrl(getCurrentServerConfig().origin || ENVIRONMENTS[CURRENT_ENV])
}

function getApiBaseUrl() {
  return getBaseUrl() + API_PREFIX
}

module.exports = {
  DEFAULT_HOST,
  DEFAULT_PORT,
  ENVIRONMENTS,
  CURRENT_ENV,
  API_PREFIX,
  LAN_API_ORIGIN,
  SERVER_CONFIG_KEY,
  LEGACY_OVERRIDE_KEY,
  VERIFIED_SERVER_KEY,
  normalizeBaseUrl,
  normalizeHost,
  validateHost,
  validatePort,
  buildServerConfig,
  parseBaseUrl,
  getCurrentServerConfig,
  saveServerConfig,
  clearServerConfig,
  hasExplicitServerConfig,
  markHealthVerified,
  clearHealthVerification,
  isCurrentServerVerified,
  getBaseUrl,
  getApiBaseUrl,
}
