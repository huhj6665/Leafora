<template>
  <div>
    <el-alert
      type="info"
      :closable="false"
      title="本页面仅在开发环境显示，用于调试后端连接与认证状态。"
      class="tip"
    />

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never" class="section">
          <template #header>Backend / Database</template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="Backend API">
              <el-tag :type="health ? 'success' : 'danger'">
                {{ health ? '正常' : '不可达' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Database">
              {{ health?.database ?? '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="Environment">{{ health?.environment ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="短信配置">
              {{ health?.sms_configured ? '已配置' : '未配置(Mock)' }}
            </el-descriptions-item>
          </el-descriptions>
          <el-button class="refresh" @click="checkHealth">刷新健康检查</el-button>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" class="section">
          <template #header>Authentication / JWT</template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="认证状态">
              <el-tag :type="auth.authenticated ? 'success' : 'danger'">
                {{ auth.authenticated ? '已认证' : '未认证' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="当前 User ID">{{ auth.userId ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="身份类型">
              {{ (auth.user?.identities ?? []).map((i) => i.identity_type).join(', ') || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="JWT 存在">{{ auth.token ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="JWT 过期时间">{{ tokenExpiry }}</el-descriptions-item>
            <el-descriptions-item label="JWT（脱敏）">{{ maskToken(auth.token) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="call-header">
          <span>最近 API 调用</span>
          <el-button size="small" @click="dev.clear()">清空</el-button>
        </div>
      </template>
      <el-table :data="dev.calls" border>
        <el-table-column prop="name" label="接口" width="180" />
        <el-table-column label="结果" width="100">
          <template #default="{ row }">
            <el-tag :type="row.ok ? 'success' : 'danger'" size="small">
              {{ row.ok ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" />
        <el-table-column prop="at" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { deviceApi } from '@/api/device'
import { healthApi } from '@/api/health'
import { userApi } from '@/api/user'
import { useAuthStore } from '@/stores/auth'
import { useDevToolsStore } from '@/stores/devtools'
import type { HealthInfo } from '@/types'
import { decodeTokenPayload, maskToken } from '@/utils/token'

const auth = useAuthStore()
const dev = useDevToolsStore()
const health = ref<HealthInfo | null>(null)

const tokenExpiry = computed(() => {
  if (!auth.token) return '—'
  const payload = decodeTokenPayload(auth.token)
  const exp = payload?.exp as number | undefined
  if (!exp) return '未知'
  return new Date(exp * 1000).toLocaleString()
})

async function checkHealth() {
  try {
    health.value = await healthApi.check()
    dev.record({ name: 'GET /api/health', ok: true, message: 'ok', at: now() })
  } catch (e) {
    health.value = null
    dev.record({ name: 'GET /api/health', ok: false, message: String(e), at: now() })
  }
}

async function checkProfile() {
  try {
    await userApi.profile()
    dev.record({ name: 'GET /api/user/profile', ok: true, message: 'ok', at: now() })
  } catch (e) {
    dev.record({ name: 'GET /api/user/profile', ok: false, message: String(e), at: now() })
  }
}

async function checkDevices() {
  try {
    await deviceApi.list()
    dev.record({ name: 'GET /api/device/list', ok: true, message: 'ok', at: now() })
  } catch (e) {
    dev.record({ name: 'GET /api/device/list', ok: false, message: String(e), at: now() })
  }
}

function now(): string {
  return new Date().toLocaleTimeString()
}

onMounted(async () => {
  await checkHealth()
  await checkProfile()
  await checkDevices()
})
</script>

<style scoped>
.tip {
  margin-bottom: 16px;
}
.section {
  margin-bottom: 16px;
}
.refresh {
  margin-top: 12px;
}
.call-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
