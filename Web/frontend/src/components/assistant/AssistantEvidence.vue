<template>
  <section v-if="evidence" class="evidence-detail">
    <div class="evidence-title"><span>{{ evidence.id }}</span><h3>{{ evidence.title }}</h3></div>
    <p class="evidence-meta">{{ labels[evidence.kind] || '资料' }} · {{ date(evidence.retrieved_at) }}<template v-if="evidence.page"> · 第 {{ evidence.page }} {{ evidence.locator || '页/段' }}</template></p>
    <RouterLink v-if="safeInternal" :to="safeInternal" class="source-link">打开对应平台记录 ↗</RouterLink>
    <a v-else-if="safeExternal" :href="safeExternal" target="_blank" rel="noopener noreferrer" class="source-link">查看原始资料 ↗</a>
    <AssistantWeather v-if="evidence.kind === 'weather' && !Array.isArray(evidence.data)" :data="data" />
    <div v-if="rows.length" class="data-table"><table><thead><tr><th v-for="column in columns" :key="column">{{ columnLabel(column) }}</th></tr></thead><tbody><tr v-for="(row,index) in rows" :key="index"><td v-for="column in columns" :key="column">{{ cell(row[column]) }}</td></tr></tbody></table></div>
    <div v-if="metricRows.length" class="data-table"><table><thead><tr><th>指标</th><th>有效/缺失</th><th>均值</th><th>范围</th></tr></thead><tbody><tr v-for="row in metricRows" :key="row.key"><td>{{ columnLabel(row.key) }}</td><td>{{ row.valid_count }}/{{ row.missing_count }}</td><td>{{ cell(row.mean) }} {{ row.unit }}</td><td>{{ cell(row.min) }} — {{ cell(row.max) }}</td></tr></tbody></table></div>
    <div v-if="trend.length" class="chart"><p>温度（°C）· 最近 {{ trend.length }} 条有效环境记录</p><EnvironmentChart :data="trend" :fields="chartFields" :height="190" /><p>湿度（%）</p><EnvironmentChart :data="trend" :fields="humidityFields" :height="190" /></div>
    <div v-if="summary.length" class="summary-list"><div v-for="[key,value] in summary" :key="key"><span>{{ columnLabel(key) }}</span><b>{{ cell(value) }}</b></div></div>
    <p v-if="text" class="excerpt">{{ text }}</p>
    <details><summary>查看完整查询结果</summary><pre>{{ JSON.stringify(evidence.data, null, 2) }}</pre></details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import EnvironmentChart from '@/components/EnvironmentChart.vue'
import AssistantWeather from './AssistantWeather.vue'
import type { Evidence } from '@/api/assistant'
const props = defineProps<{ evidence: Evidence | null }>()
const labels: Record<string,string> = { platform:'平台数据', weather:'天气服务', document:'知识文档', web:'联网资料', knowledge:'知识检索', search:'联网检索', image:'图片' }
const names: Record<string,string> = { metric:'指标', first:'第一次', second:'第二次', delta:'变化', field_id:'烟田编号', name:'名称', status:'状态', device_id:'设备编号', started_at:'开始时间', cell_id:'分区', valid_sample_count:'有效样本', suspicious_count:'疑似样本', risk_score:'风险分', risk_level:'等级', inspection_id:'巡检编号', sample_count:'采样数', total:'总数', edge_target_count:'边缘目标数', cloud_target_count:'云端目标数', image_record_count:'图片记录数', note:'说明', cloud_scope:'云端统计范围', temperature:'温度', humidity:'湿度', co2:'CO₂', light:'光照', created_at:'创建时间', location_name:'地区', title:'标题', communication_status:'通信状态', operating_status:'运行状态', received_at:'接收时间', link_state:'链路状态', age_ms:'陈旧度（毫秒）', data_provenance:'数据来源', run_mode:'运行模式', limitations:'比较条件', temperatureMax:'最高温度', temperatureMin:'最低温度', forecastStartTime:'预报开始时间', max_temperature:'最高温度', min_temperature:'最低温度' }
const data = computed<Record<string,unknown>>(() => props.evidence?.data && typeof props.evidence.data === 'object' && !Array.isArray(props.evidence.data) ? props.evidence.data as Record<string,unknown> : {})
const safeInternal = computed(() => /^\/platform\/(fields|inspections|devices|live)(\/[^?#]*)?$/.test(props.evidence?.url || '') ? props.evidence!.url : null)
const safeExternal = computed(() => { try { const u = new URL(props.evidence?.url || ''); return ['http:','https:'].includes(u.protocol) ? u.href : null } catch { return null } })
const rows = computed<Record<string,unknown>[]>(() => {
  const value = Array.isArray(props.evidence?.data) ? props.evidence?.data : data.value.comparison || data.value.grids || data.value.items
  if (Array.isArray(value)) return value.filter(v => v && typeof v === 'object').slice(0,20)
  const detection = data.value.detection as Record<string,unknown> | undefined
  const classes = detection || data.value
  if (classes.edge_classes || classes.cloud_classes) {
    const edge = (classes.edge_classes || {}) as Record<string,number>, cloud = (classes.cloud_classes || {}) as Record<string,number>
    return [...new Set([...Object.keys(edge),...Object.keys(cloud)])].map(key => ({'类别':key,'边缘目标数':edge[key] || 0,'云端目标数':cloud[key] || 0}))
  }
  return []
})
const columns = computed(() => [...new Set(rows.value.flatMap(row => Object.keys(row)))].filter(key => !['images','polygon','text','url','evidence_id'].includes(key)).slice(0,6))
const env = computed(() => (data.value.environment || data.value) as Record<string,unknown>)
const trend = computed(() => (Array.isArray(env.value.series) ? env.value.series : []) as Array<{time:string;temperature:number|null;humidity:number|null;co2:number|null;light:number|null}>)
const metricRows = computed(() => Object.entries((env.value.metrics || {}) as Record<string,Record<string,unknown>>).map(([key,value])=>({key,valid_count:value.valid_count,missing_count:value.missing_count,mean:value.mean,unit:value.unit,min:value.min,max:value.max})))
const chartFields = [{key:'temperature',name:'温度 °C',color:'#315b45'}]
const humidityFields = [{key:'humidity',name:'湿度 %',color:'#a7bd73'}]
const summary = computed(() => Object.entries(data.value).filter(([_,v]) => v === null || ['string','number','boolean'].includes(typeof v)).slice(0,14))
const text = computed(() => typeof data.value.text === 'string' ? data.value.text : '')
function columnLabel(key:string){return names[key] || key}
function cell(value:unknown){if(value===null || value===undefined)return '—';if(typeof value==='boolean')return value?'是':'否';if(typeof value==='object')return JSON.stringify(value);return String(value)}
function date(value:string){return new Date(value).toLocaleString('zh-CN',{hour12:false})}
</script>

<style scoped>
.evidence-detail{font-size:12px;color:var(--ink-2)}.evidence-title{display:flex;gap:9px;align-items:flex-start}.evidence-title>span{padding:3px 6px;background:#e3ecd9;color:var(--moss);border-radius:4px;font-family:var(--mono);font-size:10px}.evidence-title h3{margin:0;font-size:14px;line-height:1.6}.evidence-meta{color:#879084;font-size:11px;line-height:1.7}.source-link{display:inline-block;color:var(--moss);font-weight:600;margin:4px 0 16px}.data-table{overflow-x:auto;margin-bottom:15px}table{border-collapse:collapse;width:100%;font-size:11px}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);white-space:nowrap}th{background:#eef2e8}.summary-list>div{display:flex;gap:15px;justify-content:space-between;padding:9px 0;border-bottom:1px solid #e8eae2}.summary-list span{flex-shrink:0;color:#7d887f}.summary-list b{font-weight:400;text-align:right;overflow-wrap:anywhere}.excerpt{white-space:pre-wrap;line-height:1.9;padding:12px;background:#f1f4eb;border-radius:8px}.chart{margin:12px -8px}details{margin-top:18px}summary{cursor:pointer;color:#82907f;font-size:11px}pre{font:10px/1.7 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;padding:10px;background:#edf0e7;border-radius:6px;max-height:380px;overflow:auto}
</style>
