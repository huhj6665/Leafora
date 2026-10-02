const auth = require('../../utils/auth')
const api = require('../../utils/api')
const scanStore = require('../../utils/scan-store')
const { toDisplayData } = require('../../utils/result-view')
const { mapOperationError, mapConfirmResponse } = require('../../utils/error-map')

Page({
  data: {
    ready: false, ok: false, kind: '', state: 'format_valid', statusText: '',
    error: '', errorMsg: '', retryable: false, confirming: false,
  },

  onLoad() { this.loadPending() },

  loadPending() {
    const result = scanStore.get()
    this._result = result
    const view = toDisplayData(result)
    if (view.ok && view.expired) {
      view.state = 'expired'
      view.statusText = view.kind === 'device_pairing' ? '配对码已过期，请回到 Jetson 刷新二维码' : 'Web 登录二维码已过期，请在 Web 端刷新'
    } else if (view.ok) {
      view.state = 'format_valid'
      view.statusText = '格式校验成功，尚未通过云端身份验证'
    }
    this.setData(view)
  },

  confirm() {
    if (!this._result || !this._result.ok || this.data.expired || this.data.confirming) return
    if (this._result.data.expires_at_ms <= Date.now()) {
      this.setData({ expired: true, state: 'expired', statusText: this._result.data.kind === 'device_pairing' ? '配对码已过期，请回到 Jetson 刷新二维码' : 'Web 登录二维码已过期，请在 Web 端刷新' })
      return
    }
    if (!auth.hasToken()) {
      wx.navigateTo({ url: '/pages/login/login?redirect=' + encodeURIComponent('/pages/scan-result/scan-result') })
      return
    }
    return this.confirmWithCloud()
  },

  async confirmWithCloud() {
    const payload = this._result.data
    const operation = payload.kind === 'device_pairing' ? 'pairing' : 'web_login'
    this.setData({ confirming: true, state: 'confirming', statusText: '正在向云端确认…', errorMsg: '' })
    try {
      const response = payload.kind === 'device_pairing'
        ? await api.confirmDevicePairing(payload)
        : await api.confirmWebLogin(payload)
      const mapped = mapConfirmResponse(operation, response)
      if (mapped.state === 'success' || mapped.state === 'cancelled' || mapped.state === 'consumed') scanStore.clear()
      this.setData({ state: mapped.state, confirming: false, statusText: mapped.message, errorMsg: mapped.state === 'success' ? '' : mapped.message, retryable: !!mapped.retryable })
    } catch (err) {
      const mapped = mapOperationError(operation, err)
      if (mapped.idempotent) scanStore.clear()
      this.setData({ state: mapped.state, statusText: mapped.message, errorMsg: mapped.message, retryable: mapped.retryable, confirming: false })
      if (mapped.state === 'auth_required') {
        wx.navigateTo({ url: '/pages/login/login?redirect=' + encodeURIComponent('/pages/scan-result/scan-result') })
      }
    }
  },

  cancelRequest() {
    scanStore.clear()
    this._result = null
    this.setData({ state: 'cancelled', statusText: '已在小程序中取消本次确认', retryable: false })
  },
  goDevices() { wx.reLaunch({ url: '/pages/devices/devices' }) },
  goHome() { scanStore.clear(); wx.reLaunch({ url: '/pages/index/index' }) },
  rescan() { scanStore.clear(); scanStore.setRequestScan(true); wx.reLaunch({ url: '/pages/index/index' }) },
})
