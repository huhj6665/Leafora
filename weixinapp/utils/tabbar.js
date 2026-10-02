/** 仅负责导航展示，业务鉴权和网络门仍由原页面处理。 */
const TABS = [
  { pagePath: 'pages/index/index', text: '首页' },
  { pagePath: 'pages/fields/fields', text: '烟田' },
  { pagePath: 'pages/mission/mission', text: '巡检' },
  { pagePath: 'pages/inspections/inspections', text: '记录' },
  { pagePath: 'pages/profile/profile', text: '我的' },
]

function selectedIndex(route) { return TABS.findIndex((item) => item.pagePath === String(route || '').replace(/^\//, '')) }
function syncTabBar(page) {
  if (!page || typeof page.getTabBar !== 'function') return
  const selected = selectedIndex(page.route)
  const bar = page.getTabBar()
  if (bar && selected !== -1) bar.setData({ selected })
}

module.exports = { TABS, selectedIndex, syncTabBar }
