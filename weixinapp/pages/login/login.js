const auth = require('../../utils/auth')
const api = require('../../utils/api')
const { isValidPhone, isValidCode, isValidPassword } = require('../../utils/validate')
const COUNTDOWN_SECONDS = 60

Page({
  data: {
    tab: 'code', phone: '', code: '', password: '', countdown: 0,
    sending: false, loading: false, errorMsg: '', redirect: '',
  },

  onLoad(options) {
    const redirect = options && options.redirect ? decodeURIComponent(options.redirect) : ''
    if (redirect === '/pages/scan-result/scan-result') this.setData({ redirect })
  },
  onUnload() { if (this._timer) clearInterval(this._timer) },
  switchTab(e) { this.setData({ tab: e.currentTarget.dataset.tab, errorMsg: '' }) },
  onPhoneInput(e) { this.setData({ phone: e.detail.value, errorMsg: '' }) },
  onCodeInput(e) { this.setData({ code: e.detail.value, errorMsg: '' }) },
  onPasswordInput(e) { this.setData({ password: e.detail.value, errorMsg: '' }) },

  async sendCode() {
    const phone = this.data.phone.trim()
    if (!isValidPhone(phone)) return this.setData({ errorMsg: '请输入正确的 11 位手机号' })
    if (this.data.sending || this.data.countdown) return
    this.setData({ sending: true, errorMsg: '' })
    try {
      await api.sendPhoneCode(phone)
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

  loginByCode() {
    const phone = this.data.phone.trim()
    const code = this.data.code.trim()
    if (!isValidPhone(phone)) return this.setData({ errorMsg: '请输入正确的 11 位手机号' })
    if (!isValidCode(code)) return this.setData({ errorMsg: '请输入 6 位数字验证码' })
    return this.doLogin(() => api.loginByPhone(phone, code))
  },

  loginByPassword() {
    const phone = this.data.phone.trim()
    if (!isValidPhone(phone)) return this.setData({ errorMsg: '请输入正确的 11 位手机号' })
    if (!isValidPassword(this.data.password)) return this.setData({ errorMsg: '密码需为 6-128 位且同时包含字母和数字' })
    return this.doLogin(() => api.loginByPassword(phone, this.data.password))
  },

  async doLogin(loginFn) {
    if (this.data.loading) return
    this.setData({ loading: true, errorMsg: '' })
    try {
      const tokenData = await loginFn()
      if (!auth.saveSession(tokenData)) throw { message: '登录响应缺少访问令牌' }
      if (this.data.redirect) wx.redirectTo({ url: this.data.redirect })
      else wx.reLaunch({ url: '/pages/index/index' })
    } catch (err) { this.setData({ errorMsg: err.message || '登录失败，请重试' }) }
    finally { this.setData({ loading: false }) }
  },
})
