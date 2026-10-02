function rawMessage(error) {
  const raw = error && error.raw
  return String((raw && (raw.errMsg || raw.message)) || (error && error.message) || '').toLowerCase()
}

function diagnoseNetworkError(error) {
  const text = rawMessage(error)
  const code = Number(error && error.code)
  if (error && error.isSessionExpired) {
    return { kind: 'unauthorized', title: '登录已过期', message: '本地会话已清理，请重新登录。' }
  }
  if (text.indexOf('domain list') !== -1 || text.indexOf('url not in domain') !== -1 || text.indexOf('合法域名') !== -1) {
    return { kind: 'domain_check', title: 'HTTP 域名校验阻止请求', message: '开发阶段请确认项目本地配置 urlCheck=false；正式发布必须改用已配置的 HTTPS 合法域名。' }
  }
  if (text.indexOf('ssl') !== -1 || text.indexOf('tls') !== -1 || text.indexOf('certificate') !== -1 || text.indexOf('handshake') !== -1) {
    return { kind: 'tls_error', title: 'TLS/证书校验失败', message: '当前地址的 HTTPS 证书或握手失败；开发期局域网使用 HTTP，正式发布必须配置有效 HTTPS 证书和合法域名。' }
  }
  if (text.indexOf('timeout') !== -1) {
    return { kind: 'timeout', title: '请求超时', message: '检查后端是否以 0.0.0.0:8000 监听、手机与电脑是否同网，以及校园网/AP 隔离和 Windows 防火墙。' }
  }
  if (text.indexOf('network is disconnected') !== -1 || text.indexOf('network disconnected') !== -1) {
    return { kind: 'offline', title: '手机网络不可用', message: '请连接与电脑相同且可互访的 Wi-Fi 后重试。' }
  }
  if (text.indexOf('refused') !== -1 || text.indexOf('econnrefused') !== -1) {
    return { kind: 'refused', title: '后端未接受连接', message: '后端可能未启动，或只监听了 127.0.0.1；请用 --host 0.0.0.0 --port 8000 启动。' }
  }
  if (code >= 500) {
    return { kind: 'server_error', title: '后端服务异常', message: '网络已到达后端，但服务返回错误；请检查 FastAPI 控制台和数据库状态。' }
  }
  if (code >= 400) {
    return { kind: 'business_error', title: '接口请求失败', message: (error && error.message) || '请检查请求参数和后端日志。' }
  }
  return {
    kind: 'unreachable',
    title: '无法连接局域网 API',
    message: '依次检查：后端是否启动、是否监听 0.0.0.0、电脑 IP 是否变化、手机与电脑是否同网、是否存在 AP 隔离，以及 Windows 防火墙是否允许 8000 端口。',
  }
}

module.exports = { diagnoseNetworkError, rawMessage }
