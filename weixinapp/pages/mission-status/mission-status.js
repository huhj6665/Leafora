const api = require('../../utils/api')
const store = require('../../utils/mission-store')
const { normalizeMission, freshness, canRequestEnd } = require('../../utils/mission-view')
const { normalizePoint, normalizeGrid } = require('../../utils/spatial-view')
const { normalizeLive, sourceLabels } = require('../../utils/telemetry-view')

Page({
  data: { inspectionId: '', mission: null, live: null, freshness: { state: 'unknown', label: '等待实时数据' }, loading: false, ending: false, errorMsg: '' },
  onLoad(options) { this.setData({ inspectionId: decodeURIComponent((options && options.inspection_id) || '') }); this._revision = 0 },
  onShow() { this._visible = true; this._revision += 1; this.setData({ ending: !!this._ending }); this.startPolling(); this.refresh() },
  onHide() { this._visible = false; this._revision += 1; this.stopPolling() },
  onUnload() { this.onHide() },
  startPolling() { this.stopPolling(); this._timer = setInterval(() => this.refresh(), 3000) },
  stopPolling() { if (this._timer) { clearInterval(this._timer); this._timer = null } },
  async refresh() {
    if (!this.data.inspectionId || this._refreshing || !this._visible || this._ending) return
    const revision = this._revision
    this.setData({ freshness: freshness(this.data.live && this.data.live.received_at) })
    this._refreshing = true
    try {
      const errors = []
      const results = await Promise.all([
        api.getInspection(this.data.inspectionId),
        api.getInspectionLive(this.data.inspectionId).catch((error) => { errors.push('实时数据：' + (error.message || '读取失败')); return null }),
        api.getInspectionSpatial(this.data.inspectionId).catch((error) => { errors.push('空间结果：' + (error.message || '读取失败')); return null }),
      ])
      if (!this._visible || revision !== this._revision) return
      const mission = normalizeMission(results[0])
      let liveResult = results[1] || this._lastLiveResult || {}
      if (liveResult.raw && liveResult.raw.inspection_id && liveResult.raw.inspection_id !== this.data.inspectionId) {
        liveResult = {}
        errors.push('等待本次巡检采样；设备最新数据仍属于上一任务')
      }
      if (results[1]) this._lastLiveResult = liveResult
      const telemetry = normalizeLive(liveResult)
      const spatial = results[2] || {}
      const field = spatial.field || mission.field_snapshot || {}
      const live = Object.assign({}, liveResult, telemetry, {
        background_url: field.base_map_url || '',
        track: spatial.track || [],
        risk_grid: spatial.risk_grids || spatial.risk_grid || [],
        disease_points: spatial.disease_points || [],
      })
      Object.assign(mission, sourceLabels(mission, field))
      const flightProgress = (telemetry.flight_status || {}).progress
      if (flightProgress != null && Number.isFinite(Number(flightProgress))) {
        mission.progress_percent = Math.max(0, Math.min(100, Math.round(Number(flightProgress) * 100)))
        mission.progress_known = true
      }
      if (live.background_url) {
        if (this._backgroundSource !== live.background_url || !this._backgroundLocal) {
          try { this._backgroundLocal = await api.downloadImage(live.background_url); this._backgroundSource = live.background_url }
          catch (error) { this._backgroundLocal = '' }
        }
        live.background_url = this._backgroundLocal || ''
      }
      if (!this._visible || revision !== this._revision) return
      live.track = (Array.isArray(live.track) ? live.track : []).map(normalizePoint).filter(Boolean)
      live.risk_grid = (Array.isArray(live.risk_grid) ? live.risk_grid : []).map(normalizeGrid).filter(Boolean)
      live.disease_points = (Array.isArray(live.disease_points) ? live.disease_points : []).map(normalizePoint).filter(Boolean)
      const fresh = freshness(live.received_at || live.updated_at)
      if (['ENDING', 'SYNCING', 'COMPLETED'].indexOf(mission.status) !== -1) this._endError = ''
      this.setData({ mission, live, freshness: fresh, errorMsg: [this._endError, errors.join('；'), mission.sync_warning].filter(Boolean).join('；') })
      store.saveActive(mission)
      if (mission.status === 'COMPLETED') {
        store.clearActive()
        store.clearRequestId('end:' + this.data.inspectionId)
      }
    } catch (error) {
      if (this._visible && revision === this._revision) this.setData({ errorMsg: [this._endError, error.message || '任务状态更新失败，页面会继续重试'].filter(Boolean).join('；'), freshness: freshness(this.data.live && this.data.live.received_at) })
    } finally {
      this._refreshing = false
      if (this._visible && revision !== this._revision && !this._ending) this.refresh()
    }
  },
  requestEnd() {
    if (!this.data.mission || !canRequestEnd(this.data.mission.status)) return
    wx.showModal({
      title: '结束本次巡检？', content: '设备将停止产生新数据并继续同步缓存。只有云端返回 COMPLETED 后任务才真正完成。', confirmText: '确认结束',
      success: (res) => { if (res.confirm) this.doEnd() },
    })
  },
  async doEnd() {
    if (this._ending || !this.data.mission || !canRequestEnd(this.data.mission.status)) return
    this._ending = true
    this._endError = ''
    this._revision += 1 // 结束前的在途轮询不能覆盖新的 ENDING 状态。
    const key = 'end:' + this.data.inspectionId
    const requestId = store.getOrCreateRequestId(key, 'END')
    this.setData({ ending: true, errorMsg: '' })
    try {
      const result = normalizeMission(await api.endInspection(this.data.inspectionId, requestId))
      if (!result.inspection_id) throw { message: '结束响应缺少 inspection_id；状态未确认，请重试同一请求' }
      if (this._visible) this.setData({ mission: result })
      store.saveActive(result)
    } catch (error) {
      this._endError = (error.message || '网络异常') + '；结束状态未确认，请查看云端状态或重试同一请求'
      if (this._visible) this.setData({ errorMsg: this._endError })
    } finally {
      this._ending = false
      if (this._visible) { this.setData({ ending: false }); this.refresh() }
    }
  },
  openRecord() { if (this.data.mission && this.data.mission.status === 'COMPLETED') wx.redirectTo({ url: '/pages/inspection-detail/inspection-detail?inspection_id=' + encodeURIComponent(this.data.inspectionId) }) },
  showGrid(e) { const cell = this.data.live.risk_grid[e.currentTarget.dataset.index]; wx.showModal({ title: cell.risk_label, content: '样本 ' + (cell.sample_count || 0) + ' · 疑似 ' + (cell.suspected_count || 0), showCancel: false }) },
})
