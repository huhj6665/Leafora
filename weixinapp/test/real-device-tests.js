/** 本地 Node 页面桩：不访问服务，不提交真实任务，不模拟真机已通过。 */
const assert = require('assert')
const fs = require('fs')
const path = require('path')
const vm = require('vm')
const { createRequire } = require('module')
const api = require('../utils/api')
const auth = require('../utils/auth')
const devices = require('../utils/device-view')
const missions = require('../utils/mission-view')
const inspections = require('../utils/inspection-view')
const store = require('../utils/mission-store')
const spatial = require('../utils/spatial-view')
const telemetry = require('../utils/telemetry-view')

function harness(name) {
  const storage = { tld_access_token: 'test-session' }
  const navigation = []
  const timers = new Map()
  let nextTimer = 1
  const wx = {
    getStorageSync: (key) => storage[key], setStorageSync: (key, value) => { storage[key] = value },
    removeStorageSync: (key) => { delete storage[key] }, navigateTo: (options) => navigation.push(options.url),
    redirectTo: (options) => navigation.push(options.url),
  }
  global.wx = wx
  const filename = path.resolve(__dirname, '../pages/' + name + '/' + name + '.js')
  let definition
  const sandbox = { wx, module: { exports: {} }, require: createRequire(filename), Page: (value) => { definition = value },
    setInterval: (fn) => { const id = nextTimer++; timers.set(id, fn); return id }, clearInterval: (id) => timers.delete(id) }
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), sandbox, { filename })
  const page = Object.assign({}, definition, { data: JSON.parse(JSON.stringify(definition.data)), setData(value) { Object.assign(this.data, value) } })
  return { page, storage, timers, navigation, exports: sandbox.module.exports }
}

async function withApi(fn) {
  const saved = Object.assign({}, api)
  const previousWx = global.wx
  try { await fn() }
  finally { Object.assign(api, saved); if (previousWx) global.wx = previousWx; else delete global.wx }
}
function deferred() { let resolve; const promise = new Promise((done) => { resolve = done }); return { promise, resolve } }

async function run(test, asyncTest) {
  console.log('[9] 真实 Jetson 兼容性与页面生命周期')
  test('真实设备不是虚拟设备，规范虚拟设备标识保留', () => {
    assert.strictEqual(devices.normalizeDevice({ device_id: 'TLD_SIM_002' }).is_simulated, false)
    assert.strictEqual(devices.normalizeDevice({ device_id: 'TLD_JETSON_001' }).is_simulated, true)
  })
  test('云端 READY 不能掩盖 GPS/Camera/Inference 明确故障', () => {
    for (const item of [{ gps_fix: 'NO_FIX' }, { gps_fix: false }, { gps_fix: 0 }, { camera_status: 'ERROR' }, { inference_status: 'UNAVAILABLE' }, { camera_status: 'NOT_STARTED' }, { inference_status: 'NOT_STARTED' }]) {
      const device = Object.assign({ standard_state: 'READY' }, item)
      assert.strictEqual(devices.normalizeDevice(device).selectable, false)
      assert.strictEqual(devices.buildPreflight(device).ready, false)
    }
    assert.ok(devices.normalizeDevice({ standard_state: 'READY', inference_status: 'ERROR' }).unavailable_reason.includes('识别'))
  })
  test('普通 GPS Fix 不依赖网络 RTK，READY 缺省模块明细不捏造 RTK', () => {
    const preflight = devices.buildPreflight({ standard_state: 'READY', gps_fix: 'GPS Fix', camera_status: 'READY', inference_status: 'READY' })
    assert.strictEqual(preflight.ready, true)
    assert.ok(!preflight.rtk_hint.includes('RTK_FIXED'))
    assert.strictEqual(devices.buildPreflight({ standard_state: 'READY', gps_fix: null, camera_status: null }).ready, true)
  })
  test('提交/DELIVERED/RECEIVED 不等于设备已接受', () => {
    for (const ack_status of ['', 'PENDING', 'DELIVERED', 'RECEIVED']) assert.strictEqual(missions.normalizeMission({ status: 'STARTING', ack_status }).accepted, false)
  })
  test('待同步与完成冲突保持 SYNCING，列表也不能归为完成', () => {
    const raw = { status: 'COMPLETED', pending_sync_count: 2 }
    assert.strictEqual(missions.normalizeMission(raw).status, 'SYNCING')
    assert.strictEqual(missions.normalizeMission(raw).terminal, false)
    assert.strictEqual(inspections.splitEvents([raw]).history.length, 0)
    assert.strictEqual(inspections.normalizeEvent({ status: 'ENDING' }).sync_label, '等待同步完成')
    assert.strictEqual(missions.normalizeMission({ status: 'COMPLETED', sync_status: 'PENDING' }).status, 'SYNCING')
    assert.strictEqual(missions.normalizeMission({ status: 'SYNCING', pending_sync_count: 0 }).status, 'SYNCING')
  })
  test('真实 null 不显示 0，真实零值正确保留', () => {
    const live = telemetry.normalizeLive({ raw: { location: { altitude_msl_m: null, ground_speed_mps: 0 }, environment: { temperature: null, humidity: 0, co2: null, light: 0 } } })
    assert.strictEqual(live.location.altitude_text, '暂无有效数据')
    assert.strictEqual(live.location.speed_text, '0')
    assert.strictEqual(live.environment.temperature_text, '暂无有效数据')
    assert.strictEqual(live.environment.humidity_text, '0')
    assert.strictEqual(live.environment.co2_text, '暂无有效数据')
    assert.strictEqual(live.environment.light_text, '0')
  })
  test('最新 raw null/无效不被平滑旧数据覆盖，保留传感器陈旧提示', () => {
    const live = telemetry.normalizeLive({ raw: { location: { position_valid: false, fix_quality: 0, altitude_msl_m: null }, environment: { temperature: null, sampled_at: '2026-10-01T00:00:00Z', valid: false } }, display: { location: { position_valid: true, altitude_msl_m: 99 }, environment: { temperature: 20 } } }, Date.parse('2026-10-01T00:00:20Z'))
    assert.strictEqual(live.location.altitude_text, '暂无有效数据')
    assert.ok(live.location.fix_text.includes('定位无效'))
    assert.strictEqual(live.environment.temperature_text, '暂无有效数据')
    assert.ok(live.sample_hints.includes('链路中断'))
    assert.ok(live.sample_hints.includes('存在无效数据'))
  })
  test('真实 Fix 枚举准确，普通 Fix 不伪报 RTK_FIXED', () => {
    assert.strictEqual(telemetry.normalizeLive({ raw: { location: { latitude: 31, longitude: 121, fix_quality: 1, position_valid: true, rtk_status: 'GPS_FIX' } } }).location.fix_text, 'GPS_FIX')
    assert.strictEqual(telemetry.normalizeLive({ raw: { location: { fix_quality: 4 } } }).location.fix_text, 'RTK_FIXED')
  })
  test('缺失/null/无效定位点过滤，不伪造原点；有效原点保留', () => {
    for (const point of [{}, { x_pct: null, y_pct: 5, x: 8 }, { x: 2, y: NaN }, { x: 2, y: 3, position_valid: false }, { x_pct: 2, y_pct: 3, lat: null }]) assert.strictEqual(spatial.normalizePoint(point), null)
    assert.strictEqual(spatial.normalizePoint({ x_pct: 0, y_pct: 0 }).x_pct, 0)
  })
  test('真实设备来源与模拟底图校准分别标注', () => {
    const labels = telemetry.sourceLabels({ data_provenance: 'DEVICE', run_mode: 'REAL_DEVICE' }, { field_id: 'FIELD_A01', calibration_status: 'SIMULATED' })
    assert.strictEqual(labels.source_label, '真实设备数据来源')
    assert.ok(labels.calibration_hint.includes('不代表图片已获得真实地理坐标'))
  })
  test('非法经纬度/底图外百分比不贴边绘制，真实未报告进度不假造飞行', () => {
    assert.strictEqual(spatial.normalizePoint({ x_pct: 101, y_pct: 20 }), null)
    assert.strictEqual(spatial.normalizePoint({ x_pct: 20, y_pct: 20, latitude: 91 }), null)
    assert.strictEqual(telemetry.normalizeLive({ raw: { location: { position_valid: true, latitude: null, longitude: null, altitude_msl_m: 1 } } }).location.altitude_text, '暂无有效数据')
    assert.strictEqual(missions.normalizeMission({ status: 'RUNNING', progress: null }).progress_known, false)
    assert.strictEqual(missions.normalizeMission({ status: 'RUNNING', progress: 0 }).progress_known, true)
  })
  await asyncTest('历史详情过滤无效空间点、保留 null 环境与模拟校准警告', () => withApi(async () => {
    const h = harness('inspection-detail')
    const detail = h.exports.normalizeDetail({ status: 'COMPLETED', pending_sync_count: 2, data_provenance: 'DEVICE', environment: [{ temperature: null, humidity: 0 }], spatial: { field: { calibration_status: 'SIMULATED' }, track: [{ x: null, y: 2 }, { x: 0, y: 0 }], disease_points: [{ x: 2, y: 3, position_valid: false }] } })
    assert.strictEqual(detail.track_count, 1)
    assert.strictEqual(detail.disease_points.length, 0)
    assert.strictEqual(detail.latest_environment.temperature_text, '暂无有效数据')
    assert.strictEqual(detail.latest_environment.humidity_text, '0')
    assert.strictEqual(detail.status, 'SYNCING')
    assert.strictEqual(detail.is_simulated, false)
    assert.ok(detail.calibration_hint.includes('模拟校准'))
  }))
  await asyncTest('实际提交分支：真实 REAL_DEVICE，虚拟 FAST_TEST；重复点击只发送一次', () => withApi(async () => {
    for (const id of ['TLD_SIM_002', 'TLD_JETSON_001']) {
      const h = harness('mission')
      const wait = deferred()
      const calls = []
      api.startInspection = (...args) => { calls.push(args); return wait.promise }
      h.page._visible = true
      h.page.data.selectedField = { field_id: 'F', ready: true }
      h.page.data.selectedDevice = devices.normalizeDevice({ device_id: id, standard_state: 'READY' })
      const pending = h.page.submit()
      await h.page.submit()
      assert.strictEqual(calls.length, 1)
      assert.strictEqual(calls[0][4], id === 'TLD_SIM_002' ? 'REAL_DEVICE' : 'FAST_TEST')
      wait.resolve({ inspection_id: 'I', status: 'STARTING', ack_status: 'RECEIVED' })
      await pending
      assert.strictEqual(store.getActive().accepted, false)
    }
  }))
  await asyncTest('START 超时后页面重建重试复用请求 ID', () => withApi(async () => {
    const h = harness('mission')
    h.page._visible = true
    h.page.data.selectedField = { field_id: 'F', ready: true }
    h.page.data.selectedDevice = devices.normalizeDevice({ device_id: 'TLD_SIM_002', standard_state: 'READY' })
    const ids = []
    api.startInspection = async (field, device, name, id) => { ids.push(id); throw { code: -1, message: 'timeout' } }
    await h.page.submit()
    const data = JSON.parse(JSON.stringify(h.page.data))
    h.page.data = data // 页面数据重新加载，Storage 未清除。
    await h.page.submit()
    assert.strictEqual(ids[0], ids[1])
    assert.strictEqual(h.navigation.length, 0)
  }))
  await asyncTest('恢复以云端为准：清除陈旧缓存，不重复启动；网络故障仍可查看缓存', () => withApi(async () => {
    const h = harness('mission')
    h.page._visible = true
    store.saveActive({ inspection_id: 'OLD', status: 'RUNNING' })
    api.getCurrentInspection = async () => null
    api.listFields = async () => []
    api.listDevices = async () => []
    await h.page.recoverOrLoad()
    assert.strictEqual(store.getActive(), null)
    assert.strictEqual(h.navigation.length, 0)
    store.saveActive({ inspection_id: 'ACTIVE', status: 'RUNNING' })
    api.getCurrentInspection = async () => { throw { code: -1 } }
    await h.page.recoverOrLoad()
    assert.ok(h.navigation[0].includes('ACTIVE'))
  }))
  await asyncTest('重启且无本地活动缓存也能从 current 恢复，恢复并发只导航一次', () => withApi(async () => {
    const h = harness('mission')
    h.page._visible = true
    const wait = deferred()
    api.getCurrentInspection = () => wait.promise
    const pending = h.page.recoverOrLoad()
    await h.page.recoverOrLoad()
    wait.resolve({ inspection_id: 'CLOUD', status: 'SYNCING' })
    await pending
    assert.strictEqual(h.navigation.length, 1)
    assert.strictEqual(store.getActive().inspection_id, 'CLOUD')
  }))
  await asyncTest('无法核对当前任务/401 不用缓存绕过鉴权，不允许重复提交', () => withApi(async () => {
    const h = harness('mission')
    h.page._visible = true
    store.saveActive({ inspection_id: 'OLD', status: 'RUNNING' })
    api.getCurrentInspection = async () => { throw { code: 401, message: 'expired' } }
    await h.page.recoverOrLoad()
    assert.strictEqual(h.navigation.length, 0)
    assert.strictEqual(h.page._recoveryFailed, true)
    h.page.data.selectedField = { field_id: 'F', ready: true }
    h.page.data.selectedDevice = devices.normalizeDevice({ standard_state: 'READY' })
    let starts = 0
    api.startInspection = async () => { starts += 1 }
    await h.page.submit()
    assert.strictEqual(starts, 0)
  }))
  await asyncTest('状态页前后台/卸载只保留一个轮询，旧异步响应不更新隐藏页', () => withApi(async () => {
    const h = harness('mission-status')
    const wait = deferred()
    let reads = 0
    api.getInspection = () => { reads += 1; return wait.promise }
    api.getInspectionLive = async () => ({})
    api.getInspectionSpatial = async () => ({})
    h.page.onLoad({ inspection_id: 'I' })
    h.page.onShow()
    h.page.onShow()
    assert.strictEqual(h.timers.size, 1)
    assert.strictEqual(reads, 1)
    h.page.onHide()
    assert.strictEqual(h.timers.size, 0)
    wait.resolve({ inspection_id: 'I', status: 'RUNNING' })
    await new Promise((done) => setImmediate(done))
    assert.strictEqual(h.page.data.mission, null)
    h.page.onShow()
    await new Promise((done) => setImmediate(done))
    assert.strictEqual(h.page.data.mission.status, 'RUNNING')
    h.page.onUnload()
    assert.strictEqual(h.timers.size, 0)
  }))
  await asyncTest('END 超时不假成功且重试复用 ID，旧轮询不能覆盖 ENDING', () => withApi(async () => {
    const h = harness('mission-status')
    h.page.onLoad({ inspection_id: 'I' })
    h.page._visible = true
    h.page.data.mission = missions.normalizeMission({ inspection_id: 'I', status: 'RUNNING' })
    const ids = []
    api.getInspection = async () => { throw { code: -1 } }
    api.getInspectionLive = async () => ({})
    api.getInspectionSpatial = async () => ({})
    api.endInspection = async (id, request) => { ids.push(request); throw { code: -1, message: 'timeout' } }
    await h.page.doEnd()
    assert.strictEqual(h.page.data.mission.status, 'RUNNING')
    assert.ok(h.page.data.errorMsg.includes('未确认'))
    const old = deferred()
    api.getInspection = () => old.promise
    const poll = h.page.refresh()
    api.endInspection = async (id, request) => { ids.push(request); return { inspection_id: 'I', status: 'ENDING' } }
    await h.page.doEnd()
    assert.strictEqual(ids[0], ids[1])
    h.page.onHide()
    old.resolve({ inspection_id: 'I', status: 'RUNNING' })
    await poll
    assert.strictEqual(h.page.data.mission.status, 'ENDING')
  }))
  await asyncTest('轮询失败陈旧提示继续更新；旧任务实时采样不冒充新任务', () => withApi(async () => {
    const h = harness('mission-status')
    h.page.onLoad({ inspection_id: 'NEW' })
    h.page._visible = true
    h.page.data.live = { received_at: new Date(Date.now() - 20000).toISOString() }
    api.getInspection = async () => { throw { code: -1 } }
    api.getInspectionLive = async () => ({ raw: { inspection_id: 'OLD', environment: { temperature: 25 } } })
    api.getInspectionSpatial = async () => ({})
    await h.page.refresh()
    assert.strictEqual(h.page.data.freshness.state, 'interrupted')
    api.getInspection = async () => ({ inspection_id: 'NEW', status: 'STARTING' })
    await h.page.refresh()
    assert.strictEqual(h.page.data.live.environment.temperature_text, '暂无有效数据')
    assert.ok(h.page.data.errorMsg.includes('上一任务'))
  }))
  await asyncTest('退出会话清除旧账号活动缓存，不影响其它本地偏好', () => withApi(async () => {
    const h = harness('mission')
    h.storage.preference = 'keep'
    store.saveActive({ inspection_id: 'I', status: 'RUNNING' })
    store.getOrCreateRequestId('end:I', 'END')
    auth.clearSession()
    assert.strictEqual(store.getActive(), null)
    assert.strictEqual(h.storage.tld_mission_requests, undefined)
    assert.strictEqual(h.storage.preference, 'keep')
  }))
}

module.exports = { run }
