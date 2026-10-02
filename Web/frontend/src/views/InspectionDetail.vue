<template>
  <div class="page-shell detail">
    <div class="detail-top">
      <router-link to="/platform/inspections" class="back">← 返回巡检记录</router-link>
      <div v-if="event" class="actions">
        <router-link :to="{path:'/platform/analysis',query:{inspection_id:event.inspection_id,field_id:event.field_id||undefined}}" class="assistant-entry">农业助手分析 ↗</router-link>
        <span :class="['event-status', event.status.toLowerCase()]">{{ statusName(event.status) }}</span>
        <span v-if="event.pending_sync_count" class="sync-note">待同步 {{ event.pending_sync_count }}</span>
      </div>
    </div>

    <div v-if="eventLoading" class="surface section-loading">正在读取任务摘要…</div>
    <section v-else-if="event" class="summary-strip surface">
      <div class="summary-time"><span>开始时间</span><b>{{ formatDate(event.started_at) }}</b></div><div class="summary-time"><span>结束时间</span><b>{{ formatDate(event.ended_at) }}</b></div><div><span>采样点</span><b>{{ event.sample_count }}</b></div><div><span>现场图片</span><b>{{ event.image_count }}</b></div><div><span>识别目标</span><b>{{ event.risk.target_count }}</b></div>
    </section>

    <div v-if="spatialLoading" class="surface section-loading map-loading">正在生成烟田空间分区…</div>
    <section v-else-if="spatial" class="surface field-spatial">
      <div class="card-head"><div><h3>{{ spatial.field.name }}</h3><p class="section-description">烟田风险分布</p></div><div class="map-tools"><label>病害显示<select v-model="selectedDisease" aria-label="地图病害筛选"><option value="">总病害</option><option v-for="disease in diseaseClasses" :key="disease" :value="disease">{{ diseaseName(disease) }}</option></select></label><span>V{{ spatial.field.version }} · {{ spatial.field.calibration_status === 'SIMULATED' ? '模拟校准' : spatial.field.calibration_status }}</span></div></div>
      <div class="spatial-layout"><div class="spatial-map">
      <div class="spatial-stage" :class="{ 'map-unavailable': mapStatus === 'error' }" :style="{ aspectRatio: `${spatialWidth}/${spatialHeight}` }">
        <img v-if="fieldImage" :src="fieldImage" alt="任务烟田底图">
        <svg :viewBox="`0 0 ${spatialWidth} ${spatialHeight}`" aria-label="烟田风险分区图">
          <path
            v-for="grid in displayedGrids" :key="grid.cell_id"
            :d="organicPath(grid.polygon)"
            :class="['grid', grid.risk_level.toLowerCase(), { selected: selectedGrid === grid.cell_id }]"
            @click="selectedGrid = grid.cell_id"
          ><title>{{ grid.cell_id }} · 有效样本 {{ grid.valid_sample_count }} · 疑似 {{ grid.suspicious_count }} · 风险 {{ grid.risk_score }}</title></path>
          <polygon :points="spatialBoundary" fill="none" stroke="#f5ffac" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" pointer-events="none"/>
          <circle v-for="(point, index) in displayedDiseasePoints" :key="index" :cx="point.x" :cy="point.y" :r="spatialWidth / 180" fill="#d74e3e" stroke="#fff" stroke-width="1.5" vector-effect="non-scaling-stroke"><title>{{ selectedDisease ? diseaseName(selectedDisease) : '病害识别点' }} · 最高置信度 {{ (point.confidence * 100).toFixed(1) }}%</title></circle>
        </svg>
        <div v-if="mapStatus === 'error'" class="map-state" role="status">烟田底图加载失败，已保留空间轮廓与风险分区。</div>
      </div>
      <div class="legend"><span><i class="low"></i>较低</span><span><i class="attention"></i>需关注</span><span><i class="review"></i>重点复核</span><span><i class="high"></i>高风险</span><span><i class="insufficient"></i>数据不足</span><span>● 识别点 {{ displayedDiseasePoints.length }}</span><p>{{ selectedGridInfo || mapFormula }}</p><p v-if="selectedDisease">当前：{{ diseaseName(selectedDisease) }}。仅统计已完成云端识别的采样点；无图片、识别失败或未完成不视为健康。右侧为本次巡检整体风险。</p></div>
      </div>
      <aside v-if="event" class="detail-sidebar">
      <section class="risk-card risk-sidebar" aria-label="风险分析">
        <div class="risk-heading"><span>整体风险</span><h3 :style="{color:riskColor}">{{ levelName(event.risk.level) }}</h3></div>
        <div class="risk-values"><span>风险分 <b :style="{color:riskColor}">{{ event.risk.score }}<small> / 100</small></b></span><span>目标数量 <b>{{ event.risk.target_count }}</b></span><span>平均置信度 <b>{{ Math.round(event.risk.avg_confidence * 100) }}%</b></span></div>
        <p>{{ event.risk.disclaimer }}</p>
      </section>
      <section class="env-sidebar" aria-label="环境数据">
        <div class="environment-heading"><h3>环境</h3><span>{{ event.environment_summary.valid_count }} 个有效采样</span></div>
        <div class="env-grid"><article v-for="item in environmentCards" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value }}</b><small>{{ item.unit }}</small></article></div>
        <p class="env-meta">更新于 {{ formatDate(event.environment_summary.sampled_at) }}</p>
      </section>
      </aside>
      </div>
    </section>

    <article v-if="event && !spatial && !spatialLoading" class="surface risk-card">
      <div><h3>{{ levelName(event.risk.level) }}</h3><p>{{ event.risk.disclaimer }}</p></div>
      <div class="risk-values"><span>风险分 <b :style="{ color: riskColor }">{{ event.risk.score }}</b></span><span>目标数量 <b>{{ event.risk.target_count }}</b></span><span>平均置信度 <b>{{ Math.round(event.risk.avg_confidence * 100) }}%</b></span></div>
    </article>

    <section v-if="event && !spatial && !spatialLoading" class="surface env-card">
      <div class="card-head"><div><h3>最新有效环境数据</h3></div><span>{{ formatDate(event.environment_summary.sampled_at) }} · {{ event.environment_summary.valid_count }} 个有效采样</span></div>
      <div class="env-grid"><article v-for="item in environmentCards" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value }}</b><small>{{ item.unit }}</small></article></div>
    </section>

    <section v-if="event" class="surface image-section">
      <div class="card-head"><div><h3>图片与识别结果</h3></div><div class="image-tools"><div class="image-tabs" aria-label="图片类型"><button v-for="tab in imageTabs" :key="tab.value" type="button" :aria-pressed="imageMode === tab.value" :class="{ active: imageMode === tab.value }" @click="imageMode = tab.value">{{ tab.label }} {{ imageCount(tab.value) }}</button></div><span>{{ imagesLoading ? `已载入 ${loadedVisibleCount}/${visibleImages.length}` : `${visibleImages.length} 张` }}</span></div></div>
      <div v-if="visibleImages.length" class="image-grid">
        <el-popover v-for="image in visibleImages" :key="image.image_id" :visible="resultOpen === image.image_id" :width="340" placement="top" strategy="fixed" :fallback-placements="['bottom', 'left', 'right']" :popper-options="{ modifiers: [{ name: 'preventOverflow', options: { rootBoundary: 'viewport', padding: 16, altAxis: true, tether: false } }] }" :show-arrow="false" teleported popper-class="evidence-popover" :persistent="false">
          <template #reference>
        <article class="evidence-card" @mouseenter="queueResult(image)" @mouseleave="scheduleResultClose" @focusout="scheduleResultClose" @keydown.esc="closeResult">
          <button type="button" class="photo" :disabled="!imageUrls[image.image_id]" :aria-label="`放大查看${imageMode === 'original' ? '原始图' : '识别图'} ${formatDate(image.captured_at)}`" @click="openPreview(image.image_id)">
            <img v-if="imageUrls[image.image_id]" :src="imageUrls[image.image_id]" :alt="imageMode === 'original' ? '巡检原始图' : '巡检识别标注图'" loading="lazy"><div v-else class="image-placeholder">{{ imagePlaceholder(image.image_id) }}</div><span>{{ imageMode === 'original' ? '原始图' : '识别图' }}</span><span v-if="imageUrls[image.image_id]" class="zoom-hint">点击放大 ↗</span>
          </button>
          <div class="image-meta"><b>{{ formatDate(image.captured_at) }}</b><small>{{ image.data_id.slice(0, 12) }}</small><div><span :class="image.cloud_detection?.status">{{ detectionName(image.cloud_detection?.status) }}</span><i>{{ image.cloud_detection?.results.length || 0 }} 个目标</i></div>
            <button v-if="imageMode === 'annotated' && image.cloud_detection?.status === 'completed'" class="result-button" type="button" :aria-expanded="resultOpen === image.image_id" @click="showResult(image.image_id)">查看结果 <span aria-hidden="true">↗</span></button>
          </div>
        </article>
          </template>
          <div class="result-panel" tabindex="0" @mouseenter="cancelResultTimer" @mouseleave="scheduleResultClose" @focusin="cancelResultTimer" @focusout="scheduleResultClose" @keydown.esc="closeResult">
            <div class="result-panel-head"><b>识别结果</b><button type="button" aria-label="关闭识别结果" @click="closeResult">×</button></div>
            <template v-if="image.cloud_detection?.status === 'completed'">
              <ul v-if="image.cloud_detection.results.length" class="detection-summary"><li v-for="group in summarizeDetections(image.cloud_detection.results)" :key="group.class"><b>{{ diseaseName(group.class) }} <small>{{ group.count }} 个</small></b><span>置信度 {{ confidenceRange(group.min, group.max) }}</span></li></ul>
              <p v-else class="detection-note">识别完成，未检出模型支持的病害目标（不等同于健康诊断）。</p>
              <details v-if="image.cloud_detection.results.length" class="detection-details"><summary>查看逐目标结果与框坐标</summary><ol><li v-for="(result, index) in image.cloud_detection.results" :key="index"><b>{{ diseaseName(result.class) }}</b> · {{ (result.confidence * 100).toFixed(1) }}%<small>{{ result.class }} · [{{ result.bbox.join(', ') }}]</small></li></ol></details>
            </template>
          </div>
        </el-popover>
      </div>
      <div v-else class="no-images">{{ imageMode === 'annotated' ? '暂无识别标注图，可切换原始图查看图片与识别状态。' : '本次巡检尚未关联原始图片。' }}</div>
    </section>
    <el-image-viewer v-if="previewIndex >= 0" :url-list="previewUrls" :initial-index="previewIndex" teleported show-progress hide-on-click-modal @close="previewIndex = -1" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { platformApi } from '@/api/platform'
import { fieldApi } from '@/api/field'
import { getToken } from '@/utils/token'
import { diseaseClasses, diseaseName, filterDiseaseGrids, filterDiseasePoints, summarizeDetections } from '@/utils/inspection-evidence'
import {
  acquireInspectionDetailCache,
  cacheInspectionEvent,
  cacheInspectionFieldImage,
  cacheInspectionImage,
  cacheInspectionSpatial,
  clearInspectionDetailCacheIfSignedOut,
  releaseInspectionDetailCache,
  spatialSnapshotIdentity,
} from '@/utils/inspection-detail-cache'
import type { EventDetail, SpatialResult } from '@/types'

const route = useRoute()
const event = shallowRef<EventDetail | null>(null)
const spatial = shallowRef<SpatialResult | null>(null)
const fieldImage = shallowRef('')
const imageUrls = shallowRef<Record<string, string>>({})
const imageStates = shallowRef<Record<string, 'idle' | 'loading' | 'success' | 'error'>>({})
const eventLoading = shallowRef(true)
const spatialLoading = shallowRef(true)
const mapStatus = shallowRef<'idle' | 'loading' | 'ready' | 'error'>('idle')
const selectedGrid = shallowRef('')
const selectedDisease = shallowRef('')
const imageMode = shallowRef('annotated')
const imageTabs = [{ value: 'original', label: '原始图' }, { value: 'annotated', label: '识别图' }]
const previewIndex = shallowRef(-1)
const resultOpen = shallowRef('')
let resultTimer: ReturnType<typeof setTimeout> | undefined
function cancelResultTimer() { if (resultTimer) clearTimeout(resultTimer); resultTimer = undefined }
function showResult(id: string) { cancelResultTimer(); resultOpen.value = id }
function closeResult() { cancelResultTimer(); resultOpen.value = '' }
function queueResult(image: EventDetail['images'][number]) {
  cancelResultTimer()
  if (imageMode.value === 'annotated' && image.cloud_detection?.status === 'completed') {
    resultTimer = setTimeout(() => { resultOpen.value = image.image_id }, 180)
  } else resultOpen.value = ''
}
function scheduleResultClose() { cancelResultTimer(); resultTimer = setTimeout(closeResult, 200) }
const visibleImages = computed(() => (event.value?.images || []).filter(image => image.image_type === imageMode.value))
const previewImages = computed(() => visibleImages.value.filter(image => imageUrls.value[image.image_id]))
const previewUrls = computed(() => previewImages.value.map(image => imageUrls.value[image.image_id]))
const loadedVisibleCount = computed(() => visibleImages.value.filter(image => imageStates.value[image.image_id] === 'success').length)
const imagesLoading = computed(() => visibleImages.value.some(image => ['idle', 'loading'].includes(imageStates.value[image.image_id] || 'idle')))
const displayedGrids = computed(() => filterDiseaseGrids(spatial.value?.risk_grids || [], event.value?.images || [], selectedDisease.value))
const displayedDiseasePoints = computed(() => filterDiseasePoints(spatial.value?.disease_points || [], event.value?.images || [], selectedDisease.value))
const mapFormula = computed(() => selectedDisease.value
  ? '100 × Σ(每个已识别采样点的该类最高置信度) ÷ 已识别采样点数；少于3个有效样本为数据不足'
  : spatial.value?.risk_formula)
type DetailImage = EventDetail['images'][number]
interface LoadSession {
  inspectionId: string
  controller: AbortController
  queue: DetailImage[]
  queued: Set<string>
  active: number
}
let currentSession: LoadSession | null = null
let leasedInspectionId = ''

const riskColor = computed(() => event.value?.risk.level === 'HIGH' ? '#ba5a4c' : event.value?.risk.level === 'MEDIUM' ? '#d8a84e' : '#759a63')
const spatialWidth = computed(() => Number(spatial.value?.field.transform_params.image_width || 1600))
const spatialHeight = computed(() => Number(spatial.value?.field.transform_params.image_height || 1105))
const spatialBoundary = computed(() => polygonPoints(spatial.value?.field.pixel_boundary || []))
const sharedEdges = computed(() => {
  const counts = new Map<string, number>()
  for (const grid of spatial.value?.risk_grids || []) {
    grid.polygon.forEach((point, index) => {
      const key = edgeKey(point, grid.polygon[(index + 1) % grid.polygon.length])
      counts.set(key, (counts.get(key) || 0) + 1)
    })
  }
  return counts
})
const selectedGridInfo = computed(() => {
  const grid = displayedGrids.value.find(item => item.cell_id === selectedGrid.value)
  return grid ? `${grid.cell_id} · 有效样本 ${grid.valid_sample_count} · 疑似 ${grid.suspicious_count} · 风险 ${grid.risk_score}` : ''
})
const environmentCards = computed(() => {
  const summary = event.value?.environment_summary
  const value = (number: number | null | undefined, digits = 1) => number == null ? '--' : number.toFixed(digits)
  return [
    { label: '温度', value: value(summary?.temperature), unit: '°C' },
    { label: '湿度', value: value(summary?.humidity), unit: '%' },
    { label: 'CO₂', value: value(summary?.co2, 0), unit: 'ppm' },
    { label: '光照', value: value(summary?.light, 0), unit: 'lux' },
  ]
})

async function fetchProtectedBlob(url: string, signal: AbortSignal) {
  const response = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` }, signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const blob = await response.blob()
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
  return URL.createObjectURL(blob)
}

function setImageState(imageId: string, state: 'idle' | 'loading' | 'success' | 'error') {
  imageStates.value = { ...imageStates.value, [imageId]: state }
}

function pumpImageQueue(session: LoadSession) {
  while (currentSession === session && !session.controller.signal.aborted && session.active < 3 && session.queue.length) {
    const image = session.queue.shift()!
    session.active += 1
    setImageState(image.image_id, 'loading')
    void fetchProtectedBlob(image.url, session.controller.signal).then(url => {
      if (currentSession !== session || session.controller.signal.aborted) {
        URL.revokeObjectURL(url)
        return
      }
      cacheInspectionImage(session.inspectionId, image.image_id, url)
      imageUrls.value = { ...imageUrls.value, [image.image_id]: url }
      setImageState(image.image_id, 'success')
    }).catch(error => {
      if (currentSession === session) {
        setImageState(image.image_id, error?.name === 'AbortError' ? 'idle' : 'error')
      }
    }).finally(() => {
      session.active -= 1
      pumpImageQueue(session)
    })
  }
}

function queueVisibleImages(session: LoadSession) {
  const images = (event.value?.images || []).filter(image => image.image_type === imageMode.value)
  for (const image of images) {
    if (imageUrls.value[image.image_id]) {
      setImageState(image.image_id, 'success')
    } else if (!session.queued.has(image.image_id)) {
      session.queued.add(image.image_id)
      session.queue.push(image)
      setImageState(image.image_id, 'idle')
    }
  }
  pumpImageQueue(session)
}

async function load() {
  closeResult()
  currentSession?.controller.abort()
  if (leasedInspectionId) releaseInspectionDetailCache(leasedInspectionId)
  const inspectionId = String(route.params.inspectionId)
  const cached = acquireInspectionDetailCache(inspectionId)
  leasedInspectionId = inspectionId
  const session: LoadSession = {
    inspectionId, controller: new AbortController(), queue: [], queued: new Set(), active: 0,
  }
  currentSession = session
  const { signal } = session.controller
  event.value = cached?.event || null
  spatial.value = cached?.spatial || null
  fieldImage.value = cached?.fieldImage || ''
  imageUrls.value = cached?.imageUrls || {}
  imageStates.value = Object.fromEntries(Object.keys(imageUrls.value).map(imageId => [imageId, 'success']))
  previewIndex.value = -1
  selectedGrid.value = ''
  selectedDisease.value = ''
  imageMode.value = 'annotated'
  eventLoading.value = !event.value
  mapStatus.value = spatial.value?.field.base_map_url
    ? (fieldImage.value ? 'ready' : 'loading') : (spatial.value ? 'ready' : 'idle')
  spatialLoading.value = !spatial.value || (!!spatial.value.field.base_map_url && !fieldImage.value)
  if (event.value) queueVisibleImages(session)
  const eventRequest = platformApi.event(inspectionId, false, signal).then(result => {
    if (currentSession !== session || signal.aborted) return
    event.value = result
    cacheInspectionEvent(inspectionId, result)
    eventLoading.value = false
    window.requestAnimationFrame(() => {
      if (currentSession === session && !signal.aborted) queueVisibleImages(session)
    })
  }).catch(() => { if (currentSession === session && !signal.aborted) eventLoading.value = false })
  const spatialRequest = fieldApi.spatial(inspectionId, signal).then(async result => {
    if (currentSession !== session || signal.aborted) return
    spatial.value = result
    cacheInspectionSpatial(inspectionId, result)
    if (result.field.base_map_url) {
      const identity = spatialSnapshotIdentity(result)
      if (fieldImage.value && cached?.spatial && spatialSnapshotIdentity(cached.spatial) === identity) {
        mapStatus.value = 'ready'
        spatialLoading.value = false
        return
      }
      mapStatus.value = 'loading'
      spatialLoading.value = true
      try {
        const url = await fetchProtectedBlob(result.field.base_map_url, signal)
        if (currentSession !== session || signal.aborted) URL.revokeObjectURL(url)
        else {
          cacheInspectionFieldImage(inspectionId, identity, url)
          fieldImage.value = url
          mapStatus.value = 'ready'
          spatialLoading.value = false
        }
      } catch {
        if (currentSession === session && !signal.aborted) {
          mapStatus.value = 'error'
          spatialLoading.value = false
        }
      }
    } else {
      fieldImage.value = ''
      mapStatus.value = 'ready'
      spatialLoading.value = false
    }
  }).catch(() => {
    if (currentSession === session && !signal.aborted) {
      mapStatus.value = 'error'
      spatialLoading.value = false
    }
  })
  await Promise.allSettled([eventRequest, spatialRequest])
}

function polygonPoints(points: number[][]) { return points.map(point => point.join(',')).join(' ') }
function pointKey(point: number[]) { return `${point[0].toFixed(2)},${point[1].toFixed(2)}` }
function edgeKey(first: number[], second: number[]) {
  const a = pointKey(first), b = pointKey(second)
  return a < b ? `${a}|${b}` : `${b}|${a}`
}
function organicPath(points: number[][]) {
  if (points.length < 3) return ''
  const commands = [`M ${points[0][0]} ${points[0][1]}`]
  points.forEach((first, index) => {
    const second = points[(index + 1) % points.length]
    const key = edgeKey(first, second)
    if ((sharedEdges.value.get(key) || 0) < 2) {
      commands.push(`L ${second[0]} ${second[1]}`)
      return
    }
    const canonical = pointKey(first) < pointKey(second) ? [first, second] : [second, first]
    const dx = canonical[1][0] - canonical[0][0], dy = canonical[1][1] - canonical[0][1]
    const length = Math.hypot(dx, dy) || 1
    let hash = 0
    for (const char of key) hash = ((hash * 31) + char.charCodeAt(0)) | 0
    const amplitude = Math.min(11, Math.max(1.5, length * .075)) * (Math.abs(hash) % 2 ? 1 : -1)
    const controlX = (first[0] + second[0]) / 2 - (dy / length) * amplitude
    const controlY = (first[1] + second[1]) / 2 + (dx / length) * amplitude
    commands.push(`Q ${controlX.toFixed(2)} ${controlY.toFixed(2)} ${second[0]} ${second[1]}`)
  })
  return `${commands.join(' ')} Z`
}
function formatDate(value?: string | null) { return value ? new Date(value).toLocaleString('zh-CN') : '—' }
function imageCount(mode: string) { return event.value?.images.filter(image => image.image_type === mode).length || 0 }
function imagePlaceholder(imageId: string) {
  return imageStates.value[imageId] === 'error' ? '图片加载失败' : '图片载入中…'
}
function openPreview(imageId: string) { closeResult(); previewIndex.value = previewImages.value.findIndex(image => image.image_id === imageId) }
function confidenceRange(min: number, max: number) { return min === max ? `${(max * 100).toFixed(1)}%` : `${(min * 100).toFixed(1)}%–${(max * 100).toFixed(1)}%` }
function statusName(value: string) { return ({ CREATED: '待开始', START_REQUESTED: '等待下发', STARTING: '等待设备确认', RUNNING: '进行中', RUNNING_OFFLINE: '离线运行', ENDING: '正在结束', SYNCING: '同步中', COMPLETED: '已完成', FAILED: '异常', CANCELLED: '已取消' } as Record<string, string>)[value] || value }
function levelName(value: string) { return ({ LOW: '低风险', MEDIUM: '中风险', HIGH: '高风险' } as Record<string, string>)[value] || value }
function detectionName(value?: string) { return ({ completed: '识别完成', pending: '等待识别', processing: '识别中', model_unavailable: '模型离线', failed: '识别失败' } as Record<string, string>)[value || ''] || '未识别' }

watch(() => route.params.inspectionId, load, { immediate: true })
watch(imageMode, () => {
  closeResult()
  previewIndex.value = -1
  if (currentSession) queueVisibleImages(currentSession)
})
onBeforeUnmount(() => {
  closeResult()
  currentSession?.controller.abort()
  if (leasedInspectionId) releaseInspectionDetailCache(leasedInspectionId)
  clearInspectionDetailCacheIfSignedOut()
})
</script>

<style scoped>
.assistant-entry{font-size:11px;color:var(--moss);border:1px solid var(--line);border-radius:6px;padding:7px 10px}
.detail-top{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:25px}.back{display:block;font-size:10px;color:#6f7e75;margin-bottom:18px}.detail-top h1{font:600 32px var(--display);letter-spacing:-.04em;margin:7px 0}.detail-top p{color:#7f8b83;font-size:11px;margin:0}.actions{display:flex;align-items:center;gap:10px}.event-status{padding:7px 10px;background:#e6e9e3;font:9px var(--mono)}.event-status.running{background:#e1edd9;color:#447438}.event-status.completed{background:#dfe9e4;color:#315b45}.section-loading{min-height:95px;display:grid;place-items:center;color:#7d8981;font-size:11px;margin-bottom:14px;background:linear-gradient(100deg,#f7f8f2 25%,#eef1e9 45%,#f7f8f2 65%);background-size:250% 100%;animation:skeleton 1.4s ease infinite}.map-loading{min-height:360px}@keyframes skeleton{to{background-position:-160% 0}}.summary-strip{display:grid;grid-template-columns:1.3fr 1.3fr .7fr .7fr .7fr 1.4fr;margin-bottom:14px;overflow:hidden}.summary-strip>div{padding:17px 20px;border-right:1px solid var(--line)}.summary-strip>div:last-child{border-right:0}.summary-strip span{display:block;color:#849088;font-size:9px;margin-bottom:7px}.summary-strip b{font:500 12px var(--mono)}.summary-strip .risk{display:flex;align-items:baseline;gap:6px;background:#18261f;color:white}.risk span{width:100%;margin:0}.risk strong{font:600 27px var(--display)}.risk strong.low{color:#9bc47f}.risk strong.medium{color:#e0b25e}.risk strong.high{color:#df7a6c}.risk i{font:normal 8px var(--mono);color:#8fa097;white-space:nowrap}.field-spatial,.risk-card,.env-card,.image-section{padding:22px}.field-spatial{margin-bottom:14px}.card-head{display:flex;justify-content:space-between;gap:16px}.card-head h3{font:600 18px var(--display);margin:6px 0}.card-head>span{font:9px var(--mono);color:#839087;text-align:right}.spatial-stage{position:relative;background:#1c3025;margin-top:16px;max-height:70vh}.spatial-stage img,.spatial-stage svg{position:absolute;inset:0;width:100%;height:100%}.spatial-stage img{object-fit:cover}.spatial-stage svg{z-index:2}.grid{stroke:rgba(255,255,255,.2);stroke-width:2;fill-opacity:.42;transition:fill-opacity .15s,stroke .15s;cursor:pointer}.grid:hover,.grid.selected{stroke:#fff;stroke-width:5;fill-opacity:.68}.grid.low{fill:#4da65a}.grid.attention{fill:#e8ce4d}.grid.review{fill:#e8903d}.grid.high{fill:#d74e3e}.grid.insufficient{fill:#8b9690;fill-opacity:.3;stroke-dasharray:10 7}.legend{display:flex;gap:15px;align-items:center;flex-wrap:wrap;margin-top:13px;font-size:9px;color:#65736b}.legend span{display:flex;gap:5px;align-items:center}.legend i{width:10px;height:10px}.legend .low{background:#4da65a}.legend .attention{background:#e8ce4d}.legend .review{background:#e8903d}.legend .high{background:#d74e3e}.legend .insufficient{background:#8b9690}.legend p{margin:0 0 0 auto;color:#879189;font-size:8px}.risk-card{display:flex;align-items:center;justify-content:space-between;gap:24px}.risk-card h3{font:600 22px var(--display);margin:7px 0}.risk-card p{margin:0;color:#89938c;font-size:9px}.risk-values{display:flex;gap:8px}.risk-values span{min-width:110px;padding:14px;background:#f1f3ed;color:#7d8981;font-size:9px}.risk-values b{display:block;margin-top:7px;color:#26362e;font:600 21px var(--display)}.env-card,.image-section{margin-top:14px}.env-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}.env-grid article{padding:18px;background:#f1f3ed;border:1px solid #e1e5dd}.env-grid span{display:block;color:#7f8b83;font-size:9px}.env-grid b{display:inline-block;margin-top:11px;font:600 28px var(--display)}.env-grid small{margin-left:5px;color:#879189;font:9px var(--mono)}.image-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:18px}.image-grid article{border:1px solid var(--line);background:#f5f6f0}.photo{height:160px;position:relative;background:#25372e;overflow:hidden}.photo img{width:100%;height:100%;object-fit:cover}.photo>span{position:absolute;left:8px;top:8px;background:#17251fcc;color:white;padding:4px 6px;font:8px var(--mono)}.image-placeholder{height:100%;display:grid;place-items:center;color:#788a7f;font:9px var(--mono)}.image-meta{padding:12px}.image-meta>b,.image-meta>small{display:block}.image-meta>b{font-size:10px}.image-meta>small{font:8px var(--mono);color:#89938c;margin-top:4px}.image-meta>div{display:flex;justify-content:space-between;margin-top:10px}.image-meta span{font-size:8px;color:#52734f}.image-meta span.failed{color:#a34c40}.image-meta i{font:normal 8px var(--mono);color:#89938c}.no-images{height:150px;display:grid;place-items:center;color:#849087;font-size:11px}
@media(max-width:1100px){.summary-strip{grid-template-columns:repeat(3,1fr)}.image-grid{grid-template-columns:repeat(2,1fr)}.risk-card{align-items:flex-start;flex-direction:column}.risk-values{width:100%}.risk-values span{flex:1}.env-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){.detail-top{align-items:flex-start;flex-direction:column;gap:18px}.summary-strip{grid-template-columns:repeat(2,1fr)}.summary-strip>div{padding:14px}.image-grid,.env-grid{grid-template-columns:1fr}.risk-values{flex-direction:column}.card-head{flex-direction:column}.card-head>span{text-align:left}.legend p{width:100%;margin-left:0}}
</style>

<style scoped>
.detail-top{align-items:center;margin-bottom:14px;gap:12px}.back{font-size:13px;margin:0}.event-status{font:12px 'Noto Sans SC',sans-serif;border-radius:4px}.sync-note{font-size:12px;color:#67766c}
.summary-strip{grid-template-columns:1.4fr 1.4fr .8fr .8fr .8fr}.summary-strip>div{padding:20px 24px;min-width:0}.summary-strip span{font-size:12px;color:#617168;margin-bottom:9px}.summary-strip b{font:600 26px/1.25 var(--display);font-variant-numeric:tabular-nums}.summary-strip .summary-time b{font:500 15px/1.65 var(--mono);overflow-wrap:anywhere}
.spatial-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:22px;margin-top:16px;align-items:start}.spatial-map,.detail-sidebar{min-width:0}.spatial-stage{margin-top:0;max-height:none;width:100%}.spatial-stage img{object-fit:contain}.detail-sidebar{display:grid;gap:16px}.risk-sidebar{padding:20px;background:#f5f6f0;border:1px solid var(--line);border-radius:10px;display:flex;flex-direction:column;align-items:stretch;gap:14px}.risk-sidebar h3{font-size:26px;margin:6px 0 0}.risk-sidebar .risk-values{display:grid;grid-template-columns:1fr 1fr;gap:12px;width:100%}.risk-sidebar .risk-values span{padding:10px 0 0;background:transparent;border-top:1px solid var(--line);min-width:0;font-size:12px;color:#65756b}.risk-sidebar .risk-values span:first-child{grid-column:1/-1}.risk-sidebar .risk-values b{font-size:23px;margin-top:5px}.risk-sidebar .risk-values span:first-child b{font-size:38px;line-height:1.2}.risk-sidebar small{font:12px var(--mono);color:#738078}.risk-sidebar p{font-size:11px;line-height:1.7;color:#718078}
.env-sidebar{padding:20px;border:1px solid var(--line);border-radius:10px;background:var(--surface)}.env-sidebar h3{font:600 17px var(--display);margin:6px 0 0}.env-sidebar .env-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:16px}.env-sidebar .env-grid article{padding:11px 10px;border:0;border-radius:6px;background:#f0f3eb;min-width:0}.env-sidebar .env-grid span{font-size:12px;color:#65756b}.env-sidebar .env-grid b{font-size:23px;margin-top:5px}.env-sidebar .env-grid small{font-size:10px;margin-left:3px}.env-meta{font-size:11px;line-height:1.7;color:#718078;margin:12px 0 0}.legend{font-size:11px}.legend p{width:100%;margin:4px 0 0;font-size:10px;line-height:1.6}
@media(max-width:1100px){.summary-strip{grid-template-columns:repeat(6,minmax(0,1fr))}.summary-strip>div{grid-column:span 2;border-top:1px solid var(--line);padding:16px 20px}.summary-strip>.summary-time{grid-column:span 3;border-top:0}.summary-strip>div:nth-child(2){border-right:0}}
@media(max-width:1000px){.spatial-layout{grid-template-columns:1fr}.detail-sidebar{grid-template-columns:1fr 1fr}.summary-strip .summary-time b{font-size:14px}}
@media(max-width:650px){.detail-top{flex-direction:row;flex-wrap:wrap}.summary-strip>div{padding:14px}.summary-strip b{font-size:23px}.detail-sidebar{grid-template-columns:1fr}.field-spatial{padding:16px}.card-head>span{font-size:11px}}
.map-tools,.image-tools{display:flex;align-items:center;justify-content:flex-end;gap:12px;flex-wrap:wrap}.map-tools{flex-direction:column;align-items:flex-end;gap:6px}.map-tools label{display:flex;gap:8px;align-items:center;font-size:12px;color:#617168}.map-tools select{max-width:280px;border:1px solid var(--line);border-radius:5px;background:var(--surface);color:#26362e;padding:7px 10px;font:13px var(--display)}.map-tools>span,.image-tools>span{font-size:11px;color:#738078}.image-tabs{display:flex;border:1px solid var(--line);border-radius:5px;overflow:hidden}.image-tabs button{padding:8px 12px;border:0;background:transparent;color:#617168;font:500 13px var(--display);cursor:pointer}.image-tabs button+button{border-left:1px solid var(--line)}.image-tabs button.active{background:#e6edde;color:#315b45}.photo{display:block;width:100%;padding:0;border:0;cursor:zoom-in;text-align:left}.photo:disabled{cursor:default}.photo img{object-fit:contain}.photo>span{font-size:10px}.photo .zoom-hint{top:auto;left:auto;right:8px;bottom:8px;opacity:0;transition:opacity .15s}.photo:hover .zoom-hint,.photo:focus-visible .zoom-hint{opacity:1}.photo:focus-visible,.image-tabs button:focus-visible,.map-tools select:focus-visible{outline:2px solid #759a63;outline-offset:2px}.image-meta>b{font-size:12px}.image-meta>small{font-size:10px}.image-meta>div>span,.image-meta i{font-size:11px}.detection-summary{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:9px;border-top:1px solid var(--line);padding-top:12px}.detection-summary li{display:grid;gap:4px;font-size:12px}.detection-summary b{font-weight:500;color:#26362e}.detection-summary small{font-size:11px;color:#718078;margin-left:4px}.detection-summary span{font-size:11px;color:#617168;font-variant-numeric:tabular-nums}.detection-details{margin-top:12px;font-size:11px;color:#617168}.detection-details summary{cursor:pointer}.detection-details ol{padding-left:20px;margin:10px 0 0}.detection-details li+li{margin-top:8px}.detection-details small{display:block;overflow-wrap:anywhere;margin-top:3px;color:#718078}.detection-note{font-size:12px;line-height:1.6;color:#617168;margin-bottom:0}.image-grid{align-items:start}
.map-loading{min-height:360px;aspect-ratio:1600/1105}.spatial-stage.map-unavailable{background:#e9ede6}.map-state{position:absolute;z-index:3;left:12px;right:12px;bottom:12px;padding:9px 12px;border-radius:5px;background:rgba(247,248,242,.94);color:#7a5149;font-size:11px;text-align:center}
@media(max-width:650px){.map-tools{align-items:flex-start}.image-tools{justify-content:flex-start}.map-tools label{flex-wrap:wrap}.map-tools select{max-width:100%}}
</style>
<style scoped>
.detail-top{margin-bottom:18px}.assistant-entry{font-size:13px;padding:8px 12px;border-radius:8px;background:var(--surface)}.summary-strip{margin-bottom:20px}.summary-strip>div{padding:18px 22px}.summary-strip span{font-size:13px;margin-bottom:8px;color:#617168}.summary-strip b{font-size:28px}.summary-strip .summary-time b{font:500 15px/1.6 var(--display);font-variant-numeric:tabular-nums}
.field-spatial,.image-section,.env-card,.risk-card.surface{padding:24px}.card-head{align-items:center}.card-head h3{margin:0;font-size:19px;line-height:1.5}.section-description{font-size:13px;color:#66776c;margin:4px 0 0}.map-tools label{font-size:13px}.map-tools select{min-height:36px;min-width:150px;border-radius:8px;font-family:inherit}.map-tools>span{font-size:12px}
.spatial-layout{grid-template-columns:minmax(0,1fr) 280px;gap:24px;margin-top:20px}.spatial-stage{border-radius:10px;overflow:hidden}.detail-sidebar{display:block;border:1px solid var(--line);border-radius:12px;background:#f7f9f6;padding:20px}.risk-sidebar,.env-sidebar{padding:0;border:0;background:none;border-radius:0}.risk-sidebar{gap:14px}.risk-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.risk-heading>span{font-size:13px;color:#52665a}.risk-heading h3{font-size:13px;line-height:1.5;padding:4px 9px;border-radius:6px;background:#ba5a4c0c;margin:0}.risk-sidebar .risk-values{gap:16px}.risk-sidebar .risk-values span{border:0;padding:0;font-size:12px}.risk-sidebar .risk-values span:first-child b{font-size:44px;letter-spacing:-.04em;margin-top:3px}.risk-sidebar .risk-values b{font-size:23px;font-variant-numeric:tabular-nums}.risk-sidebar p{font-size:12px;line-height:1.7}.env-sidebar{margin-top:20px;padding-top:20px;border-top:1px solid var(--line)}.environment-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.environment-heading h3{font-size:14px;margin:0}.environment-heading>span{font-size:11px;color:#66776c}.env-sidebar .env-grid{gap:12px;margin-top:14px}.env-sidebar .env-grid article{padding:0;background:none}.env-sidebar .env-grid b{font-size:24px;font-variant-numeric:tabular-nums}.env-sidebar .env-grid span{font-size:12px}.env-sidebar .env-grid small{font-size:11px}.env-meta{font-size:11px;margin-top:14px}.legend{gap:10px 16px;font-size:12px}.legend p{font-size:11px;color:#66776c}.image-section{margin-top:20px}.image-tabs{padding:3px;gap:2px;border-radius:9px;background:#f3f6f1;border:0}.image-tabs button{border-radius:6px;font-size:13px;padding:7px 12px}.image-tabs button+button{border:0}.image-tabs button.active{background:white;box-shadow:0 1px 4px #17251f12}.image-tools>span{font-size:12px}
.image-grid{gap:16px;align-items:stretch}.image-grid .evidence-card{min-width:0;border-radius:10px;overflow:hidden;background:var(--surface);transition:border-color .18s,box-shadow .18s}.evidence-card:hover,.evidence-card:focus-within{border-color:#9aafa1;box-shadow:0 4px 16px #17251f0c}.photo{height:auto;aspect-ratio:4/3;background:#21372b}.image-meta{padding:14px}.image-meta>b{font-size:13px;font-weight:500;font-variant-numeric:tabular-nums}.image-meta>small{font-size:11px}.image-meta>div>span,.image-meta i{font-size:12px}.result-button{width:100%;display:flex;align-items:center;justify-content:space-between;border:0;border-top:1px solid var(--line);background:none;color:var(--moss);padding:10px 0 0;margin-top:12px;font-size:12px;cursor:pointer}.result-panel{max-height:min(420px,60dvh);overflow:auto;color:var(--ink);overscroll-behavior:contain}.result-panel-head{display:flex;align-items:center;justify-content:space-between}.result-panel-head>b{font-size:14px}.result-panel-head button{border:0;background:#f1f4ef;border-radius:6px;width:28px;height:28px;font-size:20px;cursor:pointer;color:#5a7061}.detection-summary{padding-top:14px;margin-top:10px;gap:12px}.detection-summary li{font-size:14px;gap:3px}.detection-summary span,.detection-summary small{font-size:12px;color:#52665a}.detection-details{font-size:12px;border-top:1px solid var(--line);padding-top:12px;margin-top:14px}.detection-details li{line-height:1.7}.detection-details small{font-size:11px}.image-placeholder{font:13px var(--display)}
@media(max-width:1100px){.spatial-layout{grid-template-columns:minmax(0,1fr) 250px;gap:18px}.detail-sidebar{padding:16px}.image-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:1000px){.spatial-layout{grid-template-columns:1fr}.detail-sidebar{display:grid;grid-template-columns:1fr 1fr;gap:24px}.env-sidebar{margin-top:0;padding:0 0 0 24px;border-top:0;border-left:1px solid var(--line)}}
@media(max-width:760px){.image-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.field-spatial,.image-section{padding:18px}.card-head{align-items:flex-start;flex-wrap:wrap}.image-tools{justify-content:flex-start}.detail-sidebar{display:block}.env-sidebar{border-left:0;border-top:1px solid var(--line);margin-top:20px;padding:20px 0 0}.summary-strip>div{padding:14px}.summary-strip .summary-time b{font-size:13px}}
@media(max-width:460px){.image-grid{grid-template-columns:1fr}.actions{flex-wrap:wrap}.assistant-entry{font-size:12px}.image-tools{gap:8px}.card-head{flex-direction:column}}
</style>
