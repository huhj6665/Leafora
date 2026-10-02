<template>
  <div class="mini-page">
    <el-card shadow="never" class="mini-card">
      <div class="mini-layout">
        <div class="code-panel">
          <img :src="placeholder" width="220" height="220" alt="Leafora 小程序示意码，功能开发中" />
          <el-tag type="info">示意码 · 功能开发中</el-tag>
        </div>
        <div class="mini-copy">
          <p class="kicker">微信小程序</p>
          <h3>小程序关联</h3>
          <p>后续可由已登录的小程序扫码确认 Web 快捷登录。Web 登录码与设备配对码是两套独立流程，不会在此页面展示或交换设备密钥。</p>
          <el-alert
            type="info"
            :closable="false"
            title="当前图片仅为本地占位示意，不是可扫描二维码"
            description="正式关联入口尚未开放，本页不会发起绑定、登录或设备配对请求。"
          />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import placeholder from '@/assets/profile/leafora-miniprogram-placeholder.png'
</script>

<style scoped>
.mini-page{max-width:860px}.mini-card{padding:12px}.mini-layout{display:grid;grid-template-columns:280px 1fr;align-items:center;gap:38px;padding:20px}.code-panel{display:flex;flex-direction:column;align-items:center;gap:14px;padding:22px;border:1px solid var(--line);border-radius:14px;background:#f4f6ef}.code-panel img{display:block;max-width:100%;height:auto;image-rendering:auto}.mini-copy .kicker{margin:0 0 8px;color:#708078;font:500 10px var(--mono);letter-spacing:.16em}.mini-copy h3{margin:0 0 15px;font:600 28px var(--display)}.mini-copy>p:not(.kicker){margin:0 0 22px;color:#59665f;line-height:1.9}
@media(max-width:680px){.mini-card{padding:0}.mini-layout{grid-template-columns:1fr;gap:24px;padding:18px}.code-panel{padding:16px}.mini-copy h3{font-size:24px}}
</style>
