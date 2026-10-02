const auth = require('../../utils/auth')
const api = require('../../utils/api')
const request = require('../../utils/request')
const { normalizeField } = require('../../utils/field-view')
const { normalizePoint, normalizeGrid } = require('../../utils/spatial-view')
const { normalizeEvent } = require('../../utils/inspection-view')

Page({
  data: { fieldId: '', field: null, recent: [], loading: false, errorMsg: '' },
  onLoad(options) { this.setData({ fieldId: decodeURIComponent((options && options.field_id) || '') }); this.load() },
  async load() {
    if (!auth.hasToken()) { wx.navigateTo({ url: '/pages/login/login' }); return }
    this.setData({ loading: true, errorMsg: '' })
    try {
      const results = await Promise.all([api.getField(this.data.fieldId), api.listInspectionEvents({ field_id: this.data.fieldId, page: 1, page_size: 8 })])
      const field = normalizeField(results[0])
      field.display_image = field.background_url ? request.absoluteUrl(field.background_url) : ''
      field.track = (Array.isArray(field.latest_track) ? field.latest_track : []).map(normalizePoint).filter(Boolean)
      field.risk_grid = (Array.isArray(field.risk_grid) ? field.risk_grid : []).map(normalizeGrid).filter(Boolean)
      this.setData({ field, recent: ((results[1] && results[1].items) || []).map(normalizeEvent) })
    } catch (error) {
      this.setData({ errorMsg: error.code === 404 ? '烟田详情接口尚未由 Web V0.2 提供。' : (error.message || '烟田详情加载失败') })
    } finally { this.setData({ loading: false }) }
  },
  start() { wx.setStorageSync('tld_selected_field', this.data.fieldId); wx.switchTab({ url: '/pages/mission/mission' }) },
  openInspection(e) { wx.navigateTo({ url: '/pages/inspection-detail/inspection-detail?inspection_id=' + encodeURIComponent(e.currentTarget.dataset.id) }) },
  showGrid(e) { const cell = this.data.field.risk_grid[e.currentTarget.dataset.index]; wx.showModal({ title: cell.risk_label, content: '样本 ' + (cell.sample_count || 0) + ' · 疑似 ' + (cell.suspected_count || 0), showCancel: false }) },
})
