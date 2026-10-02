/** 扫码凭证只保存在 JS 内存，不写入 Storage，也不进入页面 URL。 */
let entry = null
let requestScan = false
const DEFAULT_TTL_MS = 5 * 60 * 1000

function set(result, nowMs) {
  const now = typeof nowMs === 'number' ? nowMs : Date.now()
  entry = {
    result,
    // 即使扫到刚过期的码，也短时保留以便结果页明确展示“已过期”；
    // 真正 Token 状态仍由云端判定，内存条目最多保留五分钟。
    expiresAt: now + DEFAULT_TTL_MS,
  }
}

function get(nowMs) {
  if (!entry) return null
  const now = typeof nowMs === 'number' ? nowMs : Date.now()
  if (entry.expiresAt <= now) {
    entry = null
    return null
  }
  return entry.result
}

function clear() {
  entry = null
}

function setRequestScan(value) {
  requestScan = !!value
}

function consumeRequestScan() {
  const value = requestScan
  requestScan = false
  return value
}

module.exports = { set, get, clear, setRequestScan, consumeRequestScan }
