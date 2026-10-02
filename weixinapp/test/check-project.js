/** 微信开发者工具导入前的项目结构静态检查。 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const errors = []
function fail(message) { errors.push(message) }
function read(relative) { return fs.readFileSync(path.join(ROOT, relative), 'utf8') }
function parseJson(relative) {
  try { return JSON.parse(read(relative)) }
  catch (error) { fail(relative + ' 不是合法 JSON：' + error.message); return null }
}

function existsWithExactCase(absolutePath) {
  const parsed = path.parse(absolutePath)
  const parts = absolutePath.slice(parsed.root.length).split(path.sep).filter(Boolean)
  let current = parsed.root
  for (const part of parts) {
    if (!fs.existsSync(current)) return false
    const entries = fs.readdirSync(current)
    if (entries.indexOf(part) === -1) return false
    current = path.join(current, part)
  }
  return true
}

const app = parseJson('app.json')
const project = parseJson('project.config.json')
const privateProject = fs.existsSync(path.join(ROOT, 'project.private.config.json'))
  ? parseJson('project.private.config.json') : null
parseJson('sitemap.json')

if (project) {
  if (project.compileType !== 'miniprogram') fail('project.config.json compileType 必须为 miniprogram')
  const appid = (privateProject && privateProject.appid) || project.appid
  if (!appid || appid === 'touristappid') {
    if (process.argv.includes('--require-appid')) fail('请在本地配置自己的 AppID 后进行真机或扫码验收')
    else console.warn('源码模板未配置正式 AppID；真机和扫码前需自行配置')
  }
  if (!project.libVersion || project.libVersion === 'trial') fail('project.config.json 应使用明确的基础库版本')
  if (project.miniprogramRoot !== './') fail('project.config.json miniprogramRoot 应为 ./')
}
if (app) {
  if (!Array.isArray(app.pages) || app.pages[0] !== 'pages/network/network') fail('首次启动页必须是顶层局域网连接门')
  const tabs = app.tabBar && app.tabBar.list
  const expectedTabs = ['pages/index/index', 'pages/fields/fields', 'pages/mission/mission', 'pages/inspections/inspections', 'pages/profile/profile']
  if (!Array.isArray(tabs) || tabs.length !== expectedTabs.length || tabs.some((item, index) => item.pagePath !== expectedTabs[index])) {
    fail('TabBar 必须按首页、烟田、巡检、记录、我的注册')
  }
}
if (privateProject && privateProject.setting) {
  if (privateProject.setting.urlCheck !== false) fail('开发配置 urlCheck 必须为 false')
  if (privateProject.setting.useLanDebug !== true) fail('开发配置 useLanDebug 必须为 true')
}

const runtimeJs = []
if (app && Array.isArray(app.pages)) {
  app.pages.forEach((page) => {
    const jsRelative = page + '.js'
    ;['.js', '.json', '.wxml', '.wxss'].forEach((extension) => {
      const absolute = path.join(ROOT, page + extension)
      if (!fs.existsSync(absolute)) fail('缺少页面文件：' + page + extension)
      else if (!existsWithExactCase(absolute)) fail('页面路径大小写不一致：' + page + extension)
    })
    parseJson(page + '.json')
    runtimeJs.push(jsRelative)

    const js = read(jsRelative)
    const wxml = read(page + '.wxml')
    const handlers = []
    const eventPattern = /(?:bind|catch|capture-bind|capture-catch)[\w:-]*="([A-Za-z_$][\w$]*)"/g
    let match
    while ((match = eventPattern.exec(wxml))) handlers.push(match[1])
    handlers.forEach((handler) => {
      if (!new RegExp('\\b' + handler.replace(/[$]/g, '\\$&') + '\\s*\\(').test(js)) {
        fail(page + '.wxml 引用了不存在的事件处理器：' + handler)
      }
    })
  })
}

if (app && app.tabBar && app.tabBar.custom) {
  const component = 'custom-tab-bar/index'
  ;['.js', '.json', '.wxml', '.wxss'].forEach((extension) => {
    const absolute = path.join(ROOT, component + extension)
    if (!existsWithExactCase(absolute)) fail('自定义 TabBar 缺少文件或大小写错误：' + component + extension)
  })
  const componentConfig = parseJson(component + '.json')
  if (!componentConfig || componentConfig.component !== true) fail('自定义 TabBar 必须声明 component: true')
  runtimeJs.push(component + '.js')
  const componentJs = read(component + '.js')
  const events = read(component + '.wxml').matchAll(/(?:bind|catch)[\w:-]*="([A-Za-z_$][\w$]*)"/g)
  for (const event of events) {
    if (!new RegExp('\\b' + event[1] + '\\s*\\(').test(componentJs)) fail('自定义 TabBar 事件不存在：' + event[1])
  }
  const declaredTabs = require('../utils/tabbar').TABS
  if (JSON.stringify(declaredTabs) !== JSON.stringify(app.tabBar.list)) fail('自定义 TabBar 与 app.json 路由/文字不一致')
  app.tabBar.list.forEach((tab) => {
    if (!/class="[^"]*\btab-page\b/.test(read(tab.pagePath + '.wxml'))) fail('Tab 页面缺少导航底部留白：' + tab.pagePath)
    if (!/syncTabBar\(this\)/.test(read(tab.pagePath + '.js'))) fail('Tab 页面缺少选中态同步：' + tab.pagePath)
  })
}

runtimeJs.push('app.js')
fs.readdirSync(path.join(ROOT, 'utils')).filter((name) => name.endsWith('.js')).forEach((name) => runtimeJs.push('utils/' + name))
runtimeJs.forEach((relative) => {
  const source = read(relative)
  const requirePattern = /require\(['"]([^'"]+)['"]\)/g
  let match
  while ((match = requirePattern.exec(source))) {
    const request = match[1]
    if (!request.startsWith('.')) {
      fail(relative + ' 使用了小程序运行时未声明依赖：' + request)
      continue
    }
    let target = path.resolve(path.dirname(path.join(ROOT, relative)), request)
    if (!path.extname(target)) target += '.js'
    if (!fs.existsSync(target)) fail(relative + ' require 路径不存在：' + request)
    else if (!existsWithExactCase(target)) fail(relative + ' require 路径大小写不一致：' + request)
  }
  if (/\brequire\(['"](?:fs|path|http|https|os|child_process)['"]\)/.test(source)) {
    fail(relative + ' 使用了 Node 专用 API')
  }
})

const allRuntime = runtimeJs.map(read).join('\n')
if (/\/platform\/events[^'"\n]*['"]\s*,?\s*.*(?:POST|PATCH)/i.test(allRuntime)) fail('检测到远程创建或推进巡检调用')
if (/mqtt\.connect|require\(['"]mqtt['"]\)/i.test(allRuntime)) fail('检测到小程序直接连接 MQTT')
if (!/\/inspections\/start/.test(read('utils/api.js')) || !/\/end/.test(read('utils/api.js'))) fail('缺少 V0.2 START/END API 封装')

const networkPageText = ['pages/network/network.js', 'pages/network/network.wxml'].map(read).join('\n')
if (/10\.136\.82\.3/.test(networkPageText)) fail('云端连接页面不得在交互文案或检查清单中写死旧局域网 IP')

if (errors.length) {
  console.error('项目专项检查失败：')
  errors.forEach((error) => console.error('  ✗ ' + error))
  process.exit(1)
}
console.log('项目专项检查通过：JSON、页面文件、大小写、事件处理器、require 路径和运行时依赖均正常。')
