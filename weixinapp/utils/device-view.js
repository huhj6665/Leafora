const STANDARD_STATUSES = ['OFFLINE', 'ONLINE_NOT_READY', 'READY', 'BUSY', 'SYNCING', 'ERROR']

function reported(value) { return value == null || value === '' ? 'UNKNOWN' : String(value).trim().toUpperCase().replace(/\s+/g, '_') }
function moduleStates(item) {
  return {
    gps: reported(item.gps_fix != null ? item.gps_fix : item.gps_status),
    camera: reported(item.camera_status),
    inference: reported(item.inference_status != null ? item.inference_status : item.ai_status),
  }
}
function failed(value, gps) {
  return (gps ? ['NO_FIX', 'INVALID', 'ERROR', 'FALSE', '0', 'OFFLINE', 'UNAVAILABLE', 'FAILED', 'NOT_READY', 'NOT_STARTED', 'STARTUP', 'STARTING'] : ['ERROR', 'OFFLINE', 'UNAVAILABLE', 'FAILED', 'NOT_READY', 'NOT_STARTED', 'STARTUP', 'STARTING', 'FALSE']).indexOf(value) !== -1
}

function deriveStatus(device) {
  const item = device || {}
  // Web V2 exposes the normalized business state as `standard_state`.
  // Keep the older alias for compatibility, but do not let the numeric
  // database status field (0/1) hide the normalized value.
  const direct = String(item.standard_state || item.standard_status || (typeof item.status === 'string' ? item.status : '')).toUpperCase()
  const modules = moduleStates(item)
  // READY 摘要不能覆盖云端同时明确报告的模块故障。
  if (direct === 'READY' && (item.has_error || item.error_message)) return 'ERROR'
  if (direct === 'READY' && (failed(modules.gps, true) || failed(modules.camera) || failed(modules.inference))) return 'ONLINE_NOT_READY'
  if (STANDARD_STATUSES.indexOf(direct) !== -1) return direct
  const communication = String(item.communication_status || '').toUpperCase()
  const operating = String(item.operating_status || '').toUpperCase()
  if (communication !== 'ONLINE') return 'OFFLINE'
  if (operating === 'ERROR' || item.has_error) return 'ERROR'
  if (operating === 'SYNCING') return 'SYNCING'
  if (['RUNNING', 'BUSY', 'STARTING', 'ENDING'].indexOf(operating) !== -1) return 'BUSY'
  if (failed(modules.gps, true) || failed(modules.camera) || failed(modules.inference)) return 'ONLINE_NOT_READY'
  return operating === 'READY' || item.ready === true ? 'READY' : 'ONLINE_NOT_READY'
}

const LABELS = {
  OFFLINE: '离线', ONLINE_NOT_READY: '在线未就绪', READY: '可开始',
  BUSY: '任务中', SYNCING: '同步中', ERROR: '异常',
}

function unavailableReason(device, status) {
  const item = device || {}
  if (status === 'OFFLINE') return '设备离线，请检查网络和电源'
  if (status === 'BUSY') return '设备已有进行中的任务'
  if (status === 'SYNCING') return '设备正在同步上一任务数据'
  if (status === 'ERROR') return item.error_message || '设备报告异常，请先排查'
  const modules = moduleStates(item)
  if (failed(modules.gps, true)) return '尚未获得普通 GPS Fix（' + modules.gps + '）'
  if (failed(modules.camera)) return '相机未就绪（' + modules.camera + '）'
  if (failed(modules.inference)) return '识别服务未就绪（' + modules.inference + '）'
  return '设备在线，但启动前检查尚未全部通过'
}

function normalizeDevice(device) {
  const status = deriveStatus(device)
  const id = (device && device.device_id) || ''
  return Object.assign({}, device || {}, {
    display_name: (device && (device.device_name || device.name)) || id || '未命名设备',
    standard_state: status,
    standard_status: status,
    status_label: LABELS[status],
    selectable: status === 'READY',
    unavailable_reason: status === 'READY' ? '' : unavailableReason(device, status),
    is_simulated: id === 'TLD_JETSON_001' || String((device && device.data_provenance) || '').toUpperCase() === 'SIMULATED',
  })
}

function buildPreflight(device) {
  const item = device || {}
  const status = deriveStatus(item)
  const modules = moduleStates(item)
  const gps = modules.gps
  const serverReady = status === 'READY'
  const gpsReported = gps !== 'UNKNOWN'
  const camera = modules.camera
  const inference = modules.inference
  const checks = [
    { key: 'cloud', label: '云端连接', ok: true, value: '已连接' },
    { key: 'device', label: '设备在线', ok: status !== 'OFFLINE', value: status === 'OFFLINE' ? '离线' : '在线' },
    { key: 'gps', label: 'GPS Fix', ok: gpsReported ? !failed(gps, true) : serverReady, value: gpsReported ? gps : (serverReady ? '云端已确认（未提供模块明细）' : '未报告') },
    { key: 'camera', label: '相机', ok: camera === 'UNKNOWN' ? serverReady : !failed(camera), value: camera === 'UNKNOWN' && serverReady ? '云端已确认（未提供模块明细）' : camera },
    { key: 'inference', label: '识别服务', ok: inference === 'UNKNOWN' ? serverReady : !failed(inference), value: inference === 'UNKNOWN' && serverReady ? '云端已确认（未提供模块明细）' : inference },
    { key: 'storage', label: '存储空间', ok: Number(item.storage_usage || 0) < 95, value: item.storage_usage == null ? '未报告' : item.storage_usage + '%' },
  ]
  const blocking = checks.filter((check) => !check.ok && check.key !== 'cloud')
  return { checks, ready: status === 'READY' && blocking.length === 0, rtk_hint: item.rtk_status || '普通 GPS Fix 可开始；RTK 只影响精度' }
}

module.exports = { STANDARD_STATUSES, deriveStatus, normalizeDevice, buildPreflight }
