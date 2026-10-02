/** 统一请求层：拼接地址、携带 JWT、解析响应并处理会话失效。 */
const config = require('./config')
const auth = require('./auth')

function extractMessage(res) {
  const data = res && res.data
  if (data && typeof data === 'object') {
    if (data.message) return data.message
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail) && data.detail.length && data.detail[0].msg) return data.detail[0].msg
    if (Array.isArray(data.data) && data.data.length && data.data[0].msg) return data.data[0].msg
  }
  return '请求失败，请稍后重试'
}

function isCredentialFailure(message) {
  const text = String(message || '')
  return ['验证码', '手机号或密码', '扫码凭证', '配对凭证'].some((part) => text.indexOf(part) !== -1)
}

function absoluteUrl(path) {
  if (/^https?:\/\//.test(path || '')) return path
  const value = String(path || '')
  if (value === config.API_PREFIX || value.indexOf(config.API_PREFIX + '/') === 0) {
    return config.getBaseUrl() + path
  }
  return config.getBaseUrl() + config.API_PREFIX + path
}

function buildHeaders(options, token) {
  return Object.assign(
    { 'Content-Type': 'application/json' },
    options && options.auth !== false && token ? { Authorization: 'Bearer ' + token } : {},
    (options && options.header) || {}
  )
}

function request(options) {
  const token = auth.getToken()
  return new Promise((resolve, reject) => {
    wx.request({
      url: absoluteUrl(options.url),
      method: (options.method || 'GET').toUpperCase(),
      data: options.data || {},
      timeout: options.timeout || 15000,
      header: buildHeaders(options, token),
      success(res) {
        const statusCode = res.statusCode
        const data = res.data
        if (statusCode >= 200 && statusCode < 300 && data && data.code === 0) {
          resolve(data.data)
          return
        }
        if (statusCode === 401) {
          const message = extractMessage(res)
          const sessionExpired = !isCredentialFailure(message)
          if (sessionExpired) auth.clearSession()
          reject({ code: 401, message, isUnauthorized: true, isSessionExpired: sessionExpired, raw: res })
          return
        }
        reject({ code: statusCode, message: extractMessage(res), raw: res })
      },
      fail(err) {
        reject({ code: -1, message: '网络请求失败，请检查网络和后端服务', raw: err })
      },
    })
  })
}

function shouldRetryRead(method, error, attempt, maxRetries) {
  const read = String(method || 'GET').toUpperCase() === 'GET'
  const retryableCode = Number(error && error.code) === -1 || Number(error && error.code) >= 500
  return read && retryableCode && attempt < (maxRetries || 0)
}

function requestWithRetry(options) {
  const settings = Object.assign({}, options)
  const maxRetries = Number(settings.retries || 0)
  delete settings.retries
  function run(attempt) {
    return request(settings).catch((error) => {
      if (!shouldRetryRead(settings.method, error, attempt, maxRetries)) throw error
      return run(attempt + 1)
    })
  }
  return run(0)
}

function downloadAuthenticated(path) {
  const token = auth.getToken()
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: absoluteUrl(path),
      timeout: 20000,
      header: token ? { Authorization: 'Bearer ' + token } : {},
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.tempFilePath)
        } else {
          if (res.statusCode === 401) auth.clearSession()
          reject({ code: res.statusCode, message: '图片加载失败', isUnauthorized: res.statusCode === 401 })
        }
      },
      fail(err) {
        reject({ code: -1, message: '图片网络加载失败', raw: err })
      },
    })
  })
}

module.exports = {
  request,
  requestWithRetry,
  shouldRetryRead,
  absoluteUrl,
  buildHeaders,
  downloadAuthenticated,
  extractMessage,
  isCredentialFailure,
  get: (url, data, options) => requestWithRetry(Object.assign({ url, method: 'GET', data, retries: 1 }, options || {})),
  post: (url, data) => request({ url, method: 'POST', data }),
}
