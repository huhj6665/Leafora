const auth = require('../../utils/auth')
const api = require('../../utils/api')
const config = require('../../utils/config')
const scanStore = require('../../utils/scan-store')
const { syncTabBar } = require('../../utils/tabbar')

Page({
  data: { user: null, avatarText: 'L', deviceCount: 0, server: '', loading: false },
  onShow() { syncTabBar(this); this.setData({ server: config.getApiBaseUrl() }); this.load() },
  async load() {
    if (!auth.hasToken()) { this.setData({ user: null }); return }
    this.setData({ loading: true })
    try { const results = await Promise.all([api.getProfile(), api.listDevices()]); auth.saveProfile(results[0]); this.setData({ user: results[0], avatarText: String(results[0].nickname || 'L').slice(0, 1), deviceCount: Array.isArray(results[1]) ? results[1].length : 0 }) }
    catch (error) { const user = auth.getProfile(); this.setData({ user, avatarText: user ? String(user.nickname || 'L').slice(0, 1) : 'L' }) }
    finally { this.setData({ loading: false }) }
  },
  login() { wx.navigateTo({ url: '/pages/login/login' }) },
  network() { wx.navigateTo({ url: '/pages/network/network?mode=settings' }) },
  devices() { wx.navigateTo({ url: '/pages/devices/devices' }) },
  password() { wx.navigateTo({ url: '/pages/password/password' }) },
  logout() { wx.showModal({ title: '退出登录', content: '局域网连接配置会保留。', success: (res) => { if (res.confirm) { auth.clearSession(); scanStore.clear(); getApp().globalData.user = null; this.setData({ user: null, deviceCount: 0 }) } } }) },
})
