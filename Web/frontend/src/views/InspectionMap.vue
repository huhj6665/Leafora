<template>
  <div class="map-page">
    <div class="map-toolbar">
      <div><span class="eyebrow">SPATIAL OPERATIONS</span><h1>巡检地图</h1></div>
      <div class="toolbar-actions"><el-segmented v-model="layer" :options="[{label:'普通地图',value:'normal'},{label:'卫星地图',value:'satellite'}]" @change="changeLayer"/><el-button @click="load"><el-icon><Refresh /></el-icon></el-button></div>
    </div>
    <div class="map-frame">
      <div v-if="hasAmap" ref="mapRef" class="amap"></div>
      <div v-else class="fallback-map soft-grid">
        <svg v-if="allPoints.length" viewBox="0 0 1000 620" preserveAspectRatio="none">
          <g v-for="track in projectedTracks" :key="track.inspection_id"><polyline :points="track.points.map(p=>`${p.x},${p.y}`).join(' ')" fill="none" stroke="#315b45" stroke-width="4" vector-effect="non-scaling-stroke"/><circle v-for="(p,i) in track.points" :key="i" :cx="p.x" :cy="p.y" r="4" fill="#eff3e9" stroke="#315b45" stroke-width="2" vector-effect="non-scaling-stroke"/></g>
          <polygon v-for="(region,i) in projectedRegions" :key="i" :points="region.points.map(p=>`${p.x},${p.y}`).join(' ')" :class="region.level.toLowerCase()"/>
          <g v-for="(p,i) in projectedDisease" :key="i"><circle :cx="p.x" :cy="p.y" r="13" class="risk-ring"/><circle :cx="p.x" :cy="p.y" r="5" class="risk-core"/></g>
        </svg>
        <div v-else class="map-empty"><span>⌖</span><b>等待空间数据</b><p>设备上传有效 GPS 后，轨迹与风险区域会显示在这里。</p></div>
        <div class="fallback-note"><b>GIS 预览模式</b><span>配置 VITE_AMAP_KEY 后启用高德地图与卫星底图</span></div>
      </div>

      <aside class="legend-panel">
        <span class="eyebrow">MAP LAYERS</span><h3>图层与风险</h3>
        <label><i class="line"></i> GPS 巡检轨迹 <b>{{ data?.tracks.length || 0 }}</b></label><label><i class="point"></i> 病害点 <b>{{ data?.disease_points.length || 0 }}</b></label>
        <div class="risk-scale"><span>风险区域</span><div><i class="low"></i>低</div><div><i class="medium"></i>中</div><div><i class="high"></i>高</div></div>
        <div class="method"><span>SPATIAL METHOD</span><b>Voronoi + 密度合并</b><p>轨迹使用 Douglas–Peucker 空间抽样，原始 GPS 全量保留。</p></div>
      </aside>
      <div v-if="data?.disease_points.length" class="risk-summary"><span>当前视图最高风险</span><strong>{{ maxRisk.score }}</strong><i>/ 100</i><b :class="maxRisk.level.toLowerCase()">{{ levelName(maxRisk.level) }}</b></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { platformApi } from '@/api/platform'; import type { MapData } from '@/types'
const mapRef=ref<HTMLDivElement>(); const data=ref<MapData|null>(null); const layer=ref('normal'); const key=import.meta.env.VITE_AMAP_KEY as string|undefined; const hasAmap=ref(Boolean(key)); let map:any; let satellite:any
const allPoints=computed(()=>data.value?.tracks.flatMap(t=>t.points)||[])
const bounds=computed(()=>{const p=[...allPoints.value,...(data.value?.disease_points||[])];if(!p.length)return{minX:0,maxX:1,minY:0,maxY:1};return{minX:Math.min(...p.map(x=>x.lng)),maxX:Math.max(...p.map(x=>x.lng)),minY:Math.min(...p.map(x=>x.lat)),maxY:Math.max(...p.map(x=>x.lat))}})
function project(lng:number,lat:number){const b=bounds.value,dx=b.maxX-b.minX||.001,dy=b.maxY-b.minY||.001;return{x:55+(lng-b.minX)/dx*890,y:570-(lat-b.minY)/dy*520}}
const projectedTracks=computed(()=>data.value?.tracks.map(t=>({...t,points:t.points.map(p=>({...p,...project(p.lng,p.lat)}))}))||[])
const projectedDisease=computed(()=>data.value?.disease_points.map(p=>({...p,...project(p.lng,p.lat)}))||[])
const projectedRegions=computed(()=>data.value?.regions.map(r=>({...r,points:r.polygon.map(p=>project(p[0],p[1]))}))||[])
const maxRisk=computed(()=>[...(data.value?.disease_points||[])].sort((a,b)=>b.score-a.score)[0]||{score:0,level:'LOW'})
async function load(){data.value=await platformApi.map();await nextTick();if(hasAmap.value)await renderAmap()}
async function renderAmap(){if(!key||!mapRef.value||!data.value)return;try{if(import.meta.env.VITE_AMAP_SECURITY_CODE)(window as any)._AMapSecurityConfig={securityJsCode:import.meta.env.VITE_AMAP_SECURITY_CODE};const AMap=await AMapLoader.load({key,version:'2.0',plugins:['AMap.Scale','AMap.ToolBar']});map?.destroy();map=new AMap.Map(mapRef.value,{zoom:14,mapStyle:'amap://styles/normal',viewMode:'3D'});map.addControl(new AMap.Scale());map.addControl(new AMap.ToolBar());satellite=new AMap.TileLayer.Satellite();for(const track of data.value.tracks){if(track.points.length)map.add(new AMap.Polyline({path:track.points.map(p=>[p.lng,p.lat]),strokeColor:'#315b45',strokeWeight:5,showDir:true}))}for(const region of data.value.regions)map.add(new AMap.Polygon({path:region.polygon,fillColor:region.level==='HIGH'?'#ba5a4c':region.level==='MEDIUM'?'#d8a84e':'#85a56d',fillOpacity:.35,strokeColor:'#ffffff',strokeWeight:1}));for(const p of data.value.disease_points)map.add(new AMap.CircleMarker({center:[p.lng,p.lat],radius:7,fillColor:'#ba5a4c',fillOpacity:.95,strokeColor:'#fff',strokeWeight:2}));map.setFitView();changeLayer()}catch{hasAmap.value=false}}
function changeLayer(){if(!map||!satellite)return;if(layer.value==='satellite')map.add(satellite);else map.remove(satellite)}
function levelName(v:string){return({LOW:'低风险',MEDIUM:'中风险',HIGH:'高风险'} as Record<string,string>)[v]||v}
onMounted(load);onBeforeUnmount(()=>map?.destroy())
</script>

<style scoped>
.map-page{height:calc(100vh - 145px);min-height:620px}.map-toolbar{height:66px;display:flex;align-items:flex-start;justify-content:space-between}.map-toolbar h1{margin:5px 0 0;font:600 27px var(--display);letter-spacing:-.03em}.toolbar-actions{display:flex;gap:9px}.map-frame{position:relative;height:calc(100% - 66px);min-height:540px;border:1px solid #bbc4bb;background:#e8ece4;overflow:hidden}.amap,.fallback-map{position:absolute;inset:0}.fallback-map{background-color:#e9ede5;background-size:40px 40px}.fallback-map:after{content:'';position:absolute;inset:0;background:radial-gradient(circle at 60% 45%,transparent 0 18%,rgba(236,240,231,.74) 70%);pointer-events:none}.fallback-map svg{position:absolute;inset:4%;width:92%;height:92%;z-index:1}.fallback-map polygon{stroke-width:2;vector-effect:non-scaling-stroke}.fallback-map polygon.low{fill:#8cab7244;stroke:#718c5e}.fallback-map polygon.medium{fill:#d8a84e55;stroke:#b78736}.fallback-map polygon.high{fill:#ba5a4c55;stroke:#a54a3d}.risk-ring{fill:none;stroke:#ba5a4c;stroke-width:2;opacity:.35;vector-effect:non-scaling-stroke}.risk-core{fill:#ba5a4c;stroke:#fff;stroke-width:2;vector-effect:non-scaling-stroke}.map-empty{position:absolute;z-index:2;left:50%;top:50%;transform:translate(-50%,-50%);text-align:center}.map-empty span{font-size:45px;color:#6a8672}.map-empty b{display:block;margin:10px}.map-empty p{color:#7d8981;font-size:11px}.fallback-note{position:absolute;z-index:3;right:20px;bottom:18px;background:rgba(247,249,243,.9);padding:10px 13px;border:1px solid #c2c9c0}.fallback-note b,.fallback-note span{display:block}.fallback-note b{font-size:10px}.fallback-note span{font-size:8px;color:#7e8a82;margin-top:3px}.legend-panel{position:absolute;z-index:5;left:18px;top:18px;width:218px;padding:18px;background:rgba(249,250,245,.94);border:1px solid #cbd1c8;backdrop-filter:blur(12px)}.legend-panel h3{font:600 17px var(--display);margin:5px 0 16px}.legend-panel label{display:flex;align-items:center;gap:9px;padding:10px 0;border-top:1px solid #e0e4dc;font-size:10px}.legend-panel label b{margin-left:auto;font:500 11px var(--mono)}.legend-panel label i.line{width:18px;height:3px;background:#315b45}.legend-panel label i.point{width:8px;height:8px;border-radius:50%;background:#ba5a4c;box-shadow:0 0 0 3px #e3bdb7}.risk-scale{border-top:1px solid #e0e4dc;padding-top:12px;display:flex;gap:9px;align-items:center;font-size:9px}.risk-scale>span{margin-right:auto;color:#7c8880}.risk-scale div{display:flex;align-items:center;gap:3px}.risk-scale i{width:6px;height:6px;border-radius:50%}.risk-scale .low{background:#85a56d}.risk-scale .medium{background:#d8a84e}.risk-scale .high{background:#ba5a4c}.method{margin:15px -8px -8px;padding:12px;background:#edf1e8}.method span{font:8px var(--mono);color:#7b8980;letter-spacing:.12em}.method b{display:block;font-size:10px;margin:5px 0}.method p{font-size:8px;line-height:1.6;color:#7b8980;margin:0}.risk-summary{position:absolute;z-index:5;right:18px;top:18px;padding:14px 16px;background:#17251f;color:white;min-width:190px}.risk-summary>span{display:block;color:#86968c;font-size:9px}.risk-summary strong{font:600 30px var(--display);color:#f3f5ef}.risk-summary>i{font:normal 9px var(--mono);color:#829188}.risk-summary>b{float:right;margin-top:12px;font:500 9px var(--mono)}.risk-summary>b.high{color:#ee8b7e}.risk-summary>b.medium{color:#e4b969}.risk-summary>b.low{color:#a6cd87}
@media(max-width:700px){.map-page{height:calc(100vh - 125px)}.legend-panel{width:180px}.risk-summary{top:auto;bottom:15px;right:15px}.fallback-note{display:none}.toolbar-actions :deep(.el-segmented){display:none}}
</style>
