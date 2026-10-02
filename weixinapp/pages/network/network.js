const api = require('../../utils/api')
const auth = require('../../utils/auth')
const config = require('../../utils/config')
const settings = require('../../utils/server-settings')
const gate = require('../../utils/network-gate')
const { diagnoseNetworkError } = require('../../utils/network-diagnostics')

Page({
  data: {
    mode: 'gate', host: '', port: String(config.DEFAULT_PORT), advanced: false,
    previewUrl: '', currentOrigin: '', testing: false, state: 'idle', canEnter: false,
    title: '连接开发服务', message: '填写电脑在当前 Wi-Fi 下的 IPv4', health: null, validationError: '',
  },
  onLoad(options) {
    const mode = options && options.mode === 'settings' ? 'settings' : 'gate'
    const current = config.getCurrentServerConfig()
    this.setData({ mode, host: current.host, port: String(current.port), previewUrl: current.apiBaseUrl, currentOrigin: current.origin })
    if (mode === 'gate' && config.hasExplicitServerConfig()) this.autoCheck()
  },
  onHostInput(e) { this.setData({ host: e.detail.value, canEnter: false }); this.updatePreview(e.detail.value, this.data.port) },
  onPortInput(e) { this.setData({ port: e.detail.value, canEnter: false }); this.updatePreview(this.data.host, e.detail.value) },
  toggleAdvanced() { this.setData({ advanced: !this.data.advanced }) },
  updatePreview(host, port) {
    const result = config.buildServerConfig(host, port)
    this.setData({ previewUrl: result.ok ? result.apiBaseUrl : '', validationError: result.ok ? '' : result.error })
    return result
  },
  async autoCheck() {
    const result = config.getCurrentServerConfig()
    this.setData({ host: result.host, port: String(result.port), previewUrl: result.apiBaseUrl })
    const ok = await this.runHealth(result)
    if (ok) setTimeout(() => this.enterLeafora(), 350)
  },
  async detectConnection() {
    const result = this.updatePreview(this.data.host, this.data.port)
    if (!result.ok) {
      this.setData({ state: 'invalid', title: '地址格式不正确', message: result.error, canEnter: false })
      return false
    }
    return this.runHealth(result)
  },
  async runHealth(result) {
    if (this.data.testing) return false
    this._tested = null
    this.setData({ testing: true, state: 'testing', title: '正在寻找 Leafora 服务', message: '请保持手机和电脑连接同一网络', health: null, canEnter: false })
    try {
      const health = await api.healthAt(result.healthUrl)
      const outcome = gate.healthOutcome(health)
      if (!outcome.ok) {
        this.setData({ state: outcome.state, title: '服务暂不可用', message: outcome.message, health })
        return false
      }
      this._tested = result
      this.setData({ state: 'success', title: '连接成功', message: '本地服务与数据库均可用，可以进入 Leafora', health, canEnter: true })
      return true
    } catch (error) {
      const diagnostic = diagnoseNetworkError(error)
      this.setData({ state: 'failed', title: diagnostic.title, message: diagnostic.message })
      return false
    } finally { this.setData({ testing: false }) }
  },
  enterLeafora() {
    if (!this.data.canEnter || !this._tested) return
    const proceed = () => {
      const saved = settings.applyServerChange(config, auth, this._tested.host, this._tested.port)
      if (!saved.ok) return this.setData({ state: 'invalid', title: '保存失败', message: saved.error, canEnter: false })
      config.markHealthVerified(saved.origin)
      wx.reLaunch({ url: '/pages/index/index' })
    }
    const changed = config.hasExplicitServerConfig() && config.getCurrentServerConfig().origin !== this._tested.origin
    if (!changed) return proceed()
    wx.showModal({
      title: '确认更换服务器',
      content: '更换后会清除旧服务器的登录状态和运行任务缓存，其他本地偏好不受影响。',
      confirmText: '确认更换',
      success: (res) => { if (res.confirm) proceed() },
    })
  },
  clearLocalConfig() {
    wx.showModal({
      title: '清除连接配置', content: '清除后将退出当前账号，下次启动需重新检测电脑地址。', confirmText: '确认清除',
      success: (res) => {
        if (!res.confirm) return
        settings.clearServerOverride(config, auth)
        const fallback = config.getCurrentServerConfig()
        this._tested = null
        this.setData({ host: fallback.host, port: String(fallback.port), previewUrl: fallback.apiBaseUrl, state: 'idle', canEnter: false, title: '配置已清除', message: '请重新填写并检测电脑局域网地址', health: null })
      },
    })
  },
  copyUrl() { wx.setClipboardData({ data: this.data.previewUrl + '/health' }) },
})
