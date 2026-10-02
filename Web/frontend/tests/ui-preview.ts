// Isolated UI fixture. Never imported by src/main.ts or a production route.
// All API calls are local fixtures, and mutations deliberately fail.
import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import ElementPlus from 'element-plus'
import * as icons from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import '../src/styles/global.css'
import http from '../src/api/http'
import { useAuthStore } from '../src/stores/auth'
import AdminLayout from '../src/layouts/AdminLayout.vue'
import Dashboard from '../src/views/Dashboard.vue'
import Inspections from '../src/views/Inspections.vue'
import InspectionDetail from '../src/views/InspectionDetail.vue'
import Devices from '../src/views/Devices.vue'
import Fields from '../src/views/Fields.vue'
import FieldDetail from '../src/views/FieldDetail.vue'
import Analysis from '../src/views/Analysis.vue'
import Profile from '../src/views/Profile.vue'
import HelpFeedback from '../src/views/HelpFeedback.vue'
import LiveData from '../src/views/LiveData.vue'
import fieldMap from '../src/assets/fields/tobacco-field-nadir-01.png'

if (location.port !== '5187') throw new Error('Run the isolated UI fixture on port 5187 only')
// This separate origin never contains a production login session.
localStorage.setItem('tld_access_token', 'isolated-ui-fixture-not-a-credential')
window.addEventListener('beforeunload', () => localStorage.removeItem('tld_access_token'))

const now = '2026-10-01T07:30:00Z'
const field = { field_id: 'FIELD_UI', name: '烟田 A-01', description: '仅用于界面回归验证的模拟烟田',
  version: 2, status: 'READY', data_source: 'DEMO_IMPORT', calibration_status: 'SIMULATED', coordinate_system: 'WGS84',
  inspection_count: 4, last_inspection_at: now, base_map_url: fieldMap,
  pixel_boundary: [[28,340],[370,55],[1000,130],[1330,460],[1320,880],[840,970],[440,750]],
  geo_boundary: { type: 'Polygon', coordinates: [] }, control_points: [], transform_params: { image_width: 1536, image_height: 1024 } }
const fields = Array.from({ length: 4 }, (_, i) => ({ ...field, field_id: `FIELD_UI_${i}`, name: `烟田 A-0${i + 1}` }))
const results = ['Frogeye', 'Wildfire', 'Budworm damage', 'Mosaic'].map((disease, i) => ({ class: disease, confidence: .984 - i * .035, bbox: [10, 20, 130, 150] }))
const images = Array.from({ length: 8 }, (_, i) => ['original', 'annotated'].map(type => ({ image_id: `IMAGE_${i}_${type}`, data_id: `DATA_UI_${i}`, captured_at: now, image_type: type, url: fieldMap, cloud_detection: { status: 'completed', results: results.slice(0, i % 4 + 1) } }))).flat()
const event = { inspection_id: 'INS_UI', field_id: fields[0].field_id, field_name: fields[0].name, device_id: 'DEVICE_UI_0', name: 'A-01 烟田巡检', status: 'COMPLETED', sync_status: 'SYNCED', pending_sync_count: 0, started_at: now, ended_at: now, created_at: now, sample_count: 90, image_count: 16, target_count: 20,
  risk: { level: 'HIGH', score: 95.3, target_count: 20, avg_confidence: .87, disclaimer: '平台风险分仅用于巡检辅助，不构成专业农业诊断。' },
  environment_summary: { temperature: 26.3, humidity: 56.4, co2: 443, light: 653, sampled_at: now, valid_count: 90 }, images, track: [], environment: [] }
const events = Array.from({ length: 6 }, (_, i) => ({ ...event, inspection_id: i ? `INS_UI_${i}` : 'INS_UI', name: i ? `第 ${i + 1} 次烟田巡检` : event.name }))
const devices = Array.from({ length: 3 }, (_, i) => ({ device_id: `DEVICE_UI_${i}`, device_name: ['Jetson 巡检设备', '田间采集设备', '虚拟巡检设备'][i], status: 1,
  operating_status: i ? 'SHUTDOWN' : 'RUNNING', communication_status: i ? 'OFFLINE' : 'ONLINE', standard_state: i ? 'OFFLINE' : 'BUSY',
  inspection_count: 4, last_seen_at: now, sync_status: 'IDLE', pending_sync_count: 0, gps_fix: 'GPS_FIX', inference_status: 'READY', camera_status: 'READY',
  current_inspection_status: i ? null : 'RUNNING', current_inspection_id: i ? null : 'INS_UI', current_inspection_name: i ? null : event.name }))
const spatial = { inspection_id: 'INS_UI', field: fields[0], track: [], risk_grids: [], disease_points: [], risk_formula: '风险计算依据有效采样与识别置信度', risk_thresholds: {} }
const context = { crop: '烟草', field_id: null, inspection_id: null, growth_stage: '', location: '' }
const conversation = { id: 'CON_UI', title: '最近巡检分析', context, active_run_id: null, updated_at: now }
const messages = Array.from({ length: 12 }, (_, i) => ({ id: `MSG_UI_${i}`, role: i % 2 ? 'assistant' : 'user', content: i % 2 ? '## 本次巡检分析\n\n需要结合现场图片复核识别结果，风险评分不替代专业判断。\n\n' + '温度与湿度来自最新有效采样，缺失读数应保持为空。\n\n'.repeat(5) : '请分析最近一次巡检', status: 'COMPLETED', attachment_ids: [], evidence: [], created_at: now }))
http.defaults.adapter = async config => {
  if (config.method && config.method !== 'get') throw new Error('UI fixture does not permit mutations')
  const path = config.url || ''
  let data: unknown
  if (path === '/device/list') data = devices
  else if (path === '/fields') data = fields
  else if (path.startsWith('/fields/')) data = fields.find(f => path.endsWith(f.field_id)) || field
  else if (path === '/platform/events') data = { total: events.length, items: events, page: 1, page_size: 50 }
  else if (path.startsWith('/platform/events/')) data = event
  else if (path.endsWith('/spatial')) data = spatial
  else if (path === '/platform/analysis/overview') data = { metrics: { events: 6, active_events: 1, samples: 540, week_samples: 180, targets: 20 }, environment_trends: [], recent_events: events }
  else if (path.endsWith('/live')) data = { device_id: devices[0].device_id, raw: {}, display: { environment: event.environment_summary, location: { latitude: null, longitude: null } }, link_state: 'LIVE', device_state: 'BUSY', received_at: now, age_ms: 100 }
  else if (path === '/user/email') data = { has_email: false, verified: false, email: null }
  else if (path.endsWith('/capabilities')) data = { model_configured: true, weather_configured: false, search_configured: false, limits: {} }
  else if (path.endsWith('/attachments')) data = []
  else if (path.endsWith('/conversations')) data = [conversation]
  else if (path.endsWith('/conversations/CON_UI')) data = { ...conversation, messages }
  else throw new Error(`Unknown UI fixture: ${path}`)
  return { config, status: 200, statusText: 'OK', headers: {}, data: { code: 0, message: 'UI fixture', data } }
}
const children = [
  { path: 'overview', component: Dashboard, meta: { title: '巡检总览' } },
  { path: 'inspections', component: Inspections, meta: { title: '巡检记录' } },
  { path: 'inspections/:inspectionId', component: InspectionDetail, meta: { title: '巡检详情' } },
  { path: 'fields', component: Fields, meta: { title: '烟田管理' } },
  { path: 'fields/:fieldId', component: FieldDetail, meta: { title: '烟田详情' } },
  { path: 'devices', component: Devices, meta: { title: '设备管理' } },
  { path: 'analysis', component: Analysis, meta: { title: '智能分析' } },
  { path: 'profile', component: Profile, meta: { title: '个人中心' } },
  { path: 'help', component: HelpFeedback, meta: { title: '帮助与反馈' } },
  { path: 'live', component: LiveData, meta: { title: '实时数据' } },
]
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/platform', component: AdminLayout, children }] })
const pinia = createPinia()
useAuthStore(pinia).user = { user_id: 0, nickname: '界面测试用户', avatar: 'preset:leaf', status: 1, email_verified: false, has_phone_password: false, identities: [] }
await router.push(new URLSearchParams(location.search).get('route') || '/platform/inspections/INS_UI')
await router.isReady()
const app = createApp({ render: () => h(RouterView) })
app.use(pinia).use(router).use(ElementPlus)
for (const [name, icon] of Object.entries(icons)) app.component(name, icon)
app.mount('#app')
