<template>
  <div class="page-shell" v-loading="loading">
    <section v-if="fields.length" class="field-grid">
      <router-link v-for="field in fields" :key="field.field_id" :to="`/platform/fields/${field.field_id}`" class="surface field-card">
        <div class="cover"><img v-if="images[field.field_id]" :src="images[field.field_id]" :alt="field.name"><div v-else>烟田底图</div><span>{{ field.status === 'READY' ? '可巡检' : field.status }}</span></div>
        <div class="body"><div class="title"><h3>{{ field.name }}</h3><small>V{{ field.version }}</small></div><p>{{ field.description }}</p><div class="tags"><i>{{ field.calibration_status === 'SIMULATED' ? '模拟校准' : field.calibration_status }}</i><i>{{ field.coordinate_system }}</i><i>{{ field.data_source === 'DEMO_IMPORT' ? '演示数据' : field.data_source }}</i></div><footer><span>最近巡检 <b>{{ date(field.last_inspection_at) }}</b></span><span>任务 <b>{{ field.inspection_count }}</b></span></footer></div>
      </router-link>
    </section>
    <div v-else class="surface empty"><h3>还没有烟田</h3><p>小程序开始巡检前，需要先在云端建立 READY 状态的烟田。</p></div>
  </div>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { fieldApi } from '@/api/field'; import { getToken } from '@/utils/token'; import type { FieldItem } from '@/types'
const loading=ref(true),fields=ref<FieldItem[]>([]),images=ref<Record<string,string>>({})
async function load(){loading.value=true;try{fields.value=await fieldApi.list();for(const field of fields.value){if(!field.base_map_url)continue;const r=await fetch(field.base_map_url,{headers:{Authorization:`Bearer ${getToken()}`}});if(r.ok)images.value[field.field_id]=URL.createObjectURL(await r.blob())}}finally{loading.value=false}}
function date(v?:string|null){return v?new Date(v).toLocaleDateString('zh-CN'):'暂无'}
onMounted(load);onBeforeUnmount(()=>Object.values(images.value).forEach(URL.revokeObjectURL))
</script>
<style scoped>
.page-intro p{margin:8px 0 0}.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field-card{color:inherit;text-decoration:none;overflow:hidden;transition:.2s}.field-card:hover{transform:translateY(-2px);box-shadow:0 12px 35px #243a2b14}.cover{height:230px;background:#dce4d8;position:relative;display:grid;place-items:center;color:#718075;font:10px var(--mono);overflow:hidden}.cover img{width:100%;height:100%;object-fit:cover}.cover span{position:absolute;right:12px;top:12px;background:#183024dc;color:#d9f2c9;padding:6px 9px;font:9px var(--mono)}.body{padding:20px}.title{display:flex;justify-content:space-between}.title h3{margin:0;font:600 21px var(--display)}.title small{font:10px var(--mono);color:#758179}.body p{min-height:36px;color:#7c8881;font-size:11px;line-height:1.6}.tags{display:flex;gap:6px;flex-wrap:wrap}.tags i{font:normal 8px var(--mono);padding:5px 7px;background:#edf0e9;color:#58685e}.tags i:first-child{background:#fff2cc;color:#85611b}.body footer{display:flex;justify-content:space-between;border-top:1px solid var(--line);margin-top:18px;padding-top:14px;color:#879189;font-size:9px}.body footer b{color:#33443a}.empty{text-align:center;padding:80px}.empty h3{font:600 20px var(--display)}.empty p{color:#7b877f;font-size:11px}@media(max-width:780px){.field-grid{grid-template-columns:1fr}.cover{height:190px}}
.field-grid{grid-template-columns:1fr}@media(min-width:1200px){.field-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
<style scoped>
.field-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.field-card{border-radius:12px;transition:border-color .2s,box-shadow .2s,transform .2s}.cover{height:auto;aspect-ratio:3/2;background:#e5ece3}.cover span{font:500 12px var(--display);padding:5px 10px;border-radius:6px}.body{padding:20px}.title{align-items:center;gap:12px}.title h3{font-size:18px;line-height:1.5}.title small{font-size:12px}.body p{font-size:13px;color:#66776c;line-height:1.7;min-height:44px}.tags i{font:normal 11px var(--display);border-radius:5px;padding:4px 7px}.body footer{font-size:12px;margin-top:18px;padding-top:14px;gap:10px;flex-wrap:wrap}.empty p{font-size:14px}
@media(max-width:1250px){.field-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.field-grid{grid-template-columns:1fr}.body p{min-height:0}}
</style>
