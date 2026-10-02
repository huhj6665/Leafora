const auth = require('../../utils/auth')
const api = require('../../utils/api')
const { splitEvents, normalizeEvent } = require('../../utils/inspection-view')
const { normalizeDevice, buildPreflight } = require('../../utils/device-view')

Page({
  data: { deviceId: '', device: null, current: [], recent: [], loading: false, errorMsg: '', unbinding: false },
  onLoad(options) {
    const deviceId = options && options.device_id ? decodeURIComponent(options.device_id) : ''
    this.setData({ deviceId })
  },
  onShow() { if (this.data.deviceId) this.load() },
  onPullDownRefresh() { this.load().finally(() => wx.stopPullDownRefresh()) },
  async load() {
    if (!auth.hasToken()) { wx.redirectTo({ url: '/pages/login/login' }); return }
    this.setData({ loading: true, errorMsg: '' })
    try {
      const results = await Promise.all([
        api.listDevices(),
        api.listInspectionEvents({ device_id: this.data.deviceId, page: 1, page_size: 20 }),
      ])
      const device = (Array.isArray(results[0]) ? results[0] : []).find((item) => item.device_id === this.data.deviceId)
      if (!device) throw { code: 404, message: '设备不存在或已解绑' }
      const items = ((results[1] && results[1].items) || []).map(normalizeEvent)
      const groups = splitEvents(items)
      this.setData({ device: normalizeDevice(device), preflight: buildPreflight(device), current: groups.current, recent: groups.history.slice(0, 5) })
    } catch (err) {
      this.setData({ errorMsg: err.message || '设备详情加载失败' })
      if (err.isUnauthorized) wx.redirectTo({ url: '/pages/login/login' })
    } finally { this.setData({ loading: false }) }
  },
  openInspection(e) {
    wx.navigateTo({ url: '/pages/inspection-detail/inspection-detail?inspection_id=' + encodeURIComponent(e.currentTarget.dataset.id) })
  },
  viewAll() {
    wx.navigateTo({ url: '/pages/inspections/inspections?device_id=' + encodeURIComponent(this.data.deviceId) })
  },
  unbind() {
    wx.showModal({
      title: '确认解绑设备',
      content: '解绑后设备不再属于当前账号，但历史巡检不会删除。确定继续吗？',
      confirmColor: '#dc2626',
      success: async (res) => {
        if (!res.confirm || this.data.unbinding) return
        this.setData({ unbinding: true, errorMsg: '' })
        try {
          await api.unbindDevice(this.data.deviceId)
          wx.showToast({ title: '已解绑', icon: 'success' })
          setTimeout(() => wx.redirectTo({ url: '/pages/devices/devices' }), 400)
        } catch (err) { this.setData({ errorMsg: err.message || '解绑失败' }) }
        finally { this.setData({ unbinding: false }) }
      },
    })
  },
})
