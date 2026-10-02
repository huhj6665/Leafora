const auth = require('../../utils/auth')
const api = require('../../utils/api')
const { unwrapItems, normalizeField } = require('../../utils/field-view')
const { syncTabBar } = require('../../utils/tabbar')

Page({
  data: { fields: [], loading: false, errorMsg: '' },
  onShow() { syncTabBar(this); this.load() },
  onPullDownRefresh() { this.load().finally(() => wx.stopPullDownRefresh()) },
  async load() {
    if (!auth.hasToken()) { wx.navigateTo({ url: '/pages/login/login' }); return }
    this.setData({ loading: true, errorMsg: '' })
    try {
      const result = await api.listFields()
      const fields = unwrapItems(result).map((field) => Object.assign(normalizeField(field), { display_image: '' }))
      this.setData({ fields })
      this.loadCovers(fields.slice(0, 12))
    } catch (error) {
      this.setData({ errorMsg: error.code === 404 ? '云端尚未提供烟田列表接口，请等待 Web V0.2 接口对齐。' : (error.message || '烟田加载失败') })
      if (error.isUnauthorized) wx.navigateTo({ url: '/pages/login/login' })
    } finally { this.setData({ loading: false }) }
  },
  async loadCovers(fields) {
    const loaded = await Promise.all(fields.map(async (field) => {
      if (!field.background_url) return field
      try { return Object.assign({}, field, { display_image: await api.downloadImage(field.background_url) }) }
      catch (error) { return field }
    }))
    const tail = this.data.fields.slice(loaded.length)
    this.setData({ fields: loaded.concat(tail) })
  },
  openField(e) { wx.navigateTo({ url: '/pages/field-detail/field-detail?field_id=' + encodeURIComponent(e.currentTarget.dataset.id) }) },
  createField() { wx.navigateTo({ url: '/pages/field-create/field-create' }) },
})
