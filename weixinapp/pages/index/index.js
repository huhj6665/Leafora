const auth = require('../../utils/auth')
const api = require('../../utils/api')
const scanner = require('../../utils/scanner')
const scanStore = require('../../utils/scan-store')
const store = require('../../utils/mission-store')
const { unwrapItems } = require('../../utils/field-view')
const { splitEvents, normalizeEvent } = require('../../utils/inspection-view')
const { normalizeMission } = require('../../utils/mission-view')
const { syncTabBar } = require('../../utils/tabbar')

Page({
  data: { isLoggedIn: false, user: null, loading: false, deviceCount: 0, fieldCount: 0, recent: null, active: null, riskText: '暂无巡检数据', partialError: '' },
  onShow() { syncTabBar(this); this.refresh(); if (scanStore.consumeRequestScan()) this.scanCode() },
  async refresh() {
    if (!auth.hasToken()) { this.setData({ isLoggedIn: false, user: null, active: null }); return }
    this.setData({ loading: true, partialError: '' })
    let profile = auth.getProfile()
    try { profile = await api.getProfile(); auth.saveProfile(profile); getApp().globalData.user = profile }
    catch (error) { if (error.isUnauthorized) return this.setData({ isLoggedIn: false, user: null, loading: false }) }
    const data = { isLoggedIn: true, user: profile || { nickname: '已登录用户' } }
    try { const devices = await api.listDevices(); data.deviceCount = Array.isArray(devices) ? devices.length : 0 } catch (e) { data.partialError = '部分概览暂不可用' }
    try { data.fieldCount = unwrapItems(await api.listFields()).length } catch (e) { data.partialError = '烟田接口待 Web V0.2 对齐' }
    try {
      const result = await api.listInspectionEvents({ page: 1, page_size: 10 })
      const groups = splitEvents(((result && result.items) || []).map(normalizeEvent))
      data.recent = groups.history[0] || null
      data.riskText = data.recent ? ((data.recent.target_count || 0) + ' 个疑似目标') : '暂无巡检数据'
      data.active = groups.current.length ? normalizeMission(groups.current[0]) : null
    } catch (e) { data.active = store.getActive() }
    this.setData(data)
    this.setData({ loading: false })
  },
  goLogin() { wx.navigateTo({ url: '/pages/login/login' }) },
  scanCode() { scanner.scanAndOpenResult() },
  goDevices() { if (!auth.hasToken()) return this.goLogin(); wx.navigateTo({ url: '/pages/devices/devices' }) },
  goFields() { if (!auth.hasToken()) return this.goLogin(); wx.switchTab({ url: '/pages/fields/fields' }) },
  goMission() { if (!auth.hasToken()) return this.goLogin(); wx.switchTab({ url: '/pages/mission/mission' }) },
  goRecords() { if (!auth.hasToken()) return this.goLogin(); wx.switchTab({ url: '/pages/inspections/inspections' }) },
  openActive() { if (this.data.active && this.data.active.inspection_id) wx.navigateTo({ url: '/pages/mission-status/mission-status?inspection_id=' + encodeURIComponent(this.data.active.inspection_id) }) },
})
