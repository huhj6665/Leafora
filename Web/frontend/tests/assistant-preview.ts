// Isolated component harness, not a production route. Network is mocked by the test runner.
import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '../src/styles/global.css'
import Analysis from '../src/views/Analysis.vue'
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/platform/analysis',component:Analysis},{path:'/:pathMatch(.*)*',component:{render:()=>h('div','test navigation')}}]})
await router.push('/platform/analysis')
await router.isReady()
const app=createApp({render:()=>h('div',{style:'padding:24px'},[h('div',{style:'height:58px;color:#315b45;font-size:14px'},'Leafora · 智能分析'),h(Analysis)])})
app.use(createPinia()).use(router).use(ElementPlus).mount('#app')
