<template>
  <div class="login-page">
    <router-link to="/" class="back-home">← 返回首页</router-link>
    <section class="login-story">
      <div class="story-brand"><span><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M7 22C8 12 15 6 25 6c0 10-5 18-14 19M9 25c4-7 8-11 14-15"/></svg></span><b>Leafora</b></div>
      <div class="story-copy"><h1>把田间现场<br>带回决策桌面</h1><p>巡检轨迹、环境数据与病害识别，在同一套记录中清晰呈现。</p></div>
      <svg viewBox="0 0 620 260"><path d="M-20 220 C80 180 131 238 213 175 S354 125 435 140 S533 78 660 34" fill="none" stroke="#b7de61" stroke-width="3"/><g fill="#17251f" stroke="#b7de61" stroke-width="3"><circle cx="78" cy="202" r="6"/><circle cx="213" cy="175" r="6"/><circle cx="435" cy="140" r="6"/><circle cx="589" cy="61" r="6"/></g></svg>
      <div class="story-foot"><span>病害识别</span><span>空间分析</span><span>环境监测</span></div>
    </section>
    <el-card class="login-card">
      <div class="title">登录 Leafora</div>

      <el-tabs v-model="activeTab" stretch>
        <el-tab-pane label="手机号密码" name="account">
          <el-form
            ref="accountFormRef"
            :model="accountForm"
            :rules="accountRules"
            autocomplete="off"
            label-position="top"
            @keyup.enter="onAccountLogin"
          >
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="accountForm.phone" name="phone" autocomplete="username" inputmode="tel" maxlength="11" placeholder="请输入手机号" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="accountForm.password"
                name="password"
                type="password"
                autocomplete="current-password"
                show-password
                placeholder="请输入密码"
              />
            </el-form-item>
            <el-button
              type="primary"
              class="submit"
              :loading="accountLoading"
              @click="onAccountLogin"
            >
              登录
            </el-button>
            <div class="link-row"><el-link type="primary" @click="router.push('/forgot-password')">忘记密码</el-link></div>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="短信验证码" name="phone">
          <el-form
            ref="phoneFormRef"
            :model="phoneForm"
            :rules="phoneRules"
            autocomplete="off"
            label-position="top"
            @keyup.enter="onPhoneLogin"
          >
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="phoneForm.phone" name="phone" autocomplete="tel" inputmode="tel" placeholder="请输入手机号" maxlength="11" />
            </el-form-item>
            <el-form-item label="验证码" prop="code">
              <div class="code-row">
                <el-input v-model="phoneForm.code" name="one-time-code" autocomplete="one-time-code" inputmode="numeric" placeholder="6 位验证码" maxlength="6" />
                <el-button :disabled="countdown > 0 || sending" :loading="sending" @click="onSendCode">
                  {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
                </el-button>
              </div>
            </el-form-item>
            <el-button
              type="primary"
              class="submit"
              :loading="phoneLoading"
              @click="onPhoneLogin"
            >
              登录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="小程序扫码" name="qr">
          <div class="qr-login" v-loading="qrLoading">
            <img v-if="qrImage" :src="qrImage" alt="TLD Web 登录二维码" />
            <p>{{ qrHint }}</p>
            <el-button v-if="qrExpired" @click="createQrLogin">刷新二维码</el-button>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import QRCode from 'qrcode'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { getSafeInternalRedirect } from '@/utils/redirect'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const activeTab = ref('account')

const accountFormRef = ref<FormInstance>()
const accountForm = reactive({ phone: '', password: '' })
const accountRules: FormRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' },
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const accountLoading = ref(false)

const phoneFormRef = ref<FormInstance>()
const phoneForm = reactive({ phone: '', code: '' })
const phoneRules: FormRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}
const phoneLoading = ref(false)

const countdown = ref(0)
const sending = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

function redirectAfterLogin() {
  router.push(getSafeInternalRedirect(route.query.redirect))
}

async function onAccountLogin() {
  await accountFormRef.value?.validate()
  accountLoading.value = true
  try {
    await auth.loginByPassword(accountForm.phone, accountForm.password)
    ElMessage.success('登录成功')
    redirectAfterLogin()
  } catch {
    // 错误已由拦截器提示
  } finally {
    accountForm.password = ''
    accountLoading.value = false
  }
}

const qrImage = ref('')
const qrLoading = ref(false)
const qrExpired = ref(false)
const qrHint = ref('正在生成安全登录二维码…')
let qrTimer: ReturnType<typeof setInterval> | null = null

async function createQrLogin() {
  if (qrTimer) clearInterval(qrTimer)
  qrLoading.value = true
  qrExpired.value = false
  try {
    const session = await authApi.createQrSession()
    const content = JSON.stringify({
      type: 'tld_web_login', version: session.version,
      login_session_id: session.login_session_id,
      scan_token: session.scan_token, expires_at: session.expires_at,
    })
    qrImage.value = await QRCode.toDataURL(content, { width: 220, margin: 1 })
    qrHint.value = '请使用已登录的 TLD 微信小程序扫码并确认'
    qrTimer = setInterval(async () => {
      try {
        const result = await authApi.pollQrSession(session.login_session_id, session.poll_token)
        if (result.access_token) {
          if (qrTimer) clearInterval(qrTimer)
          await auth.applyQrToken(result.access_token)
          ElMessage.success('扫码登录成功')
          redirectAfterLogin()
        } else if (['EXPIRED', 'CANCELLED', 'CONSUMED'].includes(result.status)) {
          if (qrTimer) clearInterval(qrTimer)
          qrExpired.value = true
          qrHint.value = result.status === 'EXPIRED' ? '二维码已过期' : '登录会话已结束'
        }
      } catch {
        if (qrTimer) clearInterval(qrTimer)
        qrExpired.value = true
        qrHint.value = '二维码不可用，请刷新重试'
      }
    }, 1500)
  } finally {
    qrLoading.value = false
  }
}

watch(activeTab, (tab) => { if (tab === 'qr' && !qrImage.value) void createQrLogin() })

async function onSendCode() {
  await phoneFormRef.value?.validateField('phone')
  if (countdown.value > 0 || sending.value) return
  sending.value = true
  try {
    await authApi.sendPhoneCode(phoneForm.phone)
    ElMessage.success('验证码已发送')
    countdown.value = 60
    timer = setInterval(() => {
      countdown.value -= 1
      if (countdown.value <= 0 && timer) {
        clearInterval(timer)
        timer = null
      }
    }, 1000)
  } catch {
    // 已由拦截器提示
  } finally {
    sending.value = false
  }
}

async function onPhoneLogin() {
  await phoneFormRef.value?.validate()
  phoneLoading.value = true
  try {
    await auth.loginByPhone(phoneForm.phone, phoneForm.code)
    ElMessage.success('登录成功')
    redirectAfterLogin()
  } catch {
    // 已由拦截器提示
  } finally {
    phoneLoading.value = false
  }
}

onBeforeUnmount(() => {
  accountForm.password = ''
  if (timer) clearInterval(timer)
  if (qrTimer) clearInterval(qrTimer)
})
</script>

<style scoped>
.login-page { min-height:100vh; display:grid; grid-template-columns:1.08fr .92fr; background:#eef0e8; position:relative; }
.back-home{position:absolute;right:32px;top:25px;z-index:3;color:#6e7b73;font-size:11px}
.login-story{position:relative;overflow:hidden;background:#17251f;color:white;padding:55px 60px;display:flex;flex-direction:column;justify-content:space-between}
.login-story:after{content:'';position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:38px 38px;pointer-events:none}.story-brand{display:flex;align-items:center;gap:11px;font:600 13px var(--display);letter-spacing:.12em;z-index:1}.story-brand span{width:32px;height:32px;display:grid;place-items:center;background:var(--lime);color:#17251f;font-size:18px}.story-copy{z-index:1}.story-copy>span{color:#82948a;font:9px var(--mono);letter-spacing:.2em}.story-copy h1{font:600 clamp(40px,5vw,69px)/1.13 var(--display);letter-spacing:-.055em;margin:23px 0}.story-copy p{color:#94a39a;line-height:1.8;max-width:470px;font-size:13px}.login-story svg{position:absolute;left:0;right:0;bottom:75px;width:100%;opacity:.7}.story-foot{display:flex;gap:30px;z-index:1;color:#6f8277;font:8px var(--mono);letter-spacing:.15em}
.login-card {
  align-self:center;justify-self:center;width:min(420px,calc(100% - 48px));padding:24px 28px;border:0;box-shadow:none;background:transparent;
}
.title {
  font:600 28px var(--display);
  font-weight: 700;
  text-align: left;
  color: #1d2129;
}
.submit {
  width: 100%;
  margin-top: 4px;
}
.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.code-row .el-button {
  height: 44px;
}
.link-row {
  margin-top: 12px;
  text-align: center;
}
.link-divider {
  margin: 0 8px;
  color: #c9cdd4;
}
.qr-login{min-height:292px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}.qr-login img{width:220px;height:220px;padding:8px;background:white;border:1px solid var(--line)}.qr-login p{color:#718078;font-size:12px;line-height:1.6;margin:14px 0}
@media(max-width:850px){.login-page{grid-template-columns:1fr}.login-story{display:none}.back-home{right:auto;left:22px}.login-card{margin-top:50px}}
</style>
<style scoped>
.story-brand>span{display:grid;place-items:center;border-radius:12px}.story-brand>span svg{position:static;width:28px;height:28px;fill:none;stroke:#17251f;stroke-width:1.7}.story-brand b{font:600 24px var(--display);letter-spacing:0}.story-copy h1{font-size:clamp(36px,3.9vw,58px);line-height:1.35;letter-spacing:-.035em}.story-copy p{font-size:14px;line-height:1.9;max-width:450px;color:#b3c5b5}.story-foot span{font-size:12px;letter-spacing:0}.back-home{font-size:13px}
.login-card{padding:0;border-radius:16px;background:#ffffffb8;box-shadow:0 12px 60px #17251f0a}
.login-card :deep(.el-card__body){padding:32px 34px}
.login-card .title{margin:0 0 24px;font:600 26px/1.35 var(--display);text-align:left}
.login-card :deep(.el-tabs__header){margin:0 0 24px}
.login-card :deep(.el-tabs__item){height:44px;font-size:14px}
.login-card :deep(.el-form-item){margin-bottom:24px}
.login-card :deep(.el-form-item__label){font-size:14px;padding-bottom:8px}
.login-card :deep(.el-input__wrapper){min-height:44px}
.login-card .submit{min-height:44px;margin-top:2px;font-size:15px;font-weight:600}
.login-card .link-row{margin-top:18px}
@media(max-width:760px){.login-card{margin-top:60px}.story-brand>span svg{display:block}}
@media(max-width:460px){.login-card{width:calc(100% - 32px)}.login-card :deep(.el-card__body){padding:28px 22px}.login-card .title{font-size:24px;margin-bottom:20px}.login-card :deep(.el-tabs__item){font-size:13px}}
</style>
