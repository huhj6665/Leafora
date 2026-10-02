const auth = require('../../utils/auth')
const api = require('../../utils/api')
const { normalizeDevice } = require('../../utils/device-view')

Page({
  data: { loading: false, devices: [], errorMsg: '' },
  onShow() { this.loadDevices() },
  onPullDownRefresh() { this.loadDevices().finally(() => wx.stopPullDownRefresh()) },
  async loadDevices() {
    if (!auth.hasToken()) { wx.redirectTo({ url: '/pages/login/login' }); return }
    this.setData({ loading: true, errorMsg: '' })
    try {
      const data = await api.listDevices()
      this.setData({ devices: (Array.isArray(data) ? data : []).map(normalizeDevice) })
    } catch (err) {
      this.setData({ errorMsg: err.message || '设备列表加载失败' })
      if (err.isUnauthorized) wx.redirectTo({ url: '/pages/login/login' })
    } finally { this.setData({ loading: false }) }
  },
  openDevice(e) {
    wx.navigateTo({ url: '/pages/device-detail/device-detail?device_id=' + encodeURIComponent(e.currentTarget.dataset.id) })
  },
  scan() {
    const scanner = require('../../utils/scanner')
    scanner.scanAndOpenResult()
  },
})

module.exports = { normalizeDevice }
