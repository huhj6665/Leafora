Page({
  data: { name: '', source: '待选择' },
  onName(e) { this.setData({ name: e.detail.value }) },
  explain() { wx.showModal({ title: '需要设备能力', content: '无人机拍摄、边界识别和控制点确认需连接支持该能力的设备。当前演示闭环请使用预置 A-01；这里不会伪造创建成功。', showCancel: false }) },
})
