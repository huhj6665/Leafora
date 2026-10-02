const RISK = {
  LOW: { label: '较低', color: '#53A96C' },
  ATTENTION: { label: '需关注', color: '#E4B64B' }, MEDIUM: { label: '需关注', color: '#E4B64B' },
  REVIEW: { label: '重点复核', color: '#E9823D' },
  HIGH: { label: '高风险', color: '#C94B45' }, CRITICAL: { label: '高风险', color: '#C94B45' },
  INSUFFICIENT: { label: '数据不足', color: '#9AA59D' },
}

function clamp(value) { return Math.max(0, Math.min(100, Number(value) || 0)) }
function validNumber(value) { return value != null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value)) }
function normalizePoint(point) {
  const item = point || {}
  const x = Object.prototype.hasOwnProperty.call(item, 'x_pct') ? item.x_pct : item.x
  const y = Object.prototype.hasOwnProperty.call(item, 'y_pct') ? item.y_pct : item.y
  if (item.position_valid === false || (item.location && item.location.position_valid === false) || !validNumber(x) || !validNumber(y)) return null
  // 新接口明确为百分比；真实 GPS 落在模拟底图外时不能强压到边缘。
  if (Object.prototype.hasOwnProperty.call(item, 'x_pct') && (Number(x) < 0 || Number(x) > 100 || Number(y) < 0 || Number(y) > 100)) return null
  // 明确无效的经纬度不能被底图百分比坐标掩盖。
  for (const key of ['latitude', 'longitude', 'lat', 'lng']) {
    if (Object.prototype.hasOwnProperty.call(item, key) && !validNumber(item[key])) return null
    if (Object.prototype.hasOwnProperty.call(item, key) && Math.abs(Number(item[key])) > (key === 'latitude' || key === 'lat' ? 90 : 180)) return null
  }
  return Object.assign({}, item, {
    x_pct: clamp(x),
    y_pct: clamp(y),
  })
}
function normalizeGrid(cell) {
  const item = cell || {}
  const point = normalizePoint(item)
  if (!point) return null
  const key = String(item.risk_level || item.level || 'INSUFFICIENT').toUpperCase()
  return Object.assign({}, item, point, {
    width_pct: clamp(item.width_pct || item.width || 10), height_pct: clamp(item.height_pct || item.height || 10),
    suspected_count: item.suspected_count != null ? item.suspected_count : (item.suspicious_count || 0),
    risk_label: (RISK[key] || RISK.INSUFFICIENT).label, risk_color: (RISK[key] || RISK.INSUFFICIENT).color,
  })
}

module.exports = { RISK, normalizePoint, normalizeGrid }
