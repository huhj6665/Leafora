const { TABS, selectedIndex } = require('../utils/tabbar')

Component({
  data: { selected: -1, list: TABS },
  lifetimes: { attached() { this.syncSelection() } },
  pageLifetimes: { show() { this._switching = false; this.syncSelection() } },
  methods: {
    syncSelection() {
      const pages = getCurrentPages()
      const current = pages[pages.length - 1]
      const selected = selectedIndex(current && current.route)
      if (selected !== -1) this.setData({ selected })
    },
    switchTab(event) {
      const index = Number(event.currentTarget.dataset.index)
      if (!Number.isInteger(index) || !TABS[index] || this._switching || index === this.data.selected) return
      this._switching = true
      wx.switchTab({
        url: '/' + TABS[index].pagePath,
        // 不提前改选中项；目标页显示时依据实际路由同步。
        fail: () => { wx.showToast({ title: '页面切换失败，请重试', icon: 'none' }); this.syncSelection() },
        complete: () => { this._switching = false },
      })
    },
  },
})
