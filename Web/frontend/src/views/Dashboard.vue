<template>
  <div class="page-shell dashboard" v-loading="loading">
    <section class="metrics">
      <article v-for="metric in metricCards" :key="metric.label"><div class="metric-top"><span>{{ metric.label }}</span><i :class="metric.tone">{{ metric.note }}</i></div><strong>{{ metric.value }}</strong><small>{{ metric.sub }}</small></article>
    </section>

    <section class="main-grid">
      <article class="surface field-risk-card">
        <div class="card-head"><div><h3>烟田风险概览</h3></div><router-link v-if="primaryField" :to="`/platform/fields/${primaryField.field_id}`">查看烟田 ↗</router-link></div>
        <div v-if="primaryField" :key="primaryField.field_id" class="field-risk-body" @touchstart="touchStart = $event.changedTouches[0]?.clientX ?? 0" @touchend="swipeField($event)">
          <router-link :to="latestFieldEvent?`/platform/inspections/${latestFieldEvent.inspection_id}`:`/platform/fields/${primaryField.field_id}`" class="field-thumb"><img v-if="fieldImage" :src="fieldImage" :alt="primaryField.name"><span v-else>烟田底图</span></router-link>
          <div class="field-risk-copy"><span class="field-name">{{ primaryField.name }}</span><strong :class="riskTone">{{ riskLabel }}</strong><p>{{ latestFieldEvent?`最近巡检 ${formatDate(latestFieldEvent.started_at||latestFieldEvent.created_at)}`:'尚无巡检记录' }}</p><div class="risk-facts"><span>高风险分区 <b>{{ highRiskCount }}</b></span><span>病害图片 <b>{{ latestFieldEvent?.image_count||0 }}</b></span><span>最近设备 <b>{{ latestFieldEvent?.device_id||'—' }}</b></span></div></div>
        </div>
        <div v-if="fields.length > 1" class="field-switch" aria-label="切换烟田">
          <button type="button" aria-label="上一块烟田" @click="switchField(-1)">←</button>
          <span>{{ fieldIndex + 1 }} / {{ fields.length }}</span>
          <button type="button" aria-label="下一块烟田" @click="switchField(1)">→</button>
        </div>
        <div v-if="!primaryField" class="empty-quiet"><b>尚未创建烟田</b><p>创建 READY 烟田后，这里会显示最近一次巡检的空间风险。</p></div>
      </article>

      <article class="surface activity-card">
        <div class="card-head"><div><h3>最近巡检</h3></div><router-link to="/platform/inspections">全部巡检 ↗</router-link></div>
        <div v-if="recent.length" class="event-list"><router-link v-for="item in recent" :key="item.inspection_id" :to="`/platform/inspections/${item.inspection_id}`"><span :class="['event-state',item.status.toLowerCase()]">{{ statusName(item.status) }}</span><div><b>{{ item.name }}</b><small>{{ item.device_id }} · {{ formatDate(item.started_at) }}</small></div><i>→</i></router-link></div>
        <div v-else class="empty-quiet"><b>尚无巡检记录</b><p>设备开始任务并收到云端确认后，记录会自动归档到这里。</p></div>
      </article>
    </section>

    <section class="bottom-grid">
      <article class="surface alerts-card"><div class="card-head"><div><h3>待处理提醒</h3></div><span class="caption">{{ alerts.length }} 项</span></div><div v-if="alerts.length" class="alert-list"><router-link v-for="item in alerts" :key="item.key" :to="item.to"><i :class="item.tone"></i><div><b>{{ item.title }}</b><p>{{ item.description }}</p></div><span>查看 →</span></router-link></div><div v-else class="all-clear"><span>✓</span><div><b>当前没有待处理事项</b><p>设备、任务和烟田风险均未发现需要立即处理的状态。</p></div></div></article>
      <article class="surface insight-card"><h3>今日摘要</h3><p>{{ summary }}</p><div class="brief-row"><span>本周采样</span><b>{{ metrics.week_samples||0 }}</b></div><div class="brief-row"><span>在线设备</span><b>{{ onlineDevices }}/{{ devices.length }}</b></div><router-link to="/platform/analysis">进入智能分析 <span>↗</span></router-link></article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { platformApi } from '@/api/platform'
import { fieldApi } from '@/api/field'
import { deviceApi } from '@/api/device'
import { getToken } from '@/utils/token'
import type { AnalysisOverview, DeviceItem, FieldItem, InspectionEventItem, SpatialResult } from '@/types'

const loading=ref(true),data=ref<AnalysisOverview|null>(null),fields=ref<FieldItem[]>([]),devices=ref<DeviceItem[]>([]),events=ref<InspectionEventItem[]>([]),spatial=ref<SpatialResult|null>(null),fieldImage=ref('')
const fieldIndex=ref(0),fieldImages=new Map<string,string>(),fieldSpatial=new Map<string,SpatialResult|null>()
let touchStart=0,selectionRequest=0,disposed=false
const metrics=computed(()=>data.value?.metrics||{events:0,active_events:0,samples:0,week_samples:0,devices:0,targets:0}),recent=computed(()=>data.value?.recent_events||[]),primaryField=computed(()=>fields.value[fieldIndex.value]),latestFieldEvent=computed(()=>events.value.find(item=>item.field_id===primaryField.value?.field_id)),onlineDevices=computed(()=>devices.value.filter(item=>item.communication_status==='ONLINE').length)
const highRiskCount=computed(()=>(spatial.value?.risk_grids||[]).filter(item=>item.risk_level==='HIGH').length)
const riskLabel=computed(()=>!latestFieldEvent.value?'等待首次巡检':!spatial.value?'风险数据待加载':highRiskCount.value?'存在高风险区域':(spatial.value?.risk_grids||[]).some(item=>item.risk_level==='REVIEW')?'存在重点复核区域':'整体风险较低')
const riskTone=computed(()=>highRiskCount.value?'high':riskLabel.value.includes('复核')?'review':'low')
const metricCards=computed(()=>[
  {label:'巡检记录',value:metrics.value.events,note:`${metrics.value.active_events} 运行中`,sub:'完整任务生命周期',tone:'green'},
  {label:'本周采样',value:metrics.value.week_samples,note:'近 7 天',sub:`累计 ${metrics.value.samples} 个点位`,tone:'plain'},
  {label:'识别目标',value:metrics.value.targets,note:'病害目标',sub:'边缘检测结果',tone:'amber'},
  {label:'在线设备',value:onlineDevices.value,note:`共 ${devices.value.length} 台`,sub:'通信在线状态',tone:'plain'},
])
const alerts=computed(()=>{
  const result:Array<{key:string;title:string;description:string;to:string;tone:string}>=[]
  if(highRiskCount.value)result.push({key:'risk',title:`${highRiskCount.value} 个高风险分区`,description:`${primaryField.value?.name||'烟田'}最近巡检需要重点复核`,to:latestFieldEvent.value?`/platform/inspections/${latestFieldEvent.value.inspection_id}`:'/platform/fields',tone:'danger'})
  const offline=devices.value.filter(item=>item.communication_status==='OFFLINE').length
  if(offline)result.push({key:'offline',title:`${offline} 台设备离线`,description:'请检查设备供电和网络连接',to:'/platform/devices',tone:'warning'})
  const pending=devices.value.reduce((sum,item)=>sum+item.pending_sync_count,0)
  if(pending)result.push({key:'pending',title:`${pending} 条数据待同步`,description:'设备恢复通信后将继续补传',to:'/platform/devices',tone:'warning'})
  const failed=events.value.filter(item=>item.status==='FAILED').length
  if(failed)result.push({key:'failed',title:`${failed} 条异常巡检`,description:'查看失败原因和设备状态',to:'/platform/inspections',tone:'danger'})
  return result
})
const summary=computed(()=>alerts.value.length?`当前共有 ${alerts.value.length} 类事项需要关注。建议先处理高风险烟田和异常设备，再检查待同步任务。`:`平台已接收 ${metrics.value.samples} 个现场采样点，当前没有需要立即处理的异常。`)

function switchField(direction:number){fieldIndex.value=(fieldIndex.value+direction+fields.value.length)%fields.value.length}
function swipeField(event:TouchEvent){const distance=(event.changedTouches[0]?.clientX??touchStart)-touchStart;if(Math.abs(distance)>50&&fields.value.length>1)switchField(distance<0?1:-1)}
async function loadSelectedField(){
  const field=primaryField.value,latest=latestFieldEvent.value,request=++selectionRequest
  spatial.value=null;fieldImage.value=''
  if(!field)return
  fieldImage.value=fieldImages.get(field.field_id)||''
  spatial.value=latest?fieldSpatial.get(latest.inspection_id)||null:null
  await Promise.allSettled([
    (async()=>{if(!field.base_map_url||fieldImages.has(field.field_id))return;const response=await fetch(field.base_map_url,{headers:{Authorization:`Bearer ${getToken()}`}});if(!response.ok)return;const url=URL.createObjectURL(await response.blob());if(disposed){URL.revokeObjectURL(url);return}if(fieldImages.has(field.field_id))URL.revokeObjectURL(url);else fieldImages.set(field.field_id,url);if(request===selectionRequest)fieldImage.value=fieldImages.get(field.field_id)||''})(),
    (async()=>{if(!latest)return;if(!fieldSpatial.has(latest.inspection_id)){try{fieldSpatial.set(latest.inspection_id,await fieldApi.spatial(latest.inspection_id))}catch{return}}if(!disposed&&request===selectionRequest)spatial.value=fieldSpatial.get(latest.inspection_id)||null})(),
  ])
}
async function load(){loading.value=true;try{const [overview,fieldList,deviceList,eventList]=await Promise.all([platformApi.overview(),fieldApi.list(),deviceApi.list(),platformApi.events({page_size:50})]);data.value=overview;devices.value=deviceList;events.value=eventList.items;fields.value=fieldList.sort((a,b)=>a.field_id.localeCompare(b.field_id))}finally{loading.value=false}}
function statusName(value:string){return({CREATED:'待开始',RUNNING:'进行中',RUNNING_OFFLINE:'离线运行',SYNCING:'同步中',COMPLETED:'已完成',FAILED:'异常',CANCELLED:'已取消'}as Record<string,string>)[value]||value}
function formatDate(value?:string|null){if(!value)return'暂无';return new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}
watch(primaryField,()=>void loadSelectedField())
onMounted(load);onBeforeUnmount(()=>{disposed=true;selectionRequest++;fieldImages.forEach(URL.revokeObjectURL)})
</script>

<style scoped>
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}.metrics article{position:relative;overflow:hidden;min-height:145px;padding:20px;background:var(--surface);border:1px solid var(--line);border-radius:12px}.metric-top{display:flex;justify-content:space-between;color:#6f7c74;font-size:11px}.metric-top i{font:normal 8px var(--mono);padding:4px 6px;background:#eef0e9}.metric-top .green{color:#47783c;background:#e6efdf}.metric-top .amber{color:#946a20;background:#f4ead7}.metrics strong{display:block;margin:18px 0 2px;font:600 34px var(--display)}.metrics small{color:#89938d;font-size:10px}.micro-bars{position:absolute;right:17px;bottom:19px;width:73px;height:35px;display:flex;align-items:flex-end;gap:3px}.micro-bars b{width:3px;background:#b7c1b8}.micro-bars b:nth-last-child(-n+4){background:#75916f}
.main-grid,.bottom-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(300px,.72fr);gap:14px}.bottom-grid{margin-top:14px}.field-risk-card,.activity-card,.alerts-card,.insight-card{padding:22px}.card-head{display:flex;align-items:flex-start;justify-content:space-between}.card-head h3{font:600 18px var(--display);margin:6px 0 0}.card-head>a{font-size:10px;color:#58705f;border-bottom:1px solid #9eaba0;padding-bottom:3px}.field-risk-body{display:grid;grid-template-columns:minmax(260px,1.1fr) 1fr;gap:22px;margin-top:18px}.field-thumb{min-height:255px;background:#23372c;display:grid;place-items:center;color:#8fa097;font:9px var(--mono);overflow:hidden}.field-thumb img{width:100%;height:100%;object-fit:cover}.field-risk-copy{padding:12px 0}.field-name{display:block;color:#748078;font-size:10px}.field-risk-copy>strong{display:block;margin:10px 0 8px;font:600 29px var(--display)}.field-risk-copy>strong.high{color:#b95749}.field-risk-copy>strong.review{color:#ba7a2d}.field-risk-copy>strong.low{color:#557e4c}.field-risk-copy>p{color:#879189;font-size:10px}.risk-facts{display:grid;gap:1px;margin-top:18px;background:var(--line)}.risk-facts span{display:flex;justify-content:space-between;padding:11px;background:#f5f6f0;color:#7b8780;font-size:9px}.risk-facts b{color:#314238;font:500 10px var(--mono)}
.event-list{margin-top:18px}.event-list a{display:grid;grid-template-columns:52px 1fr 16px;gap:11px;align-items:center;padding:16px 0;border-bottom:1px solid #e1e5dd}.event-list b{display:block;font-size:12px}.event-list small{display:block;color:#8b958e;font-size:9px;margin-top:5px}.event-list i{font-style:normal;color:#89958e}.event-state{font:8px var(--mono);padding:5px;text-align:center;background:#e9ece6;color:#6d7972}.event-state.running{background:#e2edd9;color:#47743c}.event-state.completed{background:#dfe9e4;color:#315b45}.event-state.failed{background:#f3dfdb;color:#a24d42}.caption{font:9px var(--mono);color:#8b958e}.alert-list{margin-top:15px}.alert-list a{display:grid;grid-template-columns:8px 1fr auto;gap:13px;align-items:center;padding:15px 0;border-top:1px solid var(--line)}.alert-list i{width:8px;height:8px;border-radius:50%;background:#71906e}.alert-list i.warning{background:#d5a13d}.alert-list i.danger{background:#b95749}.alert-list b{font-size:11px}.alert-list p{margin:4px 0 0;color:#859088;font-size:9px}.alert-list>a>span{font-size:9px;color:#64796b}.all-clear{display:flex;align-items:center;gap:15px;margin-top:18px;padding:25px;background:#edf3e8}.all-clear>span{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:#6f9a5d;color:white}.all-clear b{font-size:12px}.all-clear p{margin:5px 0 0;color:#7a877f;font-size:9px}.empty-quiet{text-align:center;padding:50px 15px}.empty-quiet p{font-size:10px;color:#879189}.insight-card{background:#263d32;color:#edf2ed}.insight-card .eyebrow{color:#82968a}.insight-card h3{font:600 20px var(--display);margin:8px 0 18px}.insight-card p{color:#aebbb3;font-size:12px;line-height:1.8;min-height:80px}.brief-row{display:flex;justify-content:space-between;border-top:1px solid #43584d;padding:12px 0;color:#aebbb3;font-size:11px}.brief-row b{color:white;font:500 15px var(--mono)}.insight-card>a{display:block;margin-top:12px;padding:12px 0;color:var(--lime);font-size:11px}.insight-card>a span{float:right}
@media(max-width:1100px){.metrics{grid-template-columns:repeat(2,1fr)}.main-grid,.bottom-grid{grid-template-columns:1fr}}@media(max-width:700px){.field-risk-body{grid-template-columns:1fr}.field-thumb{min-height:210px}}@media(max-width:600px){.metrics{grid-template-columns:1fr 1fr}.metrics article{min-height:130px;padding:16px}.metrics strong{font-size:27px}.micro-bars{display:none}}
</style>
<style scoped>
.field-switch{display:flex;justify-content:center;align-items:center;gap:18px;margin-top:16px;color:#7b8780;font:10px var(--mono)}.field-switch button{width:34px;height:30px;border:1px solid var(--line);border-radius:6px;background:#f5f6f0;color:#315b45;cursor:pointer}.field-switch button:hover{background:#e8efe1}.field-risk-body{animation:field-enter .2s ease-out;touch-action:pan-y}.field-thumb{aspect-ratio:3/2;min-height:0}.field-thumb img{object-fit:contain}.field-risk-copy{min-width:0}@keyframes field-enter{from{opacity:.5;transform:translateX(8px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.field-risk-body{animation:none}}
</style>
<style scoped>
.metrics{gap:16px;margin-bottom:24px}.metrics article{min-height:142px;padding:20px 22px}.metric-top{font-size:13px;gap:10px}.metric-top i{font:normal 11px var(--display);border-radius:5px}.metrics strong{font-size:36px;margin:14px 0 6px;line-height:1.1;font-variant-numeric:tabular-nums}.metrics small{font-size:12px;color:#66776c}.main-grid,.bottom-grid{gap:20px;grid-template-columns:minmax(0,1.65fr) minmax(280px,.85fr)}.bottom-grid{margin-top:20px}.field-risk-card,.activity-card,.alerts-card,.insight-card{padding:24px;min-width:0}.card-head{gap:16px;align-items:center}.card-head h3{font-size:18px;margin:0}.card-head>a{font-size:12px;border:0;white-space:nowrap}.field-risk-body{grid-template-columns:minmax(0,1fr) minmax(0,.9fr);gap:24px;margin-top:22px}.field-thumb{border-radius:10px}.field-name{font-size:13px;color:#52665a}.field-risk-copy{padding:4px 0}.field-risk-copy>strong{font-size:26px;line-height:1.4;margin:10px 0}.field-risk-copy>p{font-size:12px;color:#66776c}.risk-facts{background:none;gap:0;margin-top:18px}.risk-facts span{padding:10px 0;background:none;border-bottom:1px solid var(--line);font-size:12px;gap:8px;align-items:baseline}.risk-facts b{font:500 13px var(--display);overflow-wrap:anywhere;text-align:right}.field-switch{font-size:12px;margin-top:18px}.field-switch button{background:white;border-radius:50%;width:32px;height:32px;font-size:16px}.event-list{margin-top:16px}.event-list a{grid-template-columns:58px minmax(0,1fr) 16px;gap:10px;padding:16px 0}.event-list b{font-size:14px;line-height:1.5;overflow-wrap:anywhere}.event-list small{font-size:11px;line-height:1.6;color:#66776c}.event-state{font:11px var(--display);border-radius:5px}.caption{font:12px var(--display)}.alert-list b{font-size:14px}.alert-list p{font-size:12px;color:#66776c;line-height:1.6}.alert-list>a>span{font-size:12px}.all-clear{padding:18px;border-radius:8px}.all-clear>span{flex-shrink:0}.all-clear b{font-size:14px}.all-clear p{font-size:12px;line-height:1.6}.insight-card h3{font-size:18px;margin:0 0 16px}.insight-card p{font-size:14px;min-height:0}.brief-row{font-size:13px}.insight-card>a{font-size:13px}.empty-quiet p{font-size:13px}
@media(max-width:1100px){.main-grid,.bottom-grid{grid-template-columns:1fr}}@media(max-width:700px){.field-risk-body{grid-template-columns:1fr}.field-risk-copy>strong{font-size:25px}.metrics article{padding:18px;min-height:135px}.metric-top{flex-wrap:wrap}.metrics strong{font-size:30px}.metrics{gap:12px}.field-risk-card,.activity-card,.alerts-card,.insight-card{padding:20px}}
</style>
