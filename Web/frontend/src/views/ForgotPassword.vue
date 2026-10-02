<template>
  <div class="forgot-page">
    <el-card class="forgot-card">
      <div class="title">找回登录密码</div>
      <div class="subtitle">验证账号已绑定的手机号或邮箱</div>

      <div class="mode-switch" role="tablist" aria-label="找回方式">
        <button type="button" role="tab" :aria-selected="mode === 'phone'" :class="{ active: mode === 'phone' }" @click="setMode('phone')">手机号找回</button>
        <button type="button" role="tab" :aria-selected="mode === 'email'" :class="{ active: mode === 'email' }" @click="setMode('email')">邮箱找回</button>
      </div>

      <el-form v-if="mode === 'phone'" ref="phoneFormRef" :model="phoneForm" :rules="phoneRules" label-position="top" @keyup.enter="submitPhone">
        <el-form-item label="手机号" prop="phone">
          <div class="code-row"><el-input v-model="phoneForm.phone" maxlength="11" inputmode="tel" autocomplete="tel" placeholder="请输入登录手机号" /><el-button :disabled="countdown > 0 || sending" :loading="sending" @click="sendPhoneCode">{{ countdown > 0 ? `${countdown}s` : '获取验证码' }}</el-button></div>
        </el-form-item>
        <el-form-item label="验证码" prop="code"><el-input v-model="phoneForm.code" maxlength="6" inputmode="numeric" placeholder="6 位验证码" /></el-form-item>
        <el-form-item label="新密码" prop="newPassword"><el-input v-model="phoneForm.newPassword" type="password" show-password autocomplete="new-password" placeholder="至少 6 位，含字母和数字" /></el-form-item>
        <el-form-item label="确认新密码" prop="confirm"><el-input v-model="phoneForm.confirm" type="password" show-password autocomplete="new-password" placeholder="再次输入新密码" /></el-form-item>
        <el-button type="primary" class="submit" :loading="loading" @click="submitPhone">重置密码</el-button>
      </el-form>

      <el-form v-else ref="emailFormRef" :model="emailForm" :rules="emailRules" label-position="top" @keyup.enter="submitEmail">
        <el-alert class="email-tip" type="info" :closable="false" title="仅已验证的恢复邮箱可以找回账号" />
        <el-form-item label="邮箱" prop="email">
          <div class="code-row"><el-input v-model="emailForm.email" autocomplete="email" placeholder="请输入已绑定邮箱" /><el-button :disabled="countdown > 0 || sending" :loading="sending" @click="sendEmailCode">{{ countdown > 0 ? `${countdown}s` : '获取验证码' }}</el-button></div>
        </el-form-item>
        <el-form-item label="验证码" prop="code"><el-input v-model="emailForm.code" maxlength="6" inputmode="numeric" placeholder="6 位验证码" /></el-form-item>
        <el-form-item label="新密码" prop="newPassword"><el-input v-model="emailForm.newPassword" type="password" show-password autocomplete="new-password" placeholder="至少 6 位，含字母和数字" /></el-form-item>
        <el-form-item label="确认新密码" prop="confirm"><el-input v-model="emailForm.confirm" type="password" show-password autocomplete="new-password" placeholder="再次输入新密码" /></el-form-item>
        <el-button type="primary" class="submit" :loading="loading" @click="submitEmail">重置密码</el-button>
      </el-form>

      <div class="link-row"><el-link type="primary" @click="returnToPrevious">{{ auth.authenticated ? '返回账户与安全' : '返回登录' }}</el-link></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

type RecoveryMode = 'phone' | 'email'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const mode = ref<RecoveryMode>(route.query.mode === 'email' ? 'email' : 'phone')
const phoneFormRef = ref<FormInstance>()
const emailFormRef = ref<FormInstance>()
const loading = ref(false)
const countdown = ref(0)
const sending = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const phoneForm = reactive({ phone: '', code: '', newPassword: '', confirm: '' })
const emailForm = reactive({ email: '', code: '', newPassword: '', confirm: '' })

function passwordRules(form: { newPassword: string }): FormRules {
  return {
    code: [{ required: true, pattern: /^\d{6}$/, message: '请输入 6 位验证码', trigger: 'blur' }],
    newPassword: [{ required: true, message: '请输入新密码', trigger: 'blur' }, { min: 6, message: '密码至少 6 位', trigger: 'blur' }, { pattern: /^(?=.*[a-zA-Z])(?=.*\d)/, message: '需同时包含字母和数字', trigger: 'blur' }],
    confirm: [{ required: true, message: '请再次输入新密码', trigger: 'blur' }, { validator: (_rule, value, callback) => value === form.newPassword ? callback() : callback(new Error('两次输入的密码不一致')), trigger: 'blur' }],
  }
}

const phoneRules: FormRules = {
  phone: [{ required: true, message: '请输入手机号', trigger: 'blur' }, { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }],
  ...passwordRules(phoneForm),
}
const emailRules: FormRules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  ...passwordRules(emailForm),
}

function setMode(value: RecoveryMode) {
  mode.value = value
  stopCountdown()
  void router.replace({ query: { ...route.query, mode: value } })
}

function startCountdown() {
  countdown.value = 60
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) stopCountdown()
  }, 1000)
}

function stopCountdown() {
  if (timer) clearInterval(timer)
  timer = null
  countdown.value = 0
}

async function sendPhoneCode() {
  await phoneFormRef.value?.validateField('phone')
  if (countdown.value || sending.value) return
  sending.value = true
  try {
    await authApi.sendPhonePasswordCode(phoneForm.phone)
    ElMessage.success('验证码已发送')
    startCountdown()
  } finally { sending.value = false }
}

async function sendEmailCode() {
  await emailFormRef.value?.validateField('email')
  if (countdown.value || sending.value) return
  sending.value = true
  try {
    await authApi.forgotPassword(emailForm.email)
    ElMessage.success('如果该邮箱已绑定，验证码将发送至该邮箱')
    startCountdown()
  } finally { sending.value = false }
}

async function finishReset(action: () => Promise<unknown>) {
  loading.value = true
  try {
    await action()
    ElMessage.success('密码已重置，请使用新密码登录')
    auth.reset()
    await router.push('/login')
  } finally { loading.value = false }
}

async function submitPhone() {
  await phoneFormRef.value?.validate()
  await finishReset(() => authApi.resetPhonePassword(phoneForm.phone, phoneForm.code, phoneForm.newPassword))
}

async function submitEmail() {
  await emailFormRef.value?.validate()
  await finishReset(() => authApi.resetPassword(emailForm.email, emailForm.code, emailForm.newPassword))
}

function returnToPrevious() {
  void router.push(auth.authenticated ? '/platform/profile/security' : '/login')
}

watch(() => route.query.mode, (value) => {
  mode.value = value === 'email' ? 'email' : 'phone'
})
onBeforeUnmount(stopCountdown)
</script>

<style scoped>
.forgot-page{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px 16px;background:linear-gradient(135deg,#1f6feb 0%,#0d2b52 100%)}.forgot-card{width:420px;padding:8px 12px}.title{font-size:22px;font-weight:700;text-align:center;color:#1d2129}.subtitle{text-align:center;color:#86909c;margin:6px 0 16px}.mode-switch{display:grid;grid-template-columns:1fr 1fr;margin-bottom:18px;padding:3px;border-radius:9px;background:#eef1eb}.mode-switch button{height:36px;border:0;border-radius:7px;background:none;color:#68736d;cursor:pointer}.mode-switch button.active{background:white;color:var(--moss);box-shadow:0 1px 4px rgba(25,45,35,.12);font-weight:600}.submit{width:100%;margin-top:4px}.code-row{display:flex;gap:8px;width:100%}.code-row .el-button{flex:0 0 auto}.link-row{margin-top:12px;text-align:center}.email-tip{margin-bottom:16px}
@media(max-width:460px){.forgot-card{width:100%;padding:5px}.code-row .el-button{padding-inline:12px}}
</style>
<style scoped>
.forgot-card{border-radius:16px;box-shadow:0 12px 60px #17251f0a}.title{font:600 25px/1.5 var(--display)}.subtitle{font-size:13px;color:#66776c}.mode-switch button{font-size:14px}.forgot-card :deep(.el-input__wrapper){min-height:42px}.forgot-card :deep(.el-form-item__label){font-size:13px}
</style>
