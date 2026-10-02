<template>
  <div class="profile-page">
    <el-card shadow="never" class="profile-card">
      <section id="profile" class="profile-section identity-section">
        <div class="section-heading"><div><h3>个人资料</h3><p>账号基础信息与平台展示资料</p></div><el-button type="primary" plain @click="openEditor">编辑资料</el-button></div>
        <div class="identity-summary"><UserAvatar :avatar="auth.user?.avatar" :nickname="auth.user?.nickname" :size="88" /><div><h2>{{ auth.user?.nickname || '用户' }}</h2><span>Leafora 平台用户</span></div></div>
        <dl class="profile-grid">
          <div><dt>手机号</dt><dd>{{ phone || '未绑定' }}</dd></div>
          <div><dt>邮箱</dt><dd>{{ auth.user?.email || '未绑定' }}</dd></div>
          <div><dt>账号状态</dt><dd><el-tag :type="auth.user?.status === 1 ? 'success' : 'danger'">{{ auth.user?.status === 1 ? '正常' : '已禁用' }}</el-tag></dd></div>
          <div><dt>用户 ID</dt><dd class="mono">{{ auth.user?.user_id || '—' }}</dd></div>
          <div><dt>创建时间</dt><dd>{{ formatTime(auth.user?.created_at) }}</dd></div>
        </dl>
      </section>

      <section id="security" class="profile-section" aria-label="登录与恢复设置">
        <div class="setting-list">
          <div><div><b>登录密码</b><p>{{ auth.user?.has_phone_password ? '已设置手机号登录密码' : '尚未设置手机号登录密码' }}</p></div><el-button @click="passwordVisible = true">{{ auth.user?.has_phone_password ? '更新密码' : '设置密码' }}</el-button></div>
          <div><div><b>手机号</b><p>{{ phone || '未绑定' }} · 正式账号的唯一登录身份</p></div><el-tag :type="phone ? 'success' : 'info'">{{ phone ? '已绑定' : '未绑定' }}</el-tag></div>
          <div><div><b>邮箱</b><p>{{ emailStatus.verified ? `${emailStatus.email} · 用于账号找回` : '尚未绑定恢复邮箱' }}</p></div><el-button v-if="!emailStatus.verified" @click="emailVisible = true">绑定邮箱</el-button><el-tag v-else type="success">已绑定</el-tag></div>
          <div><div><b>账号找回</b><p>通过已经验证的手机号或邮箱重新设置登录密码</p></div><div class="recovery-actions"><el-button :disabled="!phone" @click="openRecovery('phone')">手机号找回</el-button><el-button :disabled="!emailStatus.verified" @click="openRecovery('email')">邮箱找回</el-button></div></div>
        </div>
      </section>

      <section id="miniprogram" class="profile-section mini-section">
        <div class="section-heading"><div><h3>现场操作端</h3><p>通过微信小程序配对设备、开始与结束巡检</p></div></div>
        <div class="mini-layout">
          <div class="code-panel"><img :src="placeholder" width="190" height="190" alt="Leafora 小程序示意码，功能开发中"><el-tag type="info">示意码 · 功能开发中</el-tag></div>
          <div class="mini-copy"><h4>微信小程序关联</h4><p>后续可由已登录的小程序扫码确认 Web 快捷登录。Web 登录码与设备配对码是两套独立流程，不会在此页面展示或交换设备密钥。</p><el-alert type="info" :closable="false" title="当前图片仅为本地占位示意，不是可扫描二维码" /></div>
        </div>
      </section>
    </el-card>

    <el-dialog v-model="editorVisible" title="编辑个人资料" width="min(520px, calc(100vw - 32px))" align-center destroy-on-close @closed="resetEditor">
      <el-form label-position="top" @submit.prevent="saveProfile"><el-form-item label="头像"><div class="avatar-options" role="radiogroup" aria-label="选择头像"><button v-for="option in avatarOptions" :key="option.value || 'default'" type="button" role="radio" :aria-checked="form.avatar === option.value" :class="['avatar-option',{selected:form.avatar===option.value}]" @click="form.avatar=option.value"><UserAvatar :avatar="option.value" :nickname="form.nickname" :size="56"/><span>{{ option.label }}</span></button></div></el-form-item><el-form-item label="昵称" :error="nicknameError"><el-input v-model="form.nickname" maxlength="32" show-word-limit autocomplete="nickname" @keyup.enter="saveProfile"/></el-form-item><p class="edit-note">手机号和邮箱可在下方的登录与恢复设置中查看。</p></el-form>
      <template #footer><el-button @click="editorVisible=false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!changed||!formValid" @click="saveProfile">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="passwordVisible" :title="auth.user?.has_phone_password?'更新登录密码':'设置登录密码'" width="min(500px, calc(100vw - 32px))" align-center>
      <el-form label-position="top"><el-form-item label="短信验证码"><div class="form-row"><el-input v-model="passwordForm.code" maxlength="6" inputmode="numeric" placeholder="6 位验证码"/><el-button :disabled="phoneCountdown>0||phoneSending" :loading="phoneSending" @click="sendPasswordCode">{{ phoneCountdown?`${phoneCountdown}s`:'获取验证码' }}</el-button></div></el-form-item><el-form-item label="新密码"><el-input v-model="passwordForm.password" type="password" show-password autocomplete="new-password" placeholder="至少 6 位，含字母和数字"/></el-form-item></el-form>
      <template #footer><el-button @click="passwordVisible=false">取消</el-button><el-button type="primary" :loading="passwordSaving" @click="savePassword">确认</el-button></template>
    </el-dialog>

    <el-dialog v-model="emailVisible" title="绑定恢复邮箱" width="min(500px, calc(100vw - 32px))" align-center>
      <el-form ref="emailFormRef" :model="emailForm" :rules="emailRules" label-position="top"><el-form-item label="邮箱" prop="email"><div class="form-row"><el-input v-model="emailForm.email" autocomplete="email" placeholder="请输入邮箱地址"/><el-button :disabled="emailCountdown>0||emailSending" :loading="emailSending" @click="sendEmailCode">{{ emailCountdown?`${emailCountdown}s`:'获取验证码' }}</el-button></div></el-form-item><el-form-item label="验证码" prop="code"><el-input v-model="emailForm.code" maxlength="6" inputmode="numeric" placeholder="6 位验证码"/></el-form-item></el-form>
      <template #footer><el-button @click="emailVisible=false">取消</el-button><el-button type="primary" :loading="emailBinding" @click="bindEmail">确认绑定</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import placeholder from '@/assets/profile/leafora-miniprogram-placeholder.png'
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'
import { userApi } from '@/api/user'
import type { EmailStatus } from '@/types'

const auth=useAuthStore(), route=useRoute(), router=useRouter()
const editorVisible=ref(false),saving=ref(false),passwordVisible=ref(false),emailVisible=ref(false)
const form=reactive<{nickname:string;avatar:string|null}>({nickname:'',avatar:null}),original=reactive<{nickname:string;avatar:string|null}>({nickname:'',avatar:null})
const avatarOptions=[{value:null,label:'文字头像'},{value:'preset:leaf',label:'新叶'},{value:'preset:field',label:'田垄'},{value:'preset:path',label:'巡检路线'}]
const phone=computed(()=>auth.user?.identities.find(item=>item.identity_type==='phone')?.identifier||'')
const normalizedNickname=computed(()=>form.nickname.trim()),nicknameError=computed(()=>!normalizedNickname.value?'请输入昵称':normalizedNickname.value.length<2?'昵称至少 2 个字符':'')
const formValid=computed(()=>normalizedNickname.value.length>=2&&normalizedNickname.value.length<=32),changed=computed(()=>normalizedNickname.value!==original.nickname||form.avatar!==original.avatar)
const passwordForm=reactive({code:'',password:''}),phoneCountdown=ref(0),phoneSending=ref(false),passwordSaving=ref(false);let phoneTimer:ReturnType<typeof setInterval>|null=null
const emailFormRef=ref<FormInstance>(),emailForm=reactive({email:'',code:''}),emailStatus=ref<EmailStatus>({has_email:false,verified:false,email:null}),emailBinding=ref(false),emailSending=ref(false),emailCountdown=ref(0);let emailTimer:ReturnType<typeof setInterval>|null=null
const emailRules:FormRules={email:[{required:true,message:'请输入邮箱',trigger:'blur'},{type:'email',message:'邮箱格式不正确',trigger:'blur'}],code:[{required:true,pattern:/^\d{6}$/,message:'请输入 6 位验证码',trigger:'blur'}]}

function supportedAvatar(value?:string|null){return avatarOptions.some(item=>item.value===value)?value||null:null}
function openEditor(){const nickname=auth.user?.nickname||'',avatar=supportedAvatar(auth.user?.avatar);Object.assign(form,{nickname,avatar});Object.assign(original,{nickname,avatar});editorVisible.value=true}
function resetEditor(){Object.assign(form,{nickname:'',avatar:null});Object.assign(original,{nickname:'',avatar:null})}
async function saveProfile(){if(!changed.value||!formValid.value||saving.value)return;saving.value=true;try{await auth.updateProfile({nickname:normalizedNickname.value,avatar:form.avatar});ElMessage.success('个人资料已更新');editorVisible.value=false}finally{saving.value=false}}
function startCountdown(target:typeof phoneCountdown,setter:(timer:ReturnType<typeof setInterval>)=>void){target.value=60;const timer=setInterval(()=>{target.value-=1;if(target.value<=0)clearInterval(timer)},1000);setter(timer)}
async function sendPasswordCode(){if(!phone.value||phoneCountdown.value||phoneSending.value)return;phoneSending.value=true;try{await userApi.sendCurrentPhonePasswordCode();ElMessage.success('验证码已发送到当前手机号');startCountdown(phoneCountdown,timer=>{phoneTimer=timer})}finally{phoneSending.value=false}}
async function savePassword(){if(!/^\d{6}$/.test(passwordForm.code)||!/^(?=.*[A-Za-z])(?=.*\d).{6,128}$/.test(passwordForm.password)){ElMessage.warning('请输入 6 位验证码和包含字母、数字的密码');return}passwordSaving.value=true;try{await userApi.setCurrentPhonePassword(passwordForm.code,passwordForm.password);ElMessage.success('密码已更新，请重新登录');auth.logout();await router.push('/login')}finally{passwordSaving.value=false}}
async function loadEmailStatus(){emailStatus.value=await userApi.emailStatus()}
async function sendEmailCode(){await emailFormRef.value?.validateField('email');if(emailCountdown.value||emailSending.value)return;emailSending.value=true;try{await userApi.sendBindEmailCode(emailForm.email);ElMessage.success('验证码已发送，请查收邮件');startCountdown(emailCountdown,timer=>{emailTimer=timer})}finally{emailSending.value=false}}
async function bindEmail(){await emailFormRef.value?.validate();emailBinding.value=true;try{await userApi.bindEmail(emailForm.email,emailForm.code);ElMessage.success('邮箱绑定成功');emailVisible.value=false;Object.assign(emailForm,{email:'',code:''});await Promise.all([loadEmailStatus(),auth.fetchProfile()])}finally{emailBinding.value=false}}
function openRecovery(mode:'phone'|'email'){void router.push({path:'/forgot-password',query:{mode}})}
function formatTime(iso?:string|null){if(!iso)return'—';const date=new Date(iso);return Number.isNaN(date.getTime())?'—':date.toLocaleString('zh-CN',{hour12:false})}
async function focusHash(){await nextTick();if(route.hash)document.querySelector(route.hash)?.scrollIntoView({behavior:'smooth',block:'start'})}
watch(()=>route.hash,focusHash)
onMounted(async()=>{await loadEmailStatus();await focusHash()})
onBeforeUnmount(()=>{if(phoneTimer)clearInterval(phoneTimer);if(emailTimer)clearInterval(emailTimer)})
</script>

<style scoped>
.profile-page{width:100%}.profile-card{width:100%;overflow:hidden}:deep(.profile-card>.el-card__body){padding:0}.profile-section{scroll-margin-top:105px;padding:30px 34px;border-bottom:1px solid var(--line)}.profile-section:last-child{border-bottom:0}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;margin-bottom:25px}.section-heading span{color:#7d8981;font:8px var(--mono);letter-spacing:.18em}.section-heading h3{margin:6px 0 4px;font:600 22px var(--display)}.section-heading p{margin:0;color:#7b8780;font-size:11px}.identity-summary{display:flex;align-items:center;gap:20px;padding:4px 0 25px;border-bottom:1px solid var(--line)}.identity-summary h2{margin:0 0 6px;font:600 25px var(--display)}.identity-summary span{color:#78837d;font-size:12px}.profile-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin:0}.profile-grid>div{padding:20px 14px 4px 0}.profile-grid dt{margin-bottom:8px;color:#7d8781;font-size:10px}.profile-grid dd{margin:0;color:#26362e;font-size:13px}.setting-list{border-top:1px solid var(--line)}.setting-list>div{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:18px 0;border-bottom:1px solid var(--line)}.setting-list>div:last-child{border-bottom:0}.setting-list b{display:block;font-size:13px}.setting-list p{margin:5px 0 0;color:#7d8981;font-size:10px}.recovery-actions{display:flex;gap:8px}.mini-layout{display:grid;grid-template-columns:230px 1fr;align-items:center;gap:36px}.code-panel{display:flex;flex-direction:column;align-items:center;gap:12px;padding:18px;background:#f2f4ed;border:1px solid var(--line)}.code-panel img{max-width:100%;height:auto}.mini-copy h4{margin:0 0 12px;font:600 19px var(--display)}.mini-copy>p{margin:0 0 18px;color:#5f6d64;font-size:12px;line-height:1.8}.avatar-options{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;width:100%}.avatar-option{display:flex;flex-direction:column;align-items:center;gap:7px;padding:10px 6px;border:1px solid var(--line);border-radius:10px;background:#f8f9f4;color:#68746d;font-size:11px;cursor:pointer}.avatar-option.selected{border-color:var(--moss);box-shadow:0 0 0 2px rgba(49,91,69,.1);color:var(--moss)}.edit-note{color:#849089;font-size:11px}.form-row{display:flex;gap:8px;width:100%}.form-row .el-button{flex:0 0 auto}
@media(max-width:760px){.profile-section{padding:24px 20px}.profile-grid{grid-template-columns:1fr 1fr}.mini-layout{grid-template-columns:1fr}.code-panel{justify-self:stretch}.setting-list>div{align-items:flex-start;flex-direction:column}.recovery-actions{width:100%;flex-wrap:wrap}}@media(max-width:520px){.section-heading{align-items:flex-start;flex-direction:column}.profile-grid{grid-template-columns:1fr}.avatar-options{grid-template-columns:repeat(2,1fr)}.form-row{align-items:stretch}.recovery-actions{display:grid;grid-template-columns:1fr}}
</style>

<style scoped>
.identity-section{padding-top:24px}.identity-section .section-heading{margin-bottom:20px}.identity-section .section-heading h3{margin-top:0}
</style>
<style scoped>
.profile-page{max-width:1100px;margin:0 auto}.profile-section{padding:24px 28px}.section-heading{margin-bottom:22px;align-items:center}.section-heading h3{font-size:18px;margin:0 0 5px}.section-heading p{font-size:13px;color:#66776c}.identity-summary{gap:20px;padding:0 0 24px}.identity-summary h2{font-size:24px;margin-bottom:4px}.identity-summary span{font-size:13px}.profile-grid>div{padding-top:20px}.profile-grid dt{font-size:12px;color:#617168;margin-bottom:6px}.profile-grid dd{font-size:14px;font-variant-numeric:tabular-nums}.setting-list{border-top:0}.setting-list>div{padding:18px 0;gap:20px}.setting-list>div:first-child{padding-top:0}.setting-list>div:last-child{padding-bottom:0}.setting-list b{font-size:14px;font-weight:600}.setting-list p{font-size:13px;line-height:1.6;color:#66776c}.mini-layout{grid-template-columns:180px minmax(0,1fr);gap:28px}.code-panel{padding:12px;border-radius:10px}.code-panel img{width:140px;height:140px}.mini-copy h4{font-size:16px}.mini-copy>p{font-size:13px}.recovery-actions{flex-wrap:wrap}.recovery-actions :deep(.el-button+.el-button){margin-left:0}
@media(max-width:760px){.profile-section{padding:22px 20px}.setting-list>div{flex-direction:row;align-items:center;gap:12px}.setting-list>div>div:first-child{min-width:0}.recovery-actions{width:auto;flex-shrink:0;flex-direction:column}.mini-layout{grid-template-columns:1fr}.code-panel{justify-self:start}.section-heading{flex-direction:row}.identity-summary h2{font-size:20px;overflow-wrap:anywhere}}@media(max-width:460px){.setting-list>div{flex-wrap:wrap}.profile-grid{grid-template-columns:1fr 1fr}.identity-summary{gap:14px}.identity-summary h2{font-size:18px}.identity-summary :deep(.user-avatar){flex-shrink:0}.section-heading .el-button{font-size:12px}}
</style>
