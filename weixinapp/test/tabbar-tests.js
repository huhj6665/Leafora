const assert = require('assert')
const fs = require('fs')
const path = require('path')
const vm = require('vm')
const { createRequire } = require('module')
const { TABS, selectedIndex, syncTabBar } = require('../utils/tabbar')

function harness(route) {
  const filename = path.resolve(__dirname, '../custom-tab-bar/index.js')
  let definition
  const calls = []
  const toasts = []
  const current = { route }
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    require: createRequire(filename), Component: (value) => { definition = value },
    getCurrentPages: () => [current], wx: { switchTab: (options) => calls.push(options), showToast: (value) => toasts.push(value) },
  }, { filename })
  const bar = Object.assign({}, definition.methods, { data: JSON.parse(JSON.stringify(definition.data)), setData(value) { Object.assign(this.data, value) } })
  return { bar, definition, current, calls, toasts }
}

function run(test) {
  console.log('[10] 放大底部导航与路由回归')
  test('五项顺序/文字/页面不变，使用官方自定义 TabBar 入口', () => {
    const app = require('../app.json')
    assert.strictEqual(app.tabBar.custom, true)
    assert.deepStrictEqual(app.tabBar.list, TABS)
    assert.deepStrictEqual(TABS.map((item) => item.text), ['首页', '烟田', '巡检', '记录', '我的'])
  })
  test('实际路由选择正确，非 Tab 页面不误选首页', () => {
    TABS.forEach((item, index) => assert.strictEqual(selectedIndex(item.pagePath), index))
    assert.strictEqual(selectedIndex('/pages/profile/profile'), 4)
    assert.strictEqual(selectedIndex('pages/network/network'), -1)
  })
  test('组件首次挂载/回到页面正确恢复选中态', () => {
    const h = harness('pages/profile/profile')
    h.definition.lifetimes.attached.call(h.bar)
    assert.strictEqual(h.bar.data.selected, 4)
    h.current.route = 'pages/inspections/inspections'
    h.definition.pageLifetimes.show.call(h.bar)
    assert.strictEqual(h.bar.data.selected, 3)
  })
  test('重复点击当前页和切换中连点不重复导航', () => {
    const h = harness('pages/index/index')
    h.bar.syncSelection()
    const tap = (index) => h.bar.switchTab({ currentTarget: { dataset: { index } } })
    tap(0); tap(1); tap(2)
    assert.strictEqual(h.calls.length, 1)
    assert.strictEqual(h.calls[0].url, '/pages/fields/fields')
    assert.strictEqual(h.bar.data.selected, 0)
    h.calls[0].complete()
    tap(4)
    assert.strictEqual(h.calls.length, 2)
  })
  test('切换失败保留实际选中页并提供重试反馈', () => {
    const h = harness('pages/index/index')
    h.bar.syncSelection()
    h.bar.switchTab({ currentTarget: { dataset: { index: 3 } } })
    h.calls[0].fail(); h.calls[0].complete()
    assert.strictEqual(h.bar.data.selected, 0)
    assert.strictEqual(h.toasts.length, 1)
    h.bar.switchTab({ currentTarget: { dataset: { index: 3 } } })
    assert.strictEqual(h.calls.length, 2)
  })
  test('无效索引不导航；页面同步可安全兼容组件尚未挂载', () => {
    const h = harness('pages/index/index')
    for (const index of [-1, 10, 'bad', 1.5]) h.bar.switchTab({ currentTarget: { dataset: { index } } })
    assert.strictEqual(h.calls.length, 0)
    syncTabBar({ route: 'pages/profile/profile', getTabBar: () => h.bar })
    assert.strictEqual(h.bar.data.selected, 4)
    syncTabBar({ getTabBar: () => null })
    syncTabBar({})
  })
  test('放大字体、最小点击区和五个页面底部安全留白均存在', () => {
    const read = (file) => fs.readFileSync(path.resolve(__dirname, '..', file), 'utf8')
    assert.match(read('custom-tab-bar/index.wxss'), /font-size:\s*32rpx/)
    assert.match(read('custom-tab-bar/index.wxss'), /min-height:\s*48px/)
    assert.match(read('custom-tab-bar/index.wxss'), /env\(safe-area-inset-bottom\)/)
    TABS.forEach((item) => {
      assert.match(read(item.pagePath + '.wxml'), /class="[^"]*\btab-page\b/)
      assert.match(read(item.pagePath + '.js'), /syncTabBar\(this\)/)
    })
  })
}

module.exports = { run }
