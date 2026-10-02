const { normalizeMission } = require('./mission-view')
const CURRENT_STATUSES = ['CREATED', 'START_REQUESTED', 'STARTING', 'RUNNING', 'RUNNING_OFFLINE', 'ENDING', 'SYNCING']

function isCurrentStatus(status) {
  return CURRENT_STATUSES.indexOf(String(status || '').toUpperCase()) !== -1
}

function splitEvents(items) {
  const current = []
  const history = []
  ;(Array.isArray(items) ? items : []).forEach((item) => {
    const event = normalizeEvent(item)
    ;(isCurrentStatus(event.status) ? current : history).push(event)
  })
  return { current, history }
}

const STATUS_LABELS = {
  CREATED: '任务已创建', START_REQUESTED: '开始请求已提交', STARTING: '等待设备确认', RUNNING: '巡检中',
  RUNNING_OFFLINE: '设备离线运行', ENDING: '结束请求处理中', SYNCING: '数据同步中', COMPLETED: '已完成',
  FAILED: '失败', CANCELLED: '已取消', REJECTED: '设备已拒绝', EXPIRED: '命令已过期',
}

function statusLabel(status) {
  const key = String(status || '').toUpperCase()
  return STATUS_LABELS[key] || key || '未知'
}

function normalizeEvent(item) {
  const event = normalizeMission(item)
  return Object.assign({}, event, {
    status_label: statusLabel(event.status),
    display_time: event.started_at || event.created_at || '--',
    sync_label: event.status === 'COMPLETED' ? '已同步' : (event.status === 'ENDING' || event.status === 'SYNCING' ? '等待同步完成' : '尚未确认同步完成'),
  })
}

module.exports = { CURRENT_STATUSES, isCurrentStatus, splitEvents, statusLabel, normalizeEvent }
