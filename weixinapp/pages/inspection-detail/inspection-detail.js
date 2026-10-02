const auth = require('../../utils/auth')
const api = require('../../utils/api')
const { statusLabel } = require('../../utils/inspection-view')
const { normalizePoint, normalizeGrid } = require('../../utils/spatial-view')
const { normalizeMission } = require('../../utils/mission-view')
const { valueText, sourceLabels } = require('../../utils/telemetry-view')

function normalizeDetail(detail) {
  const data = normalizeMission(detail)
  const spatial = data.spatial || {}
  const field = spatial.field || data.field_snapshot || {}
  const environment = (Array.isArray(data.environment) ? data.environment : []).map((item) => Object.assign({}, item, {
    temperature_text: valueText(item.temperature), humidity_text: valueText(item.humidity),
    co2_text: valueText(item.co2), light_text: valueText(item.light),
  }))
  const track = (Array.isArray(spatial.track || data.track) ? (spatial.track || data.track) : []).map(normalizePoint).filter(Boolean)
  const images = (Array.isArray(data.images) ? data.images : []).map((item) => {
    const cloud = item.cloud_detection || {}
    const results = (Array.isArray(cloud.results) ? cloud.results : []).map((result) => ({
      class_name: result.class || result.class_name || '未知目标',
      confidence_text: result.confidence == null ? '--' : Math.round(Number(result.confidence) * 1000) / 10 + '%',
    }))
    return Object.assign({}, item, { cloud_status: cloud.status || '未处理', results, local_path: '', load_error: '' })
  })
  return Object.assign({}, data, sourceLabels(data, field), {
    status_label: statusLabel(data.status),
    environment,
    latest_environment: environment.length ? environment[environment.length - 1] : null,
    images,
    field_name: data.field_name || field.name,
    track,
    track_count: track.length,
    risk_grid: (Array.isArray(spatial.risk_grids || spatial.risk_grid || data.risk_grid) ? (spatial.risk_grids || spatial.risk_grid || data.risk_grid) : []).map(normalizeGrid).filter(Boolean),
    disease_points: (Array.isArray(spatial.disease_points || data.disease_points) ? (spatial.disease_points || data.disease_points) : []).map(normalizePoint).filter(Boolean),
    background_url: field.base_map_url || data.background_url || data.field_background_url || '',
    background_local: '',
    is_simulated: String(data.data_provenance || '').toUpperCase() === 'SIMULATED',
    risk: data.risk || { target_count: 0, level: 'LOW', score: 0 },
  })
}

Page({
  data: { inspectionId: '', detail: null, loading: false, errorMsg: '' },
  onLoad(options) {
    const id = options && options.inspection_id ? decodeURIComponent(options.inspection_id) : ''
    this.setData({ inspectionId: id })
    this.load()
  },
  async load() {
    if (!auth.hasToken()) { wx.redirectTo({ url: '/pages/login/login' }); return }
    this.setData({ loading: true, errorMsg: '' })
    try {
      const results = await Promise.all([
        api.getInspection(this.data.inspectionId),
        api.getInspectionSpatial(this.data.inspectionId),
        api.getInspectionEvent(this.data.inspectionId).catch(() => ({})),
      ])
      const raw = Object.assign({}, results[2] || {}, results[0] || {}, { spatial: results[1] || {} })
      const detail = normalizeDetail(raw)
      this.setData({ detail })
      this.loadImages(detail.images.slice(0, 20))
      this.loadBackground(detail.background_url)
    } catch (err) {
      this.setData({ errorMsg: err.message || '巡检详情加载失败' })
      if (err.isUnauthorized) wx.redirectTo({ url: '/pages/login/login' })
    } finally { this.setData({ loading: false }) }
  },
  async loadBackground(url) {
    if (!url) return
    try { this.setData({ 'detail.background_local': await api.downloadImage(url) }) }
    catch (error) { /* 无底图时保留明确空状态 */ }
  },
  async loadImages(images) {
    const loaded = await Promise.all(images.map(async (image) => {
      try { return Object.assign({}, image, { local_path: await api.downloadImage(image.url) }) }
      catch (err) { return Object.assign({}, image, { load_error: err.message || '图片加载失败' }) }
    }))
    if (!this.data.detail) return
    const tail = this.data.detail.images.slice(loaded.length)
    this.setData({ 'detail.images': loaded.concat(tail) })
  },
  preview(e) {
    const current = e.currentTarget.dataset.path
    const urls = this.data.detail.images.map((item) => item.local_path).filter(Boolean)
    if (current) wx.previewImage({ current, urls })
  },
  showGrid(e) {
    const cell = this.data.detail.risk_grid[e.currentTarget.dataset.index]
    wx.showModal({ title: cell.risk_label, content: '样本 ' + (cell.sample_count || 0) + ' · 疑似 ' + (cell.suspected_count || 0), showCancel: false })
  },
})

module.exports = { normalizeDetail }
