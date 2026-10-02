const config = require('./utils/config')
const gate = require('./utils/network-gate')

App({
  onShow() {
    setTimeout(() => {
      const pages = getCurrentPages()
      const current = pages.length ? pages[pages.length - 1] : null
      if (current && current.route !== 'pages/network/network' && !gate.canEnterBusiness(config)) {
        wx.reLaunch({ url: '/pages/network/network' })
      }
    }, 0)
  },
  globalData: { user: null },
})
