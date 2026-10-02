/** 复用实际 WXSS 做浏览器局部排版验收，不替代微信编译/真机验证。
 * 可选工具：NODE_PATH 指向带 playwright 的 Node 包目录后运行本文件。
 */
const fs = require('fs')
const path = require('path')
const assert = require('assert')
const { chromium } = require('playwright')
const { TABS } = require('../utils/tabbar')
const ROOT = path.resolve(__dirname, '..')

async function run() {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' })
  const output = path.join(__dirname, 'ui-preview')
  fs.mkdirSync(output, { recursive: true })
  try {
    for (const width of [320, 375, 430]) {
      for (const safeBottom of [0, 34]) {
        const scale = (source) => source.replace(/([\d.]+)rpx/g, (_, value) => Number(value) * width / 750 + 'px')
          .replace(/(?:env|constant)\(safe-area-inset-bottom\)/g, safeBottom + 'px')
          .replace(/:host/g, 'body')
        const tabCss = scale(fs.readFileSync(path.join(ROOT, 'custom-tab-bar/index.wxss'), 'utf8'))
        const homeCss = scale(fs.readFileSync(path.join(ROOT, 'pages/index/index.wxss'), 'utf8'))
        const appCss = scale(fs.readFileSync(path.join(ROOT, 'app.wxss'), 'utf8')).replace(/\bpage\s*\{/g, 'body {')
        const tabHtml = TABS.map((tab, index) => '<button class="tab-item ' + (index === 0 ? 'is-selected' : '') + '"><span class="tab-label">' + tab.text + '</span>' + (index === 0 ? '<div class="tab-indicator"></div>' : '') + '</button>').join('')
        const page = await browser.newPage({ viewport: { width, height: 280 }, deviceScaleFactor: 2 })
        await page.setContent('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>' + appCss + homeCss + tabCss +
          'body{margin:0} .home{padding-top:16px} .devices-link .strong{font-size:14px} .devices-link span{display:block} .devices-link .description{margin-top:4px;font-size:11px;color:#7E8B83} .devices-link .arrow{font-size:24px;color:#4F7561} button{font-family:inherit} .system-indicator{position:fixed;bottom:6px;left:35%;width:30%;height:4px;border-radius:3px;background:#171B18;z-index:1001}</style>' +
          '<main class="home tab-page"><div class="devices-link"><div><span class="strong">设备状态</span><span class="description">查看在线、GPS、相机与同步状态</span></div><span class="arrow">›</span></div></main><nav class="tab-bar"><div class="tab-row">' + tabHtml + '</div></nav>' + (safeBottom ? '<div class="system-indicator"></div>' : '') + '</html>')
        const layout = await page.evaluate(() => {
          const bar = document.querySelector('.tab-bar').getBoundingClientRect()
          const bottomPadding = parseFloat(getComputedStyle(document.querySelector('.tab-bar')).paddingBottom)
          return { bar: { top: bar.top, bottom: bar.bottom }, bottomPadding, items: [...document.querySelectorAll('.tab-item')].map((item) => {
            const box = item.getBoundingClientRect()
            const label = item.querySelector('.tab-label').getBoundingClientRect()
            return { left: box.left, right: box.right, height: box.height, labelLeft: label.left, labelRight: label.right, fontSize: parseFloat(getComputedStyle(item.querySelector('.tab-label')).fontSize) }
          }), cardBottom: document.querySelector('.devices-link').getBoundingClientRect().bottom }
        })
        assert.strictEqual(layout.items.length, 5)
        for (const item of layout.items) {
          assert.ok(item.height >= 48)
          assert.ok(item.left >= 0 && item.right <= width)
          assert.ok(item.labelLeft >= item.left && item.labelRight <= item.right)
          assert.ok(item.fontSize >= 13.6)
        }
        assert.ok(layout.cardBottom < layout.bar.top)
        assert.ok(layout.bottomPadding >= safeBottom)
        for (let index = 1; index < 5; index += 1) assert.ok(layout.items[index].left >= layout.items[index - 1].right)
        if (safeBottom === 34) await page.screenshot({ path: path.join(output, 'tabbar-' + width + '.png') })
        console.log('排版通过：' + width + 'px / 安全区 ' + safeBottom + 'px / 字号 ' + layout.items[0].fontSize + 'px')
        await page.close()
      }
    }
  } finally { await browser.close() }
}
run().catch((error) => { console.error(error); process.exitCode = 1 })
