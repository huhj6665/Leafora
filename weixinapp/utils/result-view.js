function formatExpiry(value) {
  const timestamp = Date.parse(value || '')
  if (!Number.isFinite(timestamp)) return value || '--'
  const date = new Date(timestamp)
  const pad = (n) => String(n).padStart(2, '0')
  return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
    ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds())
}

function maskId(value) {
  const text = String(value || '')
  if (text.length <= 8) return text
  return text.slice(0, 4) + '…' + text.slice(-4)
}

function toDisplayData(result, nowMs) {
  if (!result || !result.ok || !result.data) {
    return { ready: true, ok: false, error: (result && result.error) || '未获取到扫码结果' }
  }
  const data = result.data
  const common = {
    ready: true,
    ok: true,
    kind: data.kind,
    version: data.version,
    expiresAt: formatExpiry(data.expires_at),
    expired: Number.isFinite(data.expires_at_ms)
      ? data.expires_at_ms <= (typeof nowMs === 'number' ? nowMs : Date.now())
      : !!data.is_expired,
  }
  if (data.kind === 'device_pairing') {
    return Object.assign(common, {
      title: '确认绑定 Jetson 设备',
      deviceId: data.device_id,
      sessionIdMasked: maskId(data.pairing_session_id),
    })
  }
  return Object.assign(common, {
    title: '确认 Web 快速登录',
    sessionIdMasked: maskId(data.login_session_id),
  })
}

module.exports = { toDisplayData, formatExpiry, maskId }
