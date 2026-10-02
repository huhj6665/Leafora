<template>
  <div class="help-page page-shell">
    <el-card shadow="never" class="help-card">
      <template #header><b>常用操作</b></template>
      <div class="guide-list">
        <div><span>01</span><div><b>管理设备</b><p>查看已绑定设备的在线、运行和同步状态。</p><el-button link type="primary" @click="router.push('/platform/devices')">前往设备管理</el-button></div></div>
        <div><span>02</span><div><b>回看巡检</b><p>按设备与状态查找巡检记录，并进入详情查看轨迹和现场数据。</p><el-button link type="primary" @click="router.push('/platform/inspections')">前往巡检记录</el-button></div></div>
        <div><span>03</span><div><b>维护账号</b><p>设置手机号密码、绑定恢复邮箱或进入密码找回流程。</p><el-button link type="primary" @click="router.push('/platform/profile/security')">前往个人中心</el-button></div></div>
      </div>
    </el-card>

    <el-card shadow="never" class="help-card">
      <template #header><b>问题反馈</b></template>
      <p class="feedback-copy">遇到问题时，复制诊断摘要并通过现有联系渠道交给管理员。</p><p class="feedback-availability">在线工单尚未开放</p>
      <details class="diagnostic-details"><summary>查看诊断信息</summary><div class="diagnostic">
        <div><span>用户 ID</span><b>{{ auth.user?.user_id || '—' }}</b></div>
        <div><span>当前页面</span><b class="mono">{{ route.fullPath }}</b></div>
        <div><span>发生时间</span><b>{{ now }}</b></div>
      </div></details>
      <el-button type="primary" :icon="DocumentCopy" @click="copyDiagnostic">复制诊断摘要</el-button>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const now = ref(new Date().toLocaleString('zh-CN', { hour12: false }))

async function copyDiagnostic() {
  now.value = new Date().toLocaleString('zh-CN', { hour12: false })
  const text = `Leafora Web 问题反馈\n用户 ID：${auth.user?.user_id || '—'}\n当前页面：${route.fullPath}\n发生时间：${now.value}`
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('诊断摘要已复制')
  } catch {
    ElMessage.warning('浏览器未允许复制，请手动记录页面信息')
  }
}
</script>

<style scoped>
.help-page{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr);gap:16px;max-width:1100px}.help-card b{font-size:15px}.guide-list{display:flex;flex-direction:column}.guide-list>div{display:grid;grid-template-columns:42px 1fr;gap:14px;padding:18px 0;border-bottom:1px solid #e4e7df}.guide-list>div:first-child{padding-top:2px}.guide-list>div:last-child{padding-bottom:2px;border-bottom:0}.guide-list>div>span{color:#7b897f;font:500 11px var(--mono)}.guide-list b{display:block}.guide-list p,.feedback-copy{margin:6px 0;color:#69756e;font-size:13px;line-height:1.7}.guide-list .el-button{padding:0}.feedback-copy{margin:0 0 18px}.diagnostic{margin-bottom:18px;border:1px solid var(--line);border-radius:10px;background:#f4f6ef}.diagnostic>div{display:flex;justify-content:space-between;gap:20px;padding:12px 14px;border-bottom:1px solid var(--line);font-size:12px}.diagnostic>div:last-child{border-bottom:0}.diagnostic span{color:#7d8881}.diagnostic b{min-width:0;overflow-wrap:anywhere;text-align:right;font-size:12px}
@media(max-width:820px){.help-page{grid-template-columns:1fr}}@media(max-width:430px){.diagnostic>div{display:block}.diagnostic b{display:block;margin-top:5px;text-align:left}}
</style>
<style scoped>
.help-page{width:100%;max-width:1100px;margin:0 auto;gap:24px;align-items:start;grid-template-columns:minmax(0,1.2fr) minmax(300px,.8fr)}.help-card{border-radius:12px}.help-card :deep(.el-card__header){padding:20px 24px;border-bottom:0}.help-card :deep(.el-card__body){padding:0 24px 24px}.help-card :deep(.el-card__header) b{font-size:18px}.guide-list>div{grid-template-columns:36px 1fr;padding:22px 0;gap:14px}.guide-list>div>span{display:grid;place-items:center;align-self:start;width:32px;height:32px;background:#edf3ed;color:var(--moss);border-radius:8px;font:500 12px var(--display)}.guide-list b{font-size:15px}.guide-list p{font-size:13px;line-height:1.7;margin:8px 0 10px}.guide-list .el-button{font-size:13px}.feedback-copy{font-size:14px;line-height:1.8;margin-bottom:10px}.feedback-availability{display:inline-block;font-size:12px;padding:4px 9px;border-radius:6px;background:#f1f4ef;color:#617168;margin:0 0 22px}.diagnostic-details{margin-bottom:20px;border-top:1px solid var(--line);padding-top:16px;color:#52665a;font-size:13px}.diagnostic-details summary{cursor:pointer}.diagnostic{margin-top:12px;margin-bottom:0}.diagnostic>div{padding:10px 12px}.diagnostic b{font-weight:500}.diagnostic span{flex-shrink:0}
@media(max-width:820px){.help-page{grid-template-columns:1fr}.help-card :deep(.el-card__header){padding:20px}.help-card :deep(.el-card__body){padding:0 20px 20px}}
</style>
