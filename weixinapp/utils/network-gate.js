function canEnterBusiness(config) {
  return config.hasExplicitServerConfig() && config.isCurrentServerVerified()
}

function healthOutcome(health) {
  const status = String((health && health.status) || '').toLowerCase()
  if (status === 'ok' || status === 'healthy') return { ok: true, state: 'success' }
  if (status === 'degraded') return { ok: false, state: 'degraded', message: '服务可达，但后端处于降级状态' }
  return { ok: false, state: 'service_error', message: '健康检查响应不完整' }
}

module.exports = { canEnterBusiness, healthOutcome }
