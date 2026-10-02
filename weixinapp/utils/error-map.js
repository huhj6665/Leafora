function errorText(error) {
  return String((error && error.message) || '').toLowerCase()
}

function hasAny(text, values) {
  return values.some((value) => text.indexOf(value) !== -1)
}

function mapOperationError(operation, error) {
  if (error && error.isSessionExpired) {
    return { state: 'auth_required', message: '登录已过期，请重新登录', retryable: true }
  }
  if (error && error.isApiUnavailable) {
    return { state: 'unavailable', message: error.message, retryable: false }
  }
  const code = Number(error && error.code)
  const text = errorText(error)
  if (code === -1) {
    return { state: 'network_error', message: '网络失败，请检查连接后重试', retryable: true }
  }
  if (code === 410 || hasAny(text, ['过期', 'expired'])) {
    return { state: 'expired', message: operation === 'pairing' ? '配对码已过期，请回到 Jetson 刷新二维码' : 'Web 登录二维码已过期，请在 Web 端刷新', retryable: false }
  }
  if (hasAny(text, ['已属于当前', 'already bound to current', 'already_bound_self'])) {
    return { state: 'success', message: '设备已绑定到当前账号', retryable: false, idempotent: true }
  }
  if (hasAny(text, ['其他用户', '他人', 'another user', 'bound_other'])) {
    return { state: 'bound_other', message: '设备已绑定其他账号，无法继续', retryable: false }
  }
  if (hasAny(text, ['取消', 'cancelled', 'canceled'])) {
    return { state: 'cancelled', message: '登录请求已取消', retryable: false }
  }
  if (code === 409 || hasAny(text, ['已消费', '已使用', 'consumed', 'used'])) {
    return { state: 'consumed', message: '该二维码已使用，请获取新的二维码', retryable: false }
  }
  return { state: 'server_error', message: (error && error.message) || '请求失败，请稍后重试', retryable: code >= 500 }
}

function mapConfirmResponse(operation, response) {
  const status = String((response && response.status) || '').toUpperCase()
  if (!status || status === 'CONFIRMED' || status === 'SUCCESS' || status === 'BOUND') {
    return { state: 'success', message: operation === 'pairing' ? '设备绑定成功' : 'Web 登录已确认' }
  }
  if (status === 'EXPIRED') return mapOperationError(operation, { code: 410 })
  if (status === 'CONSUMED') return mapOperationError(operation, { code: 409, message: 'consumed' })
  if (status === 'CANCELLED' || status === 'CANCELED') return mapOperationError(operation, { message: 'cancelled' })
  if (status === 'BOUND_OTHER') return mapOperationError(operation, { message: 'bound_other' })
  if (status === 'ALREADY_BOUND_SELF') return mapOperationError(operation, { message: 'already_bound_self' })
  return { state: 'success', message: operation === 'pairing' ? '设备绑定成功' : 'Web 登录已确认' }
}

module.exports = { mapOperationError, mapConfirmResponse }
