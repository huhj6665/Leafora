<template>
  <div class="page-shell" v-loading="loading">
    <div class="page-intro"><div><router-link to="/platform/fields" class="back">← 返回烟田管理</router-link><h1>{{ field?.name || '烟田详情' }}</h1><p class="muted">{{ field?.description }}</p></div><el-tag v-if="field" type="warning" effect="plain">{{ field.calibration_status === 'SIMULATED' ? '模拟校准数据' : field.calibration_status }}</el-tag></div>
    <section v-if="field" class="surface map-card">
      <router-link class="assistant-entry" :to="{path:'/platform/analysis',query:{field_id:field.field_id}}">让农业助手分析此烟田 ↗</router-link>
      <div class="map" :style="{aspectRatio:`${imageWidth}/${imageHeight}`}" ><img v-if="image" :src="image" alt="烟田底图"><svg :viewBox="`0 0 ${imageWidth} ${imageHeight}`"><polygon :points="boundary" fill="none" stroke="#d8ff75" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg></div>
      <aside><h3>烟田档案</h3><dl><div><dt>业务编号</dt><dd>{{ field.field_id }}</dd></div><div><dt>状态</dt><dd>{{ field.status }}</dd></div><div><dt>坐标系</dt><dd>{{ field.coordinate_system }}</dd></div><div><dt>数据来源</dt><dd>{{ field.data_source }}</dd></div><div><dt>版本</dt><dd>V{{ field.version }}</dd></div><div><dt>历史任务</dt><dd>{{ field.inspection_count }}</dd></div></dl><p>控制点和 WGS84 边界为固定可复现的模拟校准结果，不代表实测厘米级精度。</p></aside>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref } from 'vue';import { useRoute } from 'vue-router';import { fieldApi } from '@/api/field';import { getToken } from '@/utils/token';import type { FieldItem } from '@/types'
const route=useRoute(),loading=ref(true),field=ref<FieldItem|null>(null),image=ref('');const imageWidth=computed(()=>Number(field.value?.transform_params.image_width||1600)),imageHeight=computed(()=>Number(field.value?.transform_params.image_height||1105)),boundary=computed(()=>(field.value?.pixel_boundary||[]).map(p=>p.join(',')).join(' '))
async function load(){loading.value=true;try{field.value=await fieldApi.detail(String(route.params.fieldId));if(field.value.base_map_url){const r=await fetch(field.value.base_map_url,{headers:{Authorization:`Bearer ${getToken()}`}});if(r.ok)image.value=URL.createObjectURL(await r.blob())}}finally{loading.value=false}}
onMounted(load);onBeforeUnmount(()=>image.value&&URL.revokeObjectURL(image.value))
</script>
<style scoped>
.map-card{position:relative}.assistant-entry{position:absolute;left:16px;top:16px;z-index:3;padding:8px 12px;background:#f2f7e8;border:1px solid #d4e0c6;border-radius:7px;color:#4f6b3e;font-size:11px}
.back{display:block;font-size:10px;color:#6f7e75;margin-bottom:16px}.page-intro p{margin:8px 0 0}.map-card{display:grid;grid-template-columns:minmax(0,3fr) minmax(260px,1fr);min-height:min(720px,calc(100vh - 190px));overflow:hidden}.map{position:relative;background:#263b2d;min-height:540px}.map img,.map svg{position:absolute;inset:0;width:100%;height:100%}.map img{object-fit:cover}.map svg{z-index:2}.map-card aside{padding:30px}.map-card h3{font:600 22px var(--display);margin:0 0 22px}.map-card dl{margin:0}.map-card dl div{display:flex;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--line)}dt{font-size:10px;color:#839087}dd{font:10px var(--mono);margin:0}.map-card aside p{margin-top:25px;padding:15px;background:#fff4d8;color:#7a632b;font-size:9px;line-height:1.7}@media(max-width:950px){.map-card{grid-template-columns:1fr;min-height:0}.map{min-height:420px}.map-card aside{padding:22px}}@media(max-width:600px){.map{min-height:300px}}
</style>
<style scoped>
.map-card{min-height:0;align-items:start}.map{min-height:0;width:100%}.map img{object-fit:contain}.map-card aside{width:100%;box-sizing:border-box}
</style>
<style scoped>
.page-intro{margin-bottom:22px;align-items:center}.back{font-size:13px;margin-bottom:16px}.page-intro h1{font-size:26px;margin:0;line-height:1.5}.page-intro p{font-size:13px;color:#66776c;max-width:800px;line-height:1.7}.map-card{grid-template-columns:minmax(0,1fr) 280px;border-radius:12px}.map-card aside{padding:24px}.map-card h3{font-size:17px;margin-bottom:14px}.map-card dl div{gap:12px;padding:12px 0;align-items:baseline}.map-card dt{font-size:12px;flex-shrink:0}.map-card dd{font:13px var(--display);text-align:right;overflow-wrap:anywhere}.map-card aside p{font-size:12px;line-height:1.8;padding:12px;border-radius:8px}.assistant-entry{font-size:12px;background:#ffffffeb;border-color:var(--line)}.map{overflow:hidden}
@media(max-width:950px){.map-card{grid-template-columns:1fr}.map-card aside{padding:20px}.map-card dl{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}}@media(max-width:500px){.map-card dl{grid-template-columns:1fr}.page-intro{gap:14px}.page-intro h1{font-size:23px}}
</style>
