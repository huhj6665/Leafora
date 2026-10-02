/**
 * 扫码流程封装。
 *
 * 发起真实 wx.scanCode()，严格区分设备配对码与 Web 登录码。
 */
const scanStore = require('./scan-store')
const { parseQrContent } = require('./qrcode-parser')

function scanAndOpenResult() {
  wx.scanCode({
    onlyFromCamera: true,
    scanType: ['qrCode'],
    success(res) {
      const parsed = parseQrContent(res.result || '')
      if (parsed.ok) {
        scanStore.set(parsed)
        wx.navigateTo({ url: '/pages/scan-result/scan-result' })
      } else {
        // 错误格式 / 缺少字段 / 不支持版本：明确提示，不进入结果页
        wx.showModal({
          title: '无法识别二维码',
          content: parsed.error,
          showCancel: false,
          confirmText: '知道了',
        })
      }
    },
    fail(err) {
      // 用户主动取消：静默返回首页，不弹错误提示
      if (err && err.errMsg && err.errMsg.indexOf('cancel') !== -1) {
        return
      }
      // 其它异常（如相机权限被拒）
      wx.showToast({ title: '扫码失败，请重试', icon: 'none' })
    },
  })
}

module.exports = { scanAndOpenResult }
