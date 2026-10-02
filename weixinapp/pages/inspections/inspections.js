const auth = require('../../utils/auth')
const api = require('../../utils/api')
const { splitEvents, normalizeEvent } = require('../../utils/inspection-view')
const { syncTabBar } = require('../../utils/tabbar')

Page({
  data: {
    tab: 'current', deviceId: '', current: [], history: [], loading: false, errorMsg: '',
    fieldOptions: [{ label: '全部烟田', value: '' }], deviceOptions: [{ label: '全部设备', value: '' }],
    statusOptions: [{ label: '全部状态', value: '' }, { label: '运行中', value: 'RUNNING' }, { label: '同步中', value: 'SYNCING' }, { label: '已完成', value: 'COMPLETED' }, { label: '失败', value: 'FAILED' }],
    fieldIndex: 0, deviceIndex: 0, statusIndex: 0, dateFrom: '',
  },
  onLoad(options) {
    this.setData({ deviceId: options && options.device_id ? decodeURIComponent(options.device_id) : '' })
  },
  onShow() { syncTabBar(this); this.load() },
  onPullDownRefresh() { this.load().finally(() => wx.stopPullDownRefresh()) },
  switchTab(e) { this.setData({ tab: e.currentTarget.dataset.tab }) },
  async load() {
    if (!auth.hasToken()) { wx.redirectTo({ url: '/pages/login/login' }); return }
    this.setData({ loading: true, errorMsg: '' })
    try {
      const params = { page: 1, page_size: 100 }
      if (this.data.deviceId) params.device_id = this.data.deviceId
      const result = await api.listInspectionEvents(params)
      this._items = ((result && result.items) || []).map(normalizeEvent)
      const unique = (key, fallback) => {
        const seen = {}
        return this._items.reduce((list, item) => {
          const value = item[key]
          if (value && !seen[value]) { seen[value] = true; list.push({ label: item[fallback] || value, value }) }
          return list
        }, [])
      }
      const fieldOptions = [{ label: '全部烟田', value: '' }].concat(unique('field_id', 'field_name'))
      const deviceOptions = [{ label: '全部设备', value: '' }].concat(unique('device_id', 'device_name'))
      let deviceIndex = this.data.deviceIndex
      if (this.data.deviceId) deviceIndex = Math.max(0, deviceOptions.findIndex((item) => item.value === this.data.deviceId))
      this.setData({ fieldOptions, deviceOptions, deviceIndex })
      this.applyFilters()
    } catch (err) {
      this.setData({ errorMsg: err.message || '巡检记录加载失败' })
      if (err.isUnauthorized) wx.redirectTo({ url: '/pages/login/login' })
    } finally { this.setData({ loading: false }) }
  },
  onFilter(e) {
    const key = e.currentTarget.dataset.key
    const change = {}; change[key] = Number(e.detail.value)
    this.setData(change); this.applyFilters()
  },
  onDate(e) { this.setData({ dateFrom: e.detail.value }); this.applyFilters() },
  clearFilters() { this.setData({ fieldIndex: 0, deviceIndex: 0, statusIndex: 0, dateFrom: '' }); this.applyFilters() },
  applyFilters() {
    const field = this.data.fieldOptions[this.data.fieldIndex] || { value: '' }
    const device = this.data.deviceOptions[this.data.deviceIndex] || { value: '' }
    const status = this.data.statusOptions[this.data.statusIndex] || { value: '' }
    const filtered = (this._items || []).filter((item) => {
      if (field.value && item.field_id !== field.value) return false
      if (device.value && item.device_id !== device.value) return false
      if (status.value && String(item.status).toUpperCase() !== status.value) return false
      if (this.data.dateFrom && String(item.display_time || '').slice(0, 10) < this.data.dateFrom) return false
      return true
    })
    this.setData(splitEvents(filtered))
  },
  open(e) {
    wx.navigateTo({ url: '/pages/inspection-detail/inspection-detail?inspection_id=' + encodeURIComponent(e.currentTarget.dataset.id) })
  },
})
