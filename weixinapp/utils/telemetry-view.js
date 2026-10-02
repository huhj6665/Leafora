const { freshness } = require('./mission-view')
const EMPTY = '暂无有效数据'
const FIX = { 0: 'NO_FIX', 1: 'GPS_FIX', 2: 'DGPS', 4: 'RTK_FIXED', 5: 'RTK_FLOAT' }

function valueText(value) {
  return value == null || value === '' || typeof value === 'boolean' || !Number.isFinite(Number(value)) ? EMPTY : String(value)
}
function validCoordinate(value, limit) { return valueText(value) !== EMPTY && Math.abs(Number(value)) <= limit }

function sourceLabels(mission, field) {
  const item = mission || {}
  const map = field || {}
  const provenance = String(item.data_provenance || '').toUpperCase()
  const simulated = provenance === 'SIMULATED' || item.device_id === 'TLD_JETSON_001'
  return {
    source_label: simulated ? '模拟设备数据来源' : (provenance === 'DEVICE' || item.run_mode === 'REAL_DEVICE' ? '真实设备数据来源' : '设备数据来源未报告'),
    calibration_hint: String(map.calibration_status || '').toUpperCase() === 'SIMULATED' || map.field_id === 'FIELD_A01' || map.data_source === 'DEMO_IMPORT'
      ? '烟田底图模拟校准；真实采样不代表图片已获得真实地理坐标，不代表实测 RTK 精度。' : ('烟田底图校准：' + (map.calibration_status || '未报告')),
  }
}

function normalizeLive(result, nowMs) {
  const item = result || {}
  const raw = item.raw || {}
  const display = item.display || raw
  const live = Object.assign({}, item, display)
  // 云端平滑展示可能沿用上一有效值；最新 raw 明确 null 时不能装作仍有有效读数。
  ;['location', 'environment', 'detection', 'device_status', 'flight_status'].forEach((key) => {
    const block = Object.assign({}, raw[key] || {}, display[key] || {})
    Object.keys(raw[key] || {}).forEach((name) => {
      if (raw[key][name] == null || name === 'position_valid' || name === 'valid' || name === 'sampled_at') block[name] = raw[key][name]
    })
    live[key] = block
  })
  const loc = live.location
  if (loc.position_valid === true && (!validCoordinate(loc.latitude, 90) || !validCoordinate(loc.longitude, 180))) loc.position_valid = false
  const positionInvalid = loc.position_valid === false
  const quality = loc.fix_quality
  loc.fix_text = (loc.fix || (quality != null ? FIX[quality] || String(quality) : (loc.position_valid === true ? 'GPS_FIX' : EMPTY))) + (positionInvalid ? ' · 定位无效' : '')
  loc.rtk_text = loc.rtk || loc.rtk_status || '未报告（普通 GPS Fix 可启动）'
  loc.altitude_text = positionInvalid ? EMPTY : valueText(Object.prototype.hasOwnProperty.call(loc, 'altitude_msl_m') ? loc.altitude_msl_m : loc.altitude)
  loc.speed_text = positionInvalid ? EMPTY : valueText(Object.prototype.hasOwnProperty.call(loc, 'ground_speed_mps') ? loc.ground_speed_mps : loc.speed)
  const env = live.environment
  ;['temperature', 'humidity', 'co2', 'light'].forEach((key) => { env[key + '_text'] = valueText(env[key]) })
  live.detection.count_text = Array.isArray(live.detection.results) ? String(live.detection.results.length) : EMPTY
  live.module_hint = ['gps_fix', 'camera_status', 'inference_status'].map((key) => {
    const value = raw[key] != null ? raw[key] : (live[key] != null ? live[key] : live.device_status[key])
    return value == null ? '' : ({ gps_fix: 'GPS', camera_status: 'Camera', inference_status: 'Inference' }[key] + '：' + value)
  }).filter(Boolean).join('；')
  live.sample_hints = ['location', 'environment', 'detection'].map((key) => {
    const block = live[key]
    const fresh = freshness(block.sampled_at, nowMs)
    const name = { location: '定位', environment: '环境', detection: '识别' }[key]
    return name + '：' + (block.valid === false || block.position_valid === false ? '存在无效数据 · ' : '') + (fresh.state === 'unknown' ? '采样时间未报告' : fresh.label + ' · ' + fresh.ageSeconds + 's')
  }).join('；')
  return live
}

module.exports = { EMPTY, valueText, sourceLabels, normalizeLive }
