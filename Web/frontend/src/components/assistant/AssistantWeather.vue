<template>
  <div class="weather-evidence">
    <p class="location">{{ data.location?.name }} · 天气服务数据，不是现场实测</p>
    <article v-if="data.current" class="current-weather">
      <span>当前天气 · {{ data.current.condition?.text || '天气现象未提供' }}</span>
      <strong>{{ measure(data.current.temperature) }}</strong>
      <div><span>湿度 {{ ratio(data.current.humidity) }}</span><span>风速 {{ measure(data.current.wind?.speed) }}</span><span>降水 {{ measure(data.current.precipitation?.amount) }}</span></div>
    </article>
    <div v-if="data.forecast?.days?.length" class="daily-list">
      <div v-for="day in data.forecast.days" :key="day.forecastStartTime"><span>{{ time(day.forecastStartTime, true) }}<small>{{ day.daytime?.condition?.text }} / {{ day.nighttime?.condition?.text }}</small></span><b>{{ measure(day.temperatureMin) }} — {{ measure(day.temperatureMax) }}<small>白天降水概率 {{ ratio(day.daytime?.precipitation?.probability) }}</small></b></div>
    </div>
    <details v-if="data.hourly?.hours?.length"><summary>未来 {{ data.hourly.hours.length }} 小时预报</summary><div class="hourly-scroll"><table><thead><tr><th>时段</th><th>温度</th><th>湿度</th><th>降水概率</th></tr></thead><tbody><tr v-for="hour in data.hourly.hours" :key="hour.forecastTime"><td>{{ time(hour.forecastTime) }}</td><td>{{ measure(hour.temperature) }}</td><td>{{ ratio(hour.humidity) }}</td><td>{{ ratio(hour.precipitation?.probability) }}</td></tr></tbody></table></div></details>
    <p v-for="(message,part) in data.errors" :key="part" class="weather-warning">{{ part }}：{{ message }}</p>
    <p v-if="Array.isArray(data.alerts) && !data.alerts.length" class="location">当前未返回有效官方预警，不代表没有天气风险。</p>
    <article v-for="(alert,index) in data.alerts || []" :key="index" class="alert"><b>{{ alert.headline || alert.title || alert.event || '官方天气预警' }}</b><p>{{ alert.description || alert.text || alert.instruction }}</p></article>
    <div class="attributions"><span>天气来源：和风天气</span><template v-for="(item,index) in attributions" :key="index"><a v-if="link(item)" :href="link(item)!" target="_blank" rel="noopener noreferrer">数据归因 {{ index+1 }} ↗</a><span v-else>{{ item }}</span></template></div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
// Provider structures are preserved, including units and attribution metadata.
const props=defineProps<{data:Record<string,any>}>()
const attributions=computed<string[]>(()=>[...new Set<string>([props.data,...['current','forecast','hourly'].map(k=>props.data[k])].flatMap(d=>Array.isArray(d?.metadata?.attributions)?d.metadata.attributions:[]))])
function measure(value:{value?:number;unit?:string}|undefined){return typeof value?.value==='number'?`${Math.round(value.value*10)/10}${value.unit||''}`:'—'}
function ratio(value:unknown){return typeof value==='number'?`${Math.round(value*100)}%`:'—'}
function time(value:string,dateOnly=false){const d=new Date(value);return dateOnly?d.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric'}):d.toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})}
function link(value:string){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?u.href:null}catch{return null}}
</script>
<style scoped>
.weather-evidence{font-size:11px}.location{color:#8c9d7f;line-height:1.8}.current-weather{border:1px solid #dce8cf;border-radius:9px;background:#edf4e4;padding:17px}.current-weather>span{color:#788e64}.current-weather strong{display:block;font-size:30px;font-weight:500;color:#365b2c;margin:12px 0}.current-weather>div{display:flex;gap:10px;flex-wrap:wrap;color:#8b9e79;font-size:10px}.daily-list>div{display:flex;justify-content:space-between;gap:8px;padding:13px 0;border-bottom:1px solid #e2e9d8}.daily-list b{font-weight:400;text-align:right}.daily-list small{display:block;color:#99a58b;font-size:9px;margin-top:6px}.hourly-scroll{max-height:260px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:10px}th,td{text-align:left;white-space:nowrap;padding:8px 4px;border-bottom:1px solid #e4eadb}details{margin:18px 0}summary{cursor:pointer;color:#708a59}.weather-warning,.alert{padding:10px;border-radius:6px;background:#fff4df;color:#98845e;font-size:10px;line-height:1.8}.alert p{white-space:pre-wrap}.attributions{display:flex;flex-direction:column;gap:7px;padding-top:16px;color:#94a584;font-size:9px}.attributions a{color:#799060}
</style>
