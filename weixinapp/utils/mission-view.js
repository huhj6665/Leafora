const ACTIVE_STATUSES = ['START_REQUESTED', 'STARTING', 'RUNNING', 'RUNNING_OFFLINE', 'ENDING', 'SYNCING']
const STATUS_LABELS = {
  START_REQUESTED: '请求已提交', STARTING: '等待设备确认', RUNNING: '巡检运行中',
  RUNNING_OFFLINE: '设备离线运行', ENDING: '结束请求处理中', SYNCING: '数据同步中',
  COMPLETED: '巡检完成', FAILED: '任务失败', CANCELLED: '已取消', REJECTED: '设备已拒绝', EXPIRED: '命令已过期',
}

function normalizeMission(raw) {
  const item = raw || {}
  const reportedStatus = String(item.status || item.phase || 'START_REQUESTED').toUpperCase()
  const pendingValue = item.pending_sync_count != null ? item.pending_sync_count : item.pending_count
  const pending = pendingValue == null ? null : Number(pendingValue)
  const syncConflict = reportedStatus === 'COMPLETED' && (pending > 0 || String(item.sync_status || '').toUpperCase() === 'PENDING')
  const status = syncConflict ? 'SYNCING' : reportedStatus
  const commands = Array.isArray(item.commands) ? item.commands : []
  const command = item.command || item.latest_command || commands[commands.length - 1] || {}
  const ack = String(item.ack_status || command.status || '').toUpperCase()
  const progress = item.progress != null ? item.progress : (item.flight_status || {}).progress
  return Object.assign({}, item, {
    inspection_id: item.inspection_id || item.id || '',
    status,
    reported_status: reportedStatus,
    sync_warning: syncConflict ? '云端完成态与待同步数据不一致，仍需等待补传完成' : '',
    status_label: STATUS_LABELS[status] || status,
    ack_status: ack,
    accepted: ack === 'ACCEPTED' || ['RUNNING', 'RUNNING_OFFLINE', 'ENDING', 'SYNCING', 'COMPLETED'].indexOf(status) !== -1,
    terminal: ['COMPLETED', 'FAILED', 'CANCELLED', 'REJECTED', 'EXPIRED'].indexOf(status) !== -1,
    progress_known: progress != null && Number.isFinite(Number(progress)),
    progress_percent: progress != null && Number.isFinite(Number(progress)) ? Math.max(0, Math.min(100, Math.round(Number(progress) * 100))) : 0,
    pending_sync: Number.isFinite(pending) ? pending : null,
  })
}

function freshness(receivedAt, nowMs) {
  const stamp = Date.parse(receivedAt || '')
  if (!Number.isFinite(stamp)) return { state: 'unknown', label: '等待实时数据', ageSeconds: null }
  const seconds = Math.max(0, Math.floor(((typeof nowMs === 'number' ? nowMs : Date.now()) - stamp) / 1000))
  if (seconds <= 3) return { state: 'live', label: '实时', ageSeconds: seconds }
  if (seconds <= 10) return { state: 'delayed', label: '数据延迟', ageSeconds: seconds }
  return { state: 'interrupted', label: '链路中断', ageSeconds: seconds }
}

function canRequestEnd(status) {
  return ['RUNNING', 'RUNNING_OFFLINE'].indexOf(String(status || '').toUpperCase()) !== -1
}

module.exports = { ACTIVE_STATUSES, STATUS_LABELS, normalizeMission, freshness, canRequestEnd }
