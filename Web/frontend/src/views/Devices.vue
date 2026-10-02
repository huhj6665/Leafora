<template>
  <div class="page-shell devices-page" v-loading="loading">
    <section class="fleet-summary">
      <div><span>设备总数</span><b>{{ devices.length }}</b></div>
      <div><span>通信在线</span><b>{{ onlineCount }}</b></div>
      <div><span>正在运行</span><b>{{ runningCount }}</b></div>
      <div><span>设备累计巡检</span><b>{{ totalInspections }}</b></div>
    </section>

    <section v-if="devices.length" class="device-grid">
      <article v-for="device in devices" :key="device.device_id" class="surface device-card">
        <div class="device-head">
          <div class="device-icon"><span></span></div>
          <div><b>{{ device.device_name || '未命名边缘设备' }}</b><small>{{ device.device_id }}</small></div>
          <el-dropdown trigger="click" class="device-menu"><button class="more-button" type="button" :aria-label="`${device.device_name || device.device_id}的更多操作`">•••</button><template #dropdown><el-dropdown-menu><el-dropdown-item :disabled="!canUnbind(device)" @click="unbind(device)"><span :title="unbindReason(device)">解除绑定</span></el-dropdown-item></el-dropdown-menu></template></el-dropdown>
        </div>

        <div class="primary-states">
          <div :class="['state-block', device.communication_status.toLowerCase()]">
            <span>设备状态</span><b><i></i>{{ stateName(device.standard_state) }}</b>
            <small>{{ relativeTime(device.last_seen_at) }}</small>
          </div>
          <div :class="['state-block', device.operating_status.toLowerCase()]">
            <span>运行状态</span><b><i></i>{{ operationName(device.operating_status) }}</b>
            <small>{{ device.current_inspection_status ? taskStatusName(device.current_inspection_status) : '当前无任务' }}</small>
          </div>
        </div>

        <dl class="device-facts">
          <div><dt>当前任务</dt><dd>{{ device.current_inspection_name || '—' }}</dd></div>
          <div><dt>任务编号</dt><dd class="mono">{{ shortId(device.current_inspection_id) }}</dd></div>
          <div><dt>定位 / 推理</dt><dd>{{ moduleName(device.gps_fix) }} · {{ moduleName(device.inference_status) }}</dd></div>
          <div><dt>待同步</dt><dd>{{ device.pending_sync_count }}</dd></div>
        </dl>

        <div class="device-actions">
          <el-tooltip :content="viewReason(device)" :disabled="canView(device)">
            <span><el-button type="primary" plain :disabled="!canView(device)" @click="openDevice(device)">查看设备</el-button></span>
          </el-tooltip>
          <span class="communication-caption"><i :class="{online:device.communication_status === 'ONLINE'}"></i>{{ communicationName(device.communication_status) }}</span>
        </div>
      </article>
    </section>

    <div v-else class="empty surface">
      <div class="device-outline"><el-icon><Monitor /></el-icon></div><h3>还没有绑定设备</h3>
      <p>请在 Jetson 本机申请短时配对码，并使用已登录的微信小程序扫描设备二维码。</p>
    </div>

    <el-drawer v-model="drawerVisible" :title="selected?.device_name || '设备详情'" size="min(520px, 92vw)" @closed="closeDevice">
      <template v-if="selected && detailLive?.display">
        <div class="drawer-status">
          <span><i></i>正在执行任务</span><b>{{ selected.current_inspection_name }}</b><small>{{ selected.current_inspection_id }}</small>
        </div>
        <div class="telemetry-detail">
          <article v-for="item in detailMetrics" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value }}</b></article>
        </div>
        <dl class="live-facts">
          <div><dt>链路状态</dt><dd>{{ linkName(detailLive.link_state) }}</dd></div>
          <div><dt>GPS / RTK</dt><dd>{{ moduleName(selected.gps_fix) }} · {{ moduleName(selected.rtk_status) }}</dd></div>
          <div><dt>相机 / 推理</dt><dd>{{ moduleName(selected.camera_status) }} · {{ moduleName(selected.inference_status) }}</dd></div>
          <div><dt>最近更新</dt><dd>{{ detailLive.received_at ? new Date(detailLive.received_at).toLocaleString('zh-CN') : '—' }}</dd></div>
        </dl>
      </template>
      <div v-else class="drawer-empty">正在读取设备实时状态…</div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deviceApi } from '@/api/device'
import { fieldApi } from '@/api/field'
import type { DeviceItem, LiveData } from '@/types'

const loading = ref(true)
const devices = ref<DeviceItem[]>([])
const selected = ref<DeviceItem | null>(null)
const detailLive = ref<LiveData | null>(null)
const drawerVisible = ref(false)
let detailTimer: number | undefined

const onlineCount = computed(() => devices.value.filter(item => item.communication_status === 'ONLINE').length)
const runningCount = computed(() => devices.value.filter(item => item.current_inspection_status === 'RUNNING' || item.current_inspection_status === 'RUNNING_OFFLINE').length)
const totalInspections = computed(() => devices.value.reduce((sum, item) => sum + item.inspection_count, 0))
const detailMetrics = computed(() => {
  const status = detailLive.value?.display?.device_status || {}
  const value = (input: unknown, unit = '') => typeof input === 'number' ? `${input.toFixed(1)}${unit}` : '—'
  return [
    { label: 'CPU 温度', value: value(status.temperature, '°C') },
    { label: 'CPU 占用率', value: value(status.cpu_usage, '%') },
    { label: '内存占用率', value: value(status.memory_usage, '%') },
    { label: '存储占用率', value: value(status.storage_usage, '%') },
  ]
})

async function load() {
  loading.value = true
  try { devices.value = await deviceApi.list() } finally { loading.value = false }
}
function canView(device: DeviceItem) {
  return device.communication_status === 'ONLINE' && device.operating_status === 'RUNNING'
    && ['RUNNING', 'RUNNING_OFFLINE'].includes(device.current_inspection_status || '')
}
function viewReason(device: DeviceItem) {
  if (device.communication_status !== 'ONLINE') return '设备当前不在线'
  if (device.operating_status !== 'RUNNING') return '设备当前未运行'
  return '仅正在执行巡检任务的设备可以查看实时详情'
}
function canUnbind(device: DeviceItem) { return !device.current_inspection_status && device.pending_sync_count === 0 }
function unbindReason(device: DeviceItem) { return device.current_inspection_status ? '设备仍有关联中的巡检任务' : '设备仍有待同步数据' }
async function openDevice(device: DeviceItem) {
  if (!canView(device)) return
  selected.value = device
  drawerVisible.value = true
  await pollDetail()
  detailTimer = window.setInterval(pollDetail, 2000)
}
async function pollDetail() {
  if (!selected.value) return
  detailLive.value = await fieldApi.live(selected.value.device_id)
}
function closeDevice() {
  if (detailTimer) window.clearInterval(detailTimer)
  detailTimer = undefined
  selected.value = null
  detailLive.value = null
}
async function unbind(device: DeviceItem) {
  if (!canUnbind(device)) return
  await ElMessageBox.confirm(`确认解除“${device.device_name || device.device_id}”（${device.device_id}）的绑定？历史巡检数据不会删除。`, '解除设备绑定', { type: 'warning' })
  await deviceApi.unbind(device.device_id)
  ElMessage.success('已解除绑定')
  await load()
}
function operationName(value: string) { return ({ STARTUP: '启动检查中', RUNNING: '运行中', SHUTDOWN: '待命 / 停机', ERROR: '异常', DISABLED: '已禁用' } as Record<string, string>)[value] || value }
function moduleName(value?: string | null) { return ({ NO_FIX: '无定位', GPS_FIX: 'GPS 定位', DGPS: '差分定位', RTK_FLOAT: 'RTK 浮点', RTK_FIXED: 'RTK 固定', NOT_STARTED: '未启动', READY: '就绪', ERROR: '异常' } as Record<string, string>)[value || ''] || value || '—' }
function communicationName(value: string) { return value === 'ONLINE' ? '在线' : '离线' }
function stateName(value?: string) { return ({ READY: '设备就绪', BUSY: '任务占用', SYNCING: '正在同步', OFFLINE: '设备离线', ERROR: '设备异常', DISABLED: '已禁用', ONLINE_NOT_READY: '在线未就绪' } as Record<string, string>)[value || ''] || '状态未知' }
function taskStatusName(value: string) { return ({ START_REQUESTED: '等待下发', STARTING: '正在启动', RUNNING: '任务进行中', RUNNING_OFFLINE: '离线运行', ENDING: '正在结束', SYNCING: '正在同步' } as Record<string, string>)[value] || value }
function linkName(value: string) { return ({ LIVE: '实时', DELAYED: '数据延迟', DISCONNECTED: '链路中断', NO_DATA: '暂无数据' } as Record<string, string>)[value] || value }
function shortId(value?: string | null) { return value ? value.slice(0, 16) : '—' }
function relativeTime(value?: string | null) { if (!value) return '从未上报'; const minutes = Math.floor((Date.now() - new Date(value).getTime()) / 60000); return minutes < 1 ? '刚刚' : minutes < 60 ? `${minutes} 分钟前` : minutes < 1440 ? `${Math.floor(minutes / 60)} 小时前` : `${Math.floor(minutes / 1440)} 天前` }

onMounted(load)
onBeforeUnmount(closeDevice)
</script>

<style scoped>
.fleet-summary{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);background:#e9ede5;margin-bottom:14px}.fleet-summary>div{padding:16px 20px;border-right:1px solid #cdd4ca}.fleet-summary>div:last-child{border:0}.fleet-summary span{display:block;color:#76837b;font-size:9px}.fleet-summary b{display:block;margin-top:6px;font:600 23px var(--display)}
.device-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.device-card{padding:22px}.device-head{display:flex;align-items:center}.device-icon{width:44px;height:44px;background:#dce5d8;margin-right:12px;display:grid;place-items:center}.device-icon span{width:17px;height:24px;border:2px solid #315b45;position:relative}.device-icon span:after{content:'';position:absolute;left:4px;right:4px;bottom:3px;height:2px;background:#315b45}.device-head b,.device-head small{display:block}.device-head b{font-size:14px}.device-head small{font:9px var(--mono);color:#819087;margin-top:5px}.ready-badge{margin-left:auto;padding:6px 8px;background:#edf0e9;color:#68756d;font-size:9px}.ready-badge.ready{background:#e4eedf;color:#4b783f}.ready-badge.danger{background:#f3dfdb;color:#98483e}
.primary-states{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:20px 0 18px}.state-block{padding:17px;background:#f0f2ec;border-left:3px solid #a8b1aa}.state-block>span,.state-block>small{display:block;color:#7d8981;font-size:9px}.state-block b{display:flex;align-items:center;gap:8px;margin:8px 0 6px;font:600 21px var(--display)}.state-block b i{width:9px;height:9px;border-radius:50%;background:#9aa49e}.state-block.online,.state-block.running{border-left-color:#6da657}.state-block.online b i,.state-block.running b i{background:#6da657;box-shadow:0 0 0 4px #dcebd5}.state-block.error{border-left-color:#b75b4d}.state-block.error b i{background:#b75b4d}
.device-facts{display:grid;grid-template-columns:1fr 1fr;margin:0;background:var(--line);gap:1px}.device-facts>div{padding:11px;background:#f8f9f4}.device-facts dt{color:#839087;font-size:8px}.device-facts dd{margin:5px 0 0;color:#36473e;font-size:10px}.device-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px}.device-actions>span{display:inline-flex}
.drawer-status{padding:18px;background:#1e3529;color:white}.drawer-status span,.drawer-status small{display:block;color:#9daf9f;font-size:9px}.drawer-status span i{display:inline-block;width:7px;height:7px;margin-right:7px;border-radius:50%;background:#9dce63}.drawer-status b{display:block;margin:9px 0 5px;font-size:17px}.telemetry-detail{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px}.telemetry-detail article{padding:17px;background:#f0f2ec}.telemetry-detail span{display:block;color:#7d8981;font-size:9px}.telemetry-detail b{display:block;margin-top:8px;font:600 22px var(--display)}.live-facts{margin-top:16px}.live-facts>div{display:flex;justify-content:space-between;padding:13px 0;border-bottom:1px solid var(--line)}.live-facts dt{color:#7d8981;font-size:10px}.live-facts dd{margin:0;font:10px var(--mono)}.drawer-empty,.empty{text-align:center;padding:80px 20px;color:#7e8a82}.device-outline{width:55px;height:55px;margin:auto;display:grid;place-items:center;border:2px solid #88a08e;color:#4c6b56;font:600 23px var(--display)}.empty h3{font:600 19px var(--display);margin:20px 0 8px}.empty p{max-width:440px;margin:auto;font-size:11px;line-height:1.8}
@media(max-width:850px){.device-grid{grid-template-columns:1fr}}@media(max-width:600px){.fleet-summary{grid-template-columns:1fr 1fr}.fleet-summary>div:nth-child(2){border-right:0}.fleet-summary>div:nth-child(-n+2){border-bottom:1px solid #cdd4ca}.primary-states,.device-facts{grid-template-columns:1fr}.telemetry-detail{grid-template-columns:1fr 1fr}}
</style>

<style scoped>
.device-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.device-card{padding:20px;display:flex;flex-direction:column;min-width:0}.device-head{gap:10px;flex-wrap:wrap}.device-icon{width:36px;height:36px;flex:0 0 36px;margin-right:0;border-radius:8px}.device-head>div:nth-child(2){flex:1;min-width:0}.device-head b{font-size:15px;line-height:1.4}.device-head small{font-size:11px;overflow-wrap:anywhere}.ready-badge{font-size:11px;border-radius:4px;white-space:nowrap;padding:5px 7px}
.primary-states{gap:10px;margin:18px 0 14px}.state-block{padding:12px;border-radius:6px}.state-block>span,.state-block>small{font-size:11px;line-height:1.5}.state-block b{font-size:22px;gap:7px;margin:8px 0}.state-block b i{flex:0 0 7px;height:7px}.device-facts{background:transparent;gap:0}.device-facts>div{padding:10px 0;background:transparent;border-bottom:1px solid #e5e9df;min-width:0}.device-facts>div:nth-child(odd){padding-right:12px}.device-facts dt{font-size:11px;color:#718078}.device-facts dd{font-size:12px;line-height:1.6;overflow-wrap:anywhere}.device-actions{margin-top:auto;padding-top:18px;gap:10px}.device-actions>span{flex:1}.device-actions :deep(.el-button){width:100%;margin:0;font-size:13px;height:36px}.fleet-summary span{font-size:12px}.fleet-summary b{font-size:26px}
@media(max-width:1250px){.device-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.device-grid{grid-template-columns:1fr}.device-card{padding:18px}.primary-states,.device-facts{grid-template-columns:1fr 1fr}.fleet-summary>div{padding:14px}}
</style>
<style scoped>
.fleet-summary{border-radius:12px;background:var(--surface);margin-bottom:24px;overflow:hidden}.fleet-summary>div{padding:18px 22px;border-color:var(--line)}.fleet-summary span{font-size:13px;color:#617168}.fleet-summary b{font-size:30px;line-height:1.3;margin-top:6px;font-variant-numeric:tabular-nums}
.device-grid{gap:20px}.device-card{padding:22px;transition:border-color .2s,box-shadow .2s}.device-card:hover{border-color:#aebfb2;box-shadow:0 6px 24px #17251f08}.device-head{gap:12px;flex-wrap:nowrap}.device-head b{font-size:16px}.device-head small{font-size:11px}.device-icon{width:40px;height:40px;flex-basis:40px;background:#edf3ed}.device-menu{margin-left:auto}.more-button{border:0;background:transparent;color:#6c7e71;width:30px;height:32px;letter-spacing:2px;cursor:pointer;border-radius:6px}.more-button:hover{background:#edf3ed}
.primary-states{display:flex;flex-direction:column;gap:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:20px 0 8px;padding:10px 0}.state-block{display:grid;grid-template-columns:84px 1fr;align-items:center;padding:8px 0;border:0;border-radius:0;background:none;gap:3px 10px}.state-block>span{font-size:12px;color:#617168}.state-block b{font:500 14px/1.5 var(--display);margin:0;gap:8px}.state-block>small{grid-column:2;font-size:11px;color:#66776c}.state-block b i{height:6px;flex-basis:6px}.device-facts{grid-template-columns:1fr;gap:0}.device-facts>div,.device-facts>div:nth-child(odd){display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:9px 0;border:0}.device-facts dt{font-size:12px;flex-shrink:0}.device-facts dd{font-size:13px;line-height:1.6;margin:0;text-align:right}.device-actions{padding-top:16px;border-top:1px solid var(--line);margin-top:16px;align-items:center;justify-content:space-between}.device-actions>span{flex:0 1 auto}.device-actions :deep(.el-button){width:auto;min-width:110px;height:36px}.communication-caption{display:flex;align-items:center;gap:6px;font-size:12px;color:#65756c}.communication-caption i{width:6px;height:6px;background:#9ca8a0;border-radius:50%}.communication-caption i.online{background:#4d815d}
.telemetry-detail span,.live-facts dt,.live-facts dd{font-size:13px}.drawer-status span,.drawer-status small{font-size:12px}.empty p{font-size:14px}.device-outline{border:0;background:#edf3ed;border-radius:14px}
@media(max-width:1250px){.device-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.device-grid{grid-template-columns:1fr}.fleet-summary>div{padding:16px}.primary-states{display:flex}.device-facts{grid-template-columns:1fr}.fleet-summary b{font-size:26px}}
</style>
