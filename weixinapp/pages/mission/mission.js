const auth = require('../../utils/auth')
const api = require('../../utils/api')
const store = require('../../utils/mission-store')
const { unwrapItems, normalizeField } = require('../../utils/field-view')
const { normalizeDevice, buildPreflight } = require('../../utils/device-view')
const { normalizeMission } = require('../../utils/mission-view')
const { syncTabBar } = require('../../utils/tabbar')

Page({
  data: { step: 1, fields: [], devices: [], selectedField: null, selectedDevice: null, preflight: null, name: '', loading: false, submitting: false, errorMsg: '' },
  onShow() {
    syncTabBar(this)
    this._visible = true
    if (!auth.hasToken()) { wx.navigateTo({ url: '/pages/login/login' }); return }
    this.recoverOrLoad()
  },
  onHide() { this._visible = false },
  onUnload() { this._visible = false },
  async recoverOrLoad() {
    if (this._recovering || this.data.submitting) return
    this._recovering = true
    this._recoveryFailed = false
    try {
      const cloud = normalizeMission(await api.getCurrentInspection())
      if (!this._visible) return
      if (cloud.inspection_id && !cloud.terminal) {
        store.saveActive(cloud)
        wx.navigateTo({ url: '/pages/mission-status/mission-status?inspection_id=' + encodeURIComponent(cloud.inspection_id) })
        return
      }
      store.clearActive()
      await this.loadOptions()
    } catch (error) {
      if (!this._visible) return
      const active = store.getActive()
      // 只有网络/服务故障才使用缓存继续查看，401/404 不绕过云端归属校验。
      if ((error.code === -1 || error.code >= 500) && active && active.inspection_id && !normalizeMission(active).terminal) {
        wx.navigateTo({ url: '/pages/mission-status/mission-status?inspection_id=' + encodeURIComponent(active.inspection_id) })
        return
      }
      this._recoveryFailed = true
      this.setData({ errorMsg: (error.message || '无法确认当前任务') + '；为避免重复启动，请重新进入巡检页后重试' })
    } finally { this._recovering = false }
  },
  async loadOptions() {
    this.setData({ loading: true, errorMsg: '' })
    const selectedId = wx.getStorageSync('tld_selected_field') || ''
    try {
      const results = await Promise.all([api.listFields(), api.listDevices()])
      const fields = unwrapItems(results[0]).map(normalizeField)
      const devices = (Array.isArray(results[1]) ? results[1] : []).map(normalizeDevice)
      if (!this._visible) return
      const selectedField = fields.find((field) => field.ready && field.field_id === (selectedId || (this.data.selectedField || {}).field_id)) || null
      const selectedDevice = devices.find((device) => device.selectable && device.device_id === (this.data.selectedDevice || {}).device_id) || null
      this.setData({ fields, devices, selectedField, selectedDevice, preflight: selectedDevice ? buildPreflight(selectedDevice) : null })
    } catch (error) {
      this.setData({ errorMsg: error.code === 404 ? '云端 V0.2 烟田/任务接口尚未就绪，暂不能提交真实巡检。' : (error.message || '启动选项加载失败') })
    } finally { this.setData({ loading: false }) }
  },
  selectField(e) { const field = this.data.fields[e.currentTarget.dataset.index]; if (field.ready) this.setData({ selectedField: field, errorMsg: '' }) },
  selectDevice(e) { const device = this.data.devices[e.currentTarget.dataset.index]; if (device.selectable) this.setData({ selectedDevice: device, errorMsg: '' }) },
  onName(e) { this.setData({ name: e.detail.value }) },
  next() {
    if (this.data.step === 1 && !this.data.selectedField) return this.setData({ errorMsg: '请选择状态为 READY 的烟田' })
    if (this.data.step === 2 && !this.data.selectedDevice) return this.setData({ errorMsg: '请选择状态为 READY 的已绑定设备' })
    if (this.data.step === 2) {
      const preflight = buildPreflight(this.data.selectedDevice)
      this.setData({ preflight })
      if (!preflight.ready) return this.setData({ errorMsg: '启动前检查未通过，请处理标红项目后刷新' })
    }
    this.setData({ step: Math.min(4, this.data.step + 1), errorMsg: '' })
  },
  previous() { this.setData({ step: Math.max(1, this.data.step - 1), errorMsg: '' }) },
  async submit() {
    if (this.data.submitting || this._recovering || this._recoveryFailed || !this.data.selectedField || !this.data.selectedDevice) return
    if (!this.data.selectedField.ready || !buildPreflight(this.data.selectedDevice).ready) return this.setData({ errorMsg: '烟田或设备启动检查未通过，请刷新后重试' })
    const key = 'start:' + this.data.selectedField.field_id + ':' + this.data.selectedDevice.device_id
    const requestId = store.getOrCreateRequestId(key, 'START')
    this.setData({ submitting: true, errorMsg: '' })
    try {
      const runMode = this.data.selectedDevice.is_simulated ? 'FAST_TEST' : 'REAL_DEVICE'
      const raw = await api.startInspection(this.data.selectedField.field_id, this.data.selectedDevice.device_id, this.data.name, requestId, runMode)
      const mission = normalizeMission(raw)
      if (!mission.inspection_id) throw { message: '云端响应缺少 inspection_id' }
      mission.field_name = mission.field_name || this.data.selectedField.display_name
      mission.device_name = mission.device_name || this.data.selectedDevice.display_name
      store.saveActive(mission)
      store.clearRequestId(key)
      if (this._visible) wx.navigateTo({ url: '/pages/mission-status/mission-status?inspection_id=' + encodeURIComponent(mission.inspection_id) })
    } catch (error) {
      this.setData({ errorMsg: error.message || '开始请求失败；可重试，客户端请求 ID 将保持不变' })
    } finally { this.setData({ submitting: false }) }
  },
  openDevices() { wx.navigateTo({ url: '/pages/devices/devices' }) },
})
