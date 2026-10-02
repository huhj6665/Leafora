const auth = require('../../utils/auth')
const api = require('../../utils/api')
const { isValidPhone, isValidCode, isValidPassword } = require('../../utils/validate')
const COUNTDOWN_SECONDS = 60

Page({
  data: {
    phone: '', code: '', password: '', confirmPassword: '', countdown: 0,
    sending: false, loading: false, message: '', errorMsg: '',
  },
  onLoad() {
    if (!auth.hasToken()) wx.redirectTo({ url: '/pages/login/login' })
  },
  onUnload() { if (this._timer) clearInterval(this._timer) },
  onPhone(e) { this.setData({ phone: e.detail.value, errorMsg: '' }) },
  onCode(e) { this.setData({ code: e.detail.value, errorMsg: '' }) },
  onPassword(e) { this.setData({ password: e.detail.value, errorMsg: '' }) },
  onConfirm(e) { this.setData({ confirmPassword: e.detail.value, errorMsg: '' }) },

  async sendCode() {
    const phone = this.data.phone.trim()
    if (!isValidPhone(phone)) return this.setData({ errorMsg: '请输入当前账号绑定的 11 位手机号' })
    if (this.data.sending || this.data.countdown > 0) return
    this.setData({ sending: true, errorMsg: '' })
    try {
      await api.sendPhonePasswordCode(phone)
      wx.showToast({ title: '验证码已发送', icon: 'success' })
      this.setData({ countdown: COUNTDOWN_SECONDS })
      this._timer = setInterval(() => {
        const next = this.data.countdown - 1
        this.setData({ countdown: Math.max(0, next) })
        if (next <= 0) { clearInterval(this._timer); this._timer = null }
      }, 1000)
    } catch (err) { this.setData({ errorMsg: err.message || '验证码发送失败' }) }
    finally { this.setData({ sending: false }) }
  },

  async submit() {
    const phone = this.data.phone.trim()
    const code = this.data.code.trim()
    if (!isValidPhone(phone)) return this.setData({ errorMsg: '请输入当前账号绑定的 11 位手机号' })
    if (!isValidCode(code)) return this.setData({ errorMsg: '请输入 6 位短信验证码' })
    if (!isValidPassword(this.data.password)) return this.setData({ errorMsg: '密码需为 6-128 位且同时包含字母和数字' })
    if (this.data.password !== this.data.confirmPassword) return this.setData({ errorMsg: '两次输入的密码不一致' })
    this.setData({ loading: true, errorMsg: '', message: '' })
    try {
      await api.setPassword(phone, code, this.data.password)
      // 云端设置密码后会提升 token_version，当前 JWT 随即失效。
      auth.clearSession()
      wx.showModal({
        title: '密码设置成功',
        content: '为保护账号，当前会话已退出。请使用手机号和新密码重新登录。',
        showCancel: false,
        success: () => wx.reLaunch({ url: '/pages/login/login' }),
      })
    } catch (err) {
      this.setData({ errorMsg: err.message || '设置失败' })
      if (err.isSessionExpired) wx.redirectTo({ url: '/pages/login/login' })
    } finally { this.setData({ loading: false }) }
  },
})
