<template>
  <div class="security-page">
    <el-card shadow="never" class="security-card">
      <template #header><div class="section-title"><el-icon><Key /></el-icon><div><b>登录密码</b><p>通过当前账号手机号验证码设置或更新密码</p></div></div></template>
      <template v-if="phone">
        <div class="status-line"><span>当前状态</span><el-tag :type="auth.user?.has_phone_password ? 'success' : 'warning'">{{ auth.user?.has_phone_password ? '已设置' : '未设置' }}</el-tag></div>
        <el-form label-position="top" class="compact-form">
          <el-form-item label="短信验证码">
            <div class="row"><el-input v-model="passwordForm.code" maxlength="6" inputmode="numeric" placeholder="6 位验证码" /><el-button :disabled="phoneCountdown > 0 || phoneSending" :loading="phoneSending" @click="sendPasswordCode">{{ phoneCountdown ? `${phoneCountdown}s` : '获取验证码' }}</el-button></div>
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="passwordForm.password" type="password" show-password autocomplete="new-password" placeholder="至少 6 位，含字母和数字" />
          </el-form-item>
          <el-button type="primary" :loading="passwordSaving" @click="savePassword">{{ auth.user?.has_phone_password ? '更新密码' : '设置密码' }}</el-button>
        </el-form>
      </template>
      <el-alert v-else type="warning" :closable="false" title="当前历史账号没有手机号身份，无法设置正式登录密码" />
    </el-card>

    <el-card shadow="never" class="security-card">
      <template #header><div class="section-title"><el-icon><Cellphone /></el-icon><div><b>手机号</b><p>正式账号的唯一登录身份</p></div></div></template>
      <div class="status-line"><span>{{ phone || '未绑定' }}</span><el-tag :type="phone ? 'success' : 'info'">{{ phone ? '已绑定' : '未绑定' }}</el-tag></div>
      <p class="card-note">手机号不支持在个人资料中修改。如需处理异常绑定，请联系平台管理员。</p>
    </el-card>

    <el-card shadow="never" class="security-card">
      <template #header><div class="section-title"><el-icon><Message /></el-icon><div><b>邮箱</b><p>用于账号找回，不作为登录身份</p></div></div></template>
      <template v-if="emailStatus.verified">
        <div class="status-line"><span>{{ emailStatus.email }}</span><el-tag type="success">已绑定</el-tag></div>
        <p class="card-note">如需更换或解绑邮箱，请联系平台管理员。</p>
      </template>
      <el-form v-else ref="emailFormRef" :model="emailForm" :rules="emailRules" label-position="top" class="compact-form">
        <el-form-item label="邮箱" prop="email">
          <div class="row"><el-input v-model="emailForm.email" autocomplete="email" placeholder="请输入邮箱地址" /><el-button :disabled="emailCountdown > 0 || emailSending" :loading="emailSending" @click="sendEmailCode">{{ emailCountdown ? `${emailCountdown}s` : '获取验证码' }}</el-button></div>
        </el-form-item>
        <el-form-item label="验证码" prop="code"><el-input v-model="emailForm.code" maxlength="6" inputmode="numeric" placeholder="6 位验证码" /></el-form-item>
        <el-button type="primary" :loading="emailBinding" @click="bindEmail">绑定邮箱</el-button>
      </el-form>
    </el-card>

    <el-card shadow="never" class="security-card">
      <template #header><div class="section-title"><el-icon><RefreshLeft /></el-icon><div><b>账号找回</b><p>忘记密码时可使用已验证的恢复方式</p></div></div></template>
      <div class="recovery-actions">
        <el-button :disabled="!phone" @click="openRecovery('phone')">使用手机号找回</el-button>
        <el-button :disabled="!emailStatus.verified" @click="openRecovery('email')">使用邮箱找回</el-button>
      </div>
      <p class="card-note">进入找回流程后，需要重新完成验证码校验；重置成功会退出当前登录。</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useRouter } from 'vue-router'

import { userApi } from '@/api/user'
import { useAuthStore } from '@/stores/auth'
import type { EmailStatus } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const phone = computed(() => auth.user?.identities.find((item) => item.identity_type === 'phone')?.identifier || '')

const passwordForm = reactive({ code: '', password: '' })
const phoneCountdown = ref(0)
const phoneSending = ref(false)
const passwordSaving = ref(false)
let phoneTimer: ReturnType<typeof setInterval> | null = null

const emailFormRef = ref<FormInstance>()
const emailForm = reactive({ email: '', code: '' })
const emailStatus = ref<EmailStatus>({ has_email: false, verified: false, email: null })
const emailBinding = ref(false)
const emailSending = ref(false)
const emailCountdown = ref(0)
let emailTimer: ReturnType<typeof setInterval> | null = null
const emailRules: FormRules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  code: [{ required: true, pattern: /^\d{6}$/, message: '请输入 6 位验证码', trigger: 'blur' }],
}

function startCountdown(target: typeof phoneCountdown, timerSetter: (timer: ReturnType<typeof setInterval>) => void) {
  target.value = 60
  const timer = setInterval(() => {
    target.value -= 1
    if (target.value <= 0) clearInterval(timer)
  }, 1000)
  timerSetter(timer)
}

async function sendPasswordCode() {
  if (!phone.value || phoneCountdown.value || phoneSending.value) return
  phoneSending.value = true
  try {
    await userApi.sendCurrentPhonePasswordCode()
    ElMessage.success('验证码已发送到当前手机号')
    startCountdown(phoneCountdown, (timer) => { phoneTimer = timer })
  } finally { phoneSending.value = false }
}

async function savePassword() {
  if (!/^\d{6}$/.test(passwordForm.code) || !/^(?=.*[A-Za-z])(?=.*\d).{6,128}$/.test(passwordForm.password)) {
    ElMessage.warning('请输入 6 位验证码和包含字母、数字的密码')
    return
  }
  passwordSaving.value = true
  try {
    await userApi.setCurrentPhonePassword(passwordForm.code, passwordForm.password)
    ElMessage.success('密码已更新，请重新登录')
    auth.logout()
    await router.push('/login')
  } finally { passwordSaving.value = false }
}

async function loadEmailStatus() {
  emailStatus.value = await userApi.emailStatus()
}

async function sendEmailCode() {
  await emailFormRef.value?.validateField('email')
  if (emailCountdown.value || emailSending.value) return
  emailSending.value = true
  try {
    await userApi.sendBindEmailCode(emailForm.email)
    ElMessage.success('验证码已发送，请查收邮件')
    startCountdown(emailCountdown, (timer) => { emailTimer = timer })
  } finally { emailSending.value = false }
}

async function bindEmail() {
  await emailFormRef.value?.validate()
  emailBinding.value = true
  try {
    await userApi.bindEmail(emailForm.email, emailForm.code)
    ElMessage.success('邮箱绑定成功')
    emailForm.email = ''
    emailForm.code = ''
    await Promise.all([loadEmailStatus(), auth.fetchProfile()])
  } finally { emailBinding.value = false }
}

function openRecovery(mode: 'phone' | 'email') {
  void router.push({ path: '/forgot-password', query: { mode } })
}

onMounted(loadEmailStatus)
onBeforeUnmount(() => {
  if (phoneTimer) clearInterval(phoneTimer)
  if (emailTimer) clearInterval(emailTimer)
})
</script>

<style scoped>
.security-page{display:flex;flex-direction:column;gap:16px;max-width:760px}.security-card{width:100%}.section-title{display:flex;align-items:flex-start;gap:12px}.section-title>.el-icon{margin-top:2px;color:var(--moss);font-size:20px}.section-title b{font-size:15px}.section-title p{margin:4px 0 0;color:#7f8983;font-size:12px}.status-line{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:36px;color:#35453d;font-size:14px}.card-note{margin:12px 0 0;color:#7d8881;font-size:12px;line-height:1.7}.compact-form{max-width:460px;margin-top:16px}.row{display:flex;gap:8px;width:100%}.row .el-button{flex:0 0 auto}.recovery-actions{display:flex;flex-wrap:wrap;gap:10px}
@media(max-width:520px){.row{align-items:stretch}.row .el-button{padding-inline:12px}.recovery-actions{display:grid;grid-template-columns:1fr}.recovery-actions .el-button{margin:0}}
</style>
