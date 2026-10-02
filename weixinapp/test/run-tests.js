/** 小程序纯函数测试：node test/run-tests.js */
const assert = require('assert')
const qr = require('../utils/qrcode-parser')
const validate = require('../utils/validate')
const api = require('../utils/api')
const scanStore = require('../utils/scan-store')
const { toDisplayData } = require('../utils/result-view')
const { mapOperationError, mapConfirmResponse } = require('../utils/error-map')
const inspections = require('../utils/inspection-view')
const config = require('../utils/config')
const serverSettings = require('../utils/server-settings')
const requestUtils = require('../utils/request')
const { diagnoseNetworkError } = require('../utils/network-diagnostics')
const gate = require('../utils/network-gate')
const devices = require('../utils/device-view')
const fields = require('../utils/field-view')
const missions = require('../utils/mission-view')
const missionStore = require('../utils/mission-store')
const spatial = require('../utils/spatial-view')

let passed = 0
let failed = 0
function test(name, fn) {
  try { fn(); passed += 1; console.log('  ✓ ' + name) }
  catch (error) { failed += 1; console.log('  ✗ ' + name); console.log('      ' + error.message) }
}

const NOW = Date.parse('2026-09-27T08:00:00Z')
const deviceQr = {
  type: 'tld_device_pairing', version: '2.0', device_id: 'TLD_JETSON_001',
  pairing_session_id: 'PAIR_12345678', pairing_token: 'secret-pairing-token',
  expires_at: '2026-09-27T08:05:00Z',
}
const webQr = {
  type: 'tld_web_login', version: '1.0', login_session_id: 'LOGIN_12345678',
  scan_token: 'secret-scan-token', expires_at: '2026-09-27T08:02:00Z',
}

console.log('[1] 手机号身份输入校验')
test('大陆手机号通过', () => assert.strictEqual(validate.isValidPhone('13812345678'), true))
test('非法手机号拒绝', () => assert.strictEqual(validate.isValidPhone('12812345678'), false))
test('六位验证码通过', () => assert.strictEqual(validate.isValidCode('123456'), true))
test('非六位验证码拒绝', () => assert.strictEqual(validate.isValidCode('12345'), false))
test('字母数字密码通过', () => assert.strictEqual(validate.isValidPassword('leafora123'), true))
test('过短或单一字符密码拒绝', () => {
  assert.strictEqual(validate.isValidPassword('a1'), false)
  assert.strictEqual(validate.isValidPassword('12345678'), false)
})

console.log('[2] 已冻结 API 请求参数')
const build = api.buildParams
test('验证码发送参数', () => assert.deepStrictEqual(build.buildSendCodeParams('13812345678'), { phone: '13812345678' }))
test('手机号验证码登录参数', () => assert.deepStrictEqual(build.buildPhoneLoginParams('13812345678', '123456'), { phone: '13812345678', code: '123456' }))
test('手机号密码参数不使用 username', () => assert.deepStrictEqual(build.buildPhonePasswordParams('13812345678', 'leafora123'), { phone: '13812345678', password: 'leafora123' }))
test('设置密码参数包含手机号、验证码和新密码', () => assert.deepStrictEqual(build.buildSetPasswordParams('13812345678', '123456', 'leafora123'), {
  phone: '13812345678', code: '123456', new_password: 'leafora123',
}))
test('设备配对确认仅发送协议字段', () => assert.deepStrictEqual(build.buildDevicePairingParams(deviceQr), {
  device_id: 'TLD_JETSON_001', pairing_session_id: 'PAIR_12345678', pairing_token: 'secret-pairing-token',
}))
test('Web 登录确认不发送 poll_token', () => assert.deepStrictEqual(build.buildWebLoginConfirmParams(webQr), { scan_token: 'secret-scan-token' }))
test('解绑只发送设备编号', () => assert.deepStrictEqual(build.buildUnbindParams('TLD_JETSON_001'), { device_id: 'TLD_JETSON_001' }))
test('开始巡检发送烟田、设备、客户端请求 ID 和运行模式', () => assert.deepStrictEqual(
  build.buildStartInspectionParams('FIELD_A01', 'TLD_JETSON_001', '上午巡检', 'START_001', 'FAST_TEST'),
  { field_id: 'FIELD_A01', device_id: 'TLD_JETSON_001', client_request_id: 'START_001', name: '上午巡检', run_mode: 'FAST_TEST' }
))
test('结束巡检参数复用客户端请求 ID', () => assert.deepStrictEqual(build.buildEndInspectionParams('END_001'), { client_request_id: 'END_001' }))
test('任务请求参数不包含客户端 user_id', () => assert.strictEqual(Object.prototype.hasOwnProperty.call(build.buildStartInspectionParams('F', 'D', '', 'R'), 'user_id'), false))

console.log('[3] 二维码 V2 与 Web 登录严格分流')
test('设备 V2 解析成功', () => {
  const result = qr.parseQrContent(JSON.stringify(deviceQr), NOW)
  assert.strictEqual(result.ok, true)
  assert.strictEqual(result.data.kind, 'device_pairing')
  assert.strictEqual(result.data.is_expired, false)
})
test('Web 登录码解析成功', () => {
  const result = qr.parseQrContent(JSON.stringify(webQr), NOW)
  assert.strictEqual(result.ok, true)
  assert.strictEqual(result.data.kind, 'web_login')
})
test('旧版 pairing_code 协议被拒绝', () => {
  const result = qr.parseQrContent(JSON.stringify({ type: 'tld_device_pairing', version: '1.0', device_id: 'TLD_SIM_001', pairing_code: 'OLD' }), NOW)
  assert.strictEqual(result.ok, false)
  assert.ok(result.error.indexOf('版本') !== -1)
})
test('设备码缺少会话 ID 被拒绝', () => {
  const value = Object.assign({}, deviceQr); delete value.pairing_session_id
  assert.strictEqual(qr.parseQrContent(JSON.stringify(value), NOW).ok, false)
})
test('Web 码缺少 scan_token 被拒绝', () => {
  const value = Object.assign({}, webQr); delete value.scan_token
  assert.strictEqual(qr.parseQrContent(JSON.stringify(value), NOW).ok, false)
})
test('无效 expires_at 被拒绝', () => {
  assert.strictEqual(qr.parseQrContent(JSON.stringify(Object.assign({}, deviceQr, { expires_at: 'tomorrow' })), NOW).ok, false)
})
test('过期仍是格式正确但标注 expired', () => {
  const result = qr.parseQrContent(JSON.stringify(deviceQr), Date.parse('2026-09-27T08:06:00Z'))
  assert.strictEqual(result.ok, true)
  assert.strictEqual(result.data.is_expired, true)
})
test('非支持类型与错误 JSON 被拒绝', () => {
  assert.strictEqual(qr.parseQrContent('{bad', NOW).ok, false)
  assert.strictEqual(qr.parseQrContent(JSON.stringify({ type: 'other' }), NOW).ok, false)
})
test('超长二维码被拒绝', () => assert.strictEqual(qr.parseQrContent('x'.repeat(5000), NOW).ok, false))
test('重复扫码保持相同解析结果', () => {
  const a = qr.parseQrContent(JSON.stringify(deviceQr), NOW)
  const b = qr.parseQrContent(JSON.stringify(deviceQr), NOW)
  assert.deepStrictEqual(a.data, b.data)
})

console.log('[4] Token 安全与登录续接')
test('展示映射不包含配对 Token', () => {
  const view = toDisplayData(qr.parseQrContent(JSON.stringify(deviceQr), NOW), NOW)
  assert.strictEqual(view.deviceId, 'TLD_JETSON_001')
  assert.strictEqual(Object.prototype.hasOwnProperty.call(view, 'pairing_token'), false)
  assert.strictEqual(JSON.stringify(view).indexOf('secret-pairing-token'), -1)
})
test('Web 展示映射不包含 scan_token', () => {
  const view = toDisplayData(qr.parseQrContent(JSON.stringify(webQr), NOW), NOW)
  assert.strictEqual(JSON.stringify(view).indexOf('secret-scan-token'), -1)
})
test('短时内存可续接登录，过期自动清理', () => {
  const parsed = qr.parseQrContent(JSON.stringify(deviceQr), NOW)
  scanStore.set(parsed, NOW)
  assert.strictEqual(scanStore.get(NOW + 1000).ok, true)
  assert.strictEqual(scanStore.get(NOW + 6 * 60 * 1000), null)
})

console.log('[5] 云端错误状态映射')
test('网络失败允许重试', () => assert.deepStrictEqual(mapOperationError('pairing', { code: -1 }), { state: 'network_error', message: '网络失败，请检查连接后重试', retryable: true }))
test('配对过期提示刷新 Jetson 二维码', () => assert.strictEqual(mapOperationError('pairing', { code: 410 }).state, 'expired'))
test('当前用户已绑定按幂等成功处理', () => assert.strictEqual(mapOperationError('pairing', { code: 409, message: '设备已属于当前用户' }).idempotent, true))
test('绑定他人不泄露用户信息', () => assert.strictEqual(mapOperationError('pairing', { message: '设备已绑定其他用户' }).message, '设备已绑定其他账号，无法继续'))
test('Web 取消与已消费区分', () => {
  assert.strictEqual(mapOperationError('web_login', { message: 'cancelled' }).state, 'cancelled')
  assert.strictEqual(mapOperationError('web_login', { code: 409, message: 'consumed' }).state, 'consumed')
})
test('HTTP 成功体中的状态机仍区分确认与过期', () => {
  assert.strictEqual(mapConfirmResponse('web_login', { status: 'CONFIRMED' }).state, 'success')
  assert.strictEqual(mapConfirmResponse('web_login', { status: 'EXPIRED' }).state, 'expired')
})

console.log('[6] 局域网配置与请求错误诊断')
test('常见私有 IPv4 和局域网主机名可归一化', () => {
  assert.strictEqual(config.buildServerConfig(' 192.168.1.10 ', '8000').apiBaseUrl, 'http://192.168.1.10:8000/api')
  assert.strictEqual(config.buildServerConfig('192.168.001.010', '8000').host, '192.168.1.10')
  assert.strictEqual(config.buildServerConfig('172.16.5.6', 9000).healthUrl, 'http://172.16.5.6:9000/api/health')
  assert.strictEqual(config.buildServerConfig('Leafora-PC', 8000).host, 'leafora-pc')
})
test('空地址、回环地址、监听地址和公网 IPv4 被拒绝', () => {
  assert.strictEqual(config.validateHost('').ok, false)
  assert.strictEqual(config.validateHost('localhost').ok, false)
  assert.strictEqual(config.validateHost('127.0.0.1').ok, false)
  assert.strictEqual(config.validateHost('0.0.0.0').ok, false)
  assert.strictEqual(config.validateHost('8.8.8.8').ok, false)
})
test('端口必须为 1 到 65535 的整数', () => {
  assert.strictEqual(config.validatePort('').ok, false)
  assert.strictEqual(config.validatePort('0').ok, false)
  assert.strictEqual(config.validatePort('65536').ok, false)
  assert.strictEqual(config.validatePort('80.5').ok, false)
  assert.strictEqual(config.validatePort('8000').value, 8000)
})
test('服务器配置可写入、读取并只清除自己的 Storage', () => {
  const storage = { unrelated_preference: 'keep-me' }
  global.wx = {
    getStorageSync: (key) => storage[key],
    setStorageSync: (key, value) => { storage[key] = value },
    removeStorageSync: (key) => { delete storage[key] },
  }
  assert.strictEqual(config.saveServerConfig('192.168.50.12', 8800).ok, true)
  assert.strictEqual(config.getCurrentServerConfig().origin, 'http://192.168.50.12:8800')
  config.clearServerConfig()
  assert.strictEqual(config.getCurrentServerConfig().origin, config.LAN_API_ORIGIN)
  assert.strictEqual(storage.unrelated_preference, 'keep-me')
  delete global.wx
})
test('切换服务器清理登录会话，同地址保存不清理', () => {
  let current = config.buildServerConfig('192.168.1.20', 8000)
  let cleared = 0
  const fakeConfig = {
    LAN_API_ORIGIN: config.LAN_API_ORIGIN,
    getCurrentServerConfig: () => current,
    buildServerConfig: config.buildServerConfig,
    saveServerConfig: (host, port) => { current = config.buildServerConfig(host, port); return current },
    clearHealthVerification: () => {},
  }
  const fakeAuth = { clearSession: () => { cleared += 1 } }
  global.wx = { removeStorageSync: () => {} }
  assert.strictEqual(serverSettings.applyServerChange(fakeConfig, fakeAuth, '192.168.1.21', 8000).sessionCleared, true)
  assert.strictEqual(cleared, 1)
  assert.strictEqual(serverSettings.applyServerChange(fakeConfig, fakeAuth, '192.168.1.21', 8000).sessionCleared, false)
  assert.strictEqual(cleared, 1)
  delete global.wx
})
test('API 地址覆盖值只保留一个 /api', () => {
  assert.strictEqual(config.normalizeBaseUrl('http://192.168.1.10:8000/api/'), 'http://192.168.1.10:8000')
  global.wx = { getStorageSync: () => 'http://192.168.1.10:8000/api' }
  assert.strictEqual(requestUtils.absoluteUrl('/health'), 'http://192.168.1.10:8000/api/health')
  assert.strictEqual(requestUtils.absoluteUrl('/api/health'), 'http://192.168.1.10:8000/api/health')
  delete global.wx
})
test('健康检查不会把旧服务器 JWT 发给候选服务器', () => {
  assert.strictEqual(Object.prototype.hasOwnProperty.call(requestUtils.buildHeaders({ auth: false }, 'secret-jwt'), 'Authorization'), false)
  assert.strictEqual(requestUtils.buildHeaders({}, 'secret-jwt').Authorization, 'Bearer secret-jwt')
})
test('验证码错误不会被误判为登录会话过期', () => {
  assert.strictEqual(requestUtils.isCredentialFailure('验证码错误或已过期'), true)
  assert.strictEqual(requestUtils.isCredentialFailure('登录已过期'), false)
})
test('超时和域名校验错误给出不同诊断', () => {
  assert.strictEqual(diagnoseNetworkError({ code: -1, raw: { errMsg: 'request:fail timeout' } }).kind, 'timeout')
  assert.strictEqual(diagnoseNetworkError({ code: -1, raw: { errMsg: 'url not in domain list' } }).kind, 'domain_check')
})
test('离线、拒绝、TLS、HTTP 与未知网络错误分别映射', () => {
  assert.strictEqual(diagnoseNetworkError({ raw: { errMsg: 'network is disconnected' } }).kind, 'offline')
  assert.strictEqual(diagnoseNetworkError({ raw: { errMsg: 'connect ECONNREFUSED' } }).kind, 'refused')
  assert.strictEqual(diagnoseNetworkError({ raw: { errMsg: 'SSL handshake failed' } }).kind, 'tls_error')
  assert.strictEqual(diagnoseNetworkError({ code: 503, message: 'degraded' }).kind, 'server_error')
  assert.strictEqual(diagnoseNetworkError({ code: -1, message: 'unknown' }).kind, 'unreachable')
})
test('健康检查仅 ok/healthy 放行，degraded 不放行', () => {
  assert.strictEqual(gate.healthOutcome({ status: 'ok' }).ok, true)
  assert.strictEqual(gate.healthOutcome({ status: 'healthy' }).ok, true)
  assert.strictEqual(gate.healthOutcome({ status: 'degraded' }).ok, false)
  assert.strictEqual(gate.healthOutcome({}).ok, false)
})
test('未配置或未验证不能进入业务区', () => {
  assert.strictEqual(gate.canEnterBusiness({ hasExplicitServerConfig: () => false, isCurrentServerVerified: () => true }), false)
  assert.strictEqual(gate.canEnterBusiness({ hasExplicitServerConfig: () => true, isCurrentServerVerified: () => false }), false)
  assert.strictEqual(gate.canEnterBusiness({ hasExplicitServerConfig: () => true, isCurrentServerVerified: () => true }), true)
})
test('健康验证只对当前服务器生效，清除配置后失效', () => {
  const storage = {}
  global.wx = { getStorageSync: (key) => storage[key], setStorageSync: (key, value) => { storage[key] = value }, removeStorageSync: (key) => { delete storage[key] } }
  config.saveServerConfig('192.168.1.10', 8000)
  config.markHealthVerified('http://192.168.1.10:8000', NOW)
  assert.strictEqual(config.isCurrentServerVerified(), true)
  config.saveServerConfig('192.168.1.11', 8000)
  assert.strictEqual(config.isCurrentServerVerified(), false)
  config.clearServerConfig()
  assert.strictEqual(config.hasExplicitServerConfig(), false)
  delete global.wx
})

console.log('[7] 设备、烟田与任务状态机')
test('只有 READY 设备可选择', () => {
  assert.strictEqual(devices.normalizeDevice({ device_id: 'D0', status: 1, standard_state: 'READY', communication_status: 'ONLINE', operating_status: 'SHUTDOWN' }).selectable, true)
  assert.strictEqual(devices.normalizeDevice({ device_id: 'D1', communication_status: 'ONLINE', operating_status: 'READY', ready: true }).selectable, true)
  assert.strictEqual(devices.normalizeDevice({ device_id: 'D2', communication_status: 'OFFLINE' }).selectable, false)
  assert.strictEqual(devices.normalizeDevice({ device_id: 'D3', communication_status: 'ONLINE', operating_status: 'BUSY' }).standard_status, 'BUSY')
})
test('GPS 无 Fix 和相机异常会阻止启动，RTK 不阻止', () => {
  assert.strictEqual(devices.buildPreflight({ standard_state: 'READY', communication_status: 'ONLINE', operating_status: 'SHUTDOWN' }).ready, true)
  assert.strictEqual(devices.buildPreflight({ communication_status: 'ONLINE', operating_status: 'READY', ready: true, gps_fix: 'NO_FIX' }).ready, false)
  assert.strictEqual(devices.buildPreflight({ communication_status: 'ONLINE', operating_status: 'READY', ready: true, gps_fix: 'FIX', camera_status: 'ERROR' }).ready, false)
  assert.strictEqual(devices.buildPreflight({ communication_status: 'ONLINE', operating_status: 'READY', ready: true, gps_fix: 'FIX', camera_status: 'READY', rtk_status: 'FLOAT' }).ready, true)
})
test('A-01 标记为模拟演示烟田', () => {
  const field = fields.normalizeField({ field_id: 'FIELD_A01', name: '演示烟田 A-01', status: 'READY', data_source: 'DEMO_IMPORT', calibration_status: 'SIMULATED' })
  assert.strictEqual(field.ready, true)
  assert.strictEqual(field.is_simulated, true)
  assert.strictEqual(field.calibration_label, '模拟校准 · 演示数据')
})
test('STARTING 不会误报已开始，ACCEPTED/RUNNING 才视为接受', () => {
  assert.strictEqual(missions.normalizeMission({ status: 'STARTING', ack_status: 'PENDING' }).accepted, false)
  assert.strictEqual(missions.normalizeMission({ status: 'STARTING', ack_status: 'ACCEPTED' }).accepted, true)
  assert.strictEqual(missions.normalizeMission({ status: 'RUNNING' }).accepted, true)
  assert.strictEqual(missions.normalizeMission({ status: 'STARTING', commands: [{ status: 'ACCEPTED' }] }).accepted, true)
})
test('拒绝和超时为终态，SYNCING 未完成', () => {
  assert.strictEqual(missions.normalizeMission({ status: 'REJECTED' }).terminal, true)
  assert.strictEqual(missions.normalizeMission({ status: 'EXPIRED' }).terminal, true)
  assert.strictEqual(missions.normalizeMission({ status: 'SYNCING' }).terminal, false)
  assert.strictEqual(missions.normalizeMission({ status: 'COMPLETED' }).terminal, true)
})
test('实时数据 3 秒延迟提示、10 秒链路中断', () => {
  const base = Date.parse('2026-09-30T08:00:00Z')
  assert.strictEqual(missions.freshness('2026-09-30T07:59:58Z', base).state, 'live')
  assert.strictEqual(missions.freshness('2026-09-30T07:59:55Z', base).state, 'delayed')
  assert.strictEqual(missions.freshness('2026-09-30T07:59:40Z', base).state, 'interrupted')
})
test('只有运行中或离线运行任务可请求结束', () => {
  assert.strictEqual(missions.canRequestEnd('RUNNING'), true)
  assert.strictEqual(missions.canRequestEnd('RUNNING_OFFLINE'), true)
  assert.strictEqual(missions.canRequestEnd('SYNCING'), false)
})
test('开始/结束重试复用请求 ID，小程序重启恢复活动任务', () => {
  const storage = {}
  global.wx = { getStorageSync: (key) => storage[key], setStorageSync: (key, value) => { storage[key] = value }, removeStorageSync: (key) => { delete storage[key] } }
  const first = missionStore.getOrCreateRequestId('start:F:D', 'START')
  const retry = missionStore.getOrCreateRequestId('start:F:D', 'START')
  assert.strictEqual(first, retry)
  missionStore.saveActive({ inspection_id: 'INS_001', status: 'RUNNING' })
  assert.strictEqual(missionStore.getActive().inspection_id, 'INS_001')
  missionStore.clearActive()
  assert.strictEqual(missionStore.getActive(), null)
  delete global.wx
})

console.log('[8] 巡检记录与空间结果')
test('进行中状态进入当前列表', () => {
  const groups = inspections.splitEvents([{ status: 'RUNNING' }, { status: 'SYNCING' }, { status: 'COMPLETED' }])
  assert.strictEqual(groups.current.length, 2)
  assert.strictEqual(groups.history.length, 1)
})
test('状态中文映射', () => assert.strictEqual(inspections.statusLabel('RUNNING_OFFLINE'), '设备离线运行'))
test('轨迹点坐标限制在底图范围内', () => {
  assert.deepStrictEqual(spatial.normalizePoint({ x: -2, y: 120 }).x_pct, 0)
  assert.strictEqual(spatial.normalizePoint({ x: -2, y: 120 }).y_pct, 100)
})
test('风险网格映射固定色与统计字段', () => {
  const cell = spatial.normalizeGrid({ x_pct: 10, y_pct: 20, width_pct: 15, height_pct: 12, risk_level: 'REVIEW', sample_count: 9, suspicious_count: 2 })
  assert.strictEqual(cell.risk_label, '重点复核')
  assert.strictEqual(cell.risk_color, '#E9823D')
  assert.strictEqual(cell.sample_count, 9)
  assert.strictEqual(cell.suspected_count, 2)
})
test('相对图片 URL 统一通过当前 Base URL', () => {
  global.wx = { getStorageSync: () => 'http://192.168.1.10:8000/api' }
  assert.strictEqual(requestUtils.absoluteUrl('/image/IMG_1/file'), 'http://192.168.1.10:8000/api/image/IMG_1/file')
  delete global.wx
})
test('401 业务凭证错误与登录会话失效区分', () => {
  assert.strictEqual(requestUtils.isCredentialFailure('扫码凭证已过期'), true)
  assert.strictEqual(requestUtils.isCredentialFailure('Token 已失效'), false)
})
test('空烟田/设备/记录响应安全映射为空数组', () => {
  assert.deepStrictEqual(fields.unwrapItems(null), [])
  assert.deepStrictEqual(fields.unwrapItems({ items: [] }), [])
  assert.deepStrictEqual(inspections.splitEvents(null), { current: [], history: [] })
})

async function asyncTest(name, fn) {
  try { await fn(); passed += 1; console.log('  ✓ ' + name) }
  catch (error) { failed += 1; console.log('  ✗ ' + name); console.log('      ' + error.message) }
}
require('./real-device-tests').run(test, asyncTest).then(() => {
  require('./tabbar-tests').run(test)
  console.log('')
  console.log('结果：通过 ' + passed + '，失败 ' + failed)
  if (failed > 0) process.exitCode = 1
}).catch((error) => { console.error(error); process.exitCode = 1 })
