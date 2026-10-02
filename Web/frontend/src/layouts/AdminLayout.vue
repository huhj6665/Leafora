<template>
  <div class="app-layout" :class="{ 'analysis-layout': route.path === '/platform/analysis' }">
    <aside :class="['sidebar', { open: menuOpen }]" aria-label="平台导航">
      <router-link to="/" class="logo" aria-label="Leafora 烟草智能巡检平台首页" @click="closeMenu">
        <span aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M7 22C8 12 15 6 25 6c0 10-5 18-14 19"/><path d="M9 25c4-7 8-11 14-15"/></svg></span><div><b>Leafora</b><small>烟草智能巡检平台</small></div>
      </router-link>

      <nav class="main-nav" aria-label="主要功能">
        <router-link v-for="item in nav" :key="item.path" :to="item.path" @click="closeMenu">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
        </router-link>
      </nav>

      <nav class="profile-nav" aria-label="个人中心">
        <router-link to="/platform/profile" @click="closeMenu">
          <el-icon><User /></el-icon><span>个人中心</span>
        </router-link>
      </nav>

      <nav class="support-nav" aria-label="支持">
        <router-link to="/platform/help" @click="closeMenu">
          <el-icon><QuestionFilled /></el-icon><span>帮助与反馈</span>
        </router-link>
      </nav>

      <div class="sidebar-spacer"></div>
      <button class="logout-button" type="button" @click="logout">
        <el-icon><SwitchButton /></el-icon><span>退出平台</span>
      </button>
    </aside>

    <div v-if="menuOpen" class="backdrop" aria-hidden="true" @click="closeMenu"></div>

    <section class="workspace">
      <header>
        <div class="title-wrap">
          <button
            class="menu-toggle"
            type="button"
            aria-label="打开平台导航"
            :aria-expanded="menuOpen"
            @click="menuOpen = !menuOpen"
          >
            <el-icon><Menu /></el-icon>
          </button>
          <div><h2>{{ route.meta.title }}</h2></div>
        </div>
        <el-dropdown @command="onCommand">
          <div class="user" tabindex="0">
            <UserAvatar :avatar="auth.user?.avatar" :nickname="auth.user?.nickname" :size="36" />
            <div><b>{{ auth.user?.nickname || '用户' }}</b></div>
            <el-icon><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人中心</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>
      <main><router-view /></main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const menuOpen = ref(false)

const nav = [
  { path: '/platform/overview', label: '巡检总览', icon: 'DataLine' },
  { path: '/platform/inspections', label: '巡检记录', icon: 'Tickets' },
  { path: '/platform/fields', label: '烟田管理', icon: 'MapLocation' },
  { path: '/platform/devices', label: '设备管理', icon: 'Monitor' },
  { path: '/platform/live', label: '实时数据', icon: 'Odometer' },
  { path: '/platform/analysis', label: '智能分析', icon: 'TrendCharts' },
]

function closeMenu() {
  menuOpen.value = false
}

function logout() {
  auth.logout()
  void router.push('/')
}

function onCommand(command: string) {
  if (command === 'logout') logout()
  else void router.push('/platform/profile')
}

</script>

<style scoped>
.app-layout{display:flex;min-height:100vh;background:var(--paper)}
.sidebar{position:fixed;z-index:30;inset:0 auto 0 0;width:248px;background:#17251f;color:#d8dfd9;padding:0 16px;display:flex;flex-direction:column;overflow-y:auto}
.logo{height:83px;display:flex;align-items:center;gap:11px;padding:0 10px}
.logo>span{display:grid;place-items:center;flex:0 0 34px;height:34px;border:1px solid rgba(182,219,112,.55)}.logo svg{width:23px;fill:none;stroke:#a9d35e;stroke-width:1.5;stroke-linecap:round}
.logo b{display:block;font:600 18px/1 var(--display);letter-spacing:.03em}.logo small{display:block;color:#aab3ac;font-size:10px;letter-spacing:.08em;margin-top:5px}
.main-nav{padding-top:24px}.sidebar nav{display:flex;flex-direction:column;gap:3px}
.sidebar nav a,.profile-parent,.logout-button{position:relative;display:flex;align-items:center;gap:13px;width:100%;height:46px;padding:0 13px;border:0;border-radius:7px;background:none;color:#8fa097;font-size:13px;text-align:left;cursor:pointer}
.sidebar nav a:hover,.profile-parent:hover,.logout-button:hover{color:#e5ebe6;background:#21352c}
.sidebar nav a.router-link-active,.profile-parent.active{color:#f5f8f4;background:#294434}
.sidebar nav a.router-link-active:before,.profile-parent.active:before{content:'';position:absolute;left:0;width:3px;height:19px;background:var(--lime)}
.profile-nav{margin-top:18px}
.support-nav{margin-top:7px}.sidebar-spacer{flex:1;min-height:28px}
.logout-button{flex:0 0 auto;height:54px;color:#718178;margin-bottom:14px}.logout-button:hover{background:none;color:#fff}
.workspace{margin-left:248px;width:calc(100% - 248px);min-height:100vh}.workspace>header{height:83px;display:flex;justify-content:space-between;align-items:center;padding:0 32px;background:rgba(247,248,242,.88);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}
.title-wrap{display:flex;align-items:center;gap:14px}.title-wrap span{display:block;color:#7e8a83;font:8px var(--mono);letter-spacing:.2em}.title-wrap h2{margin:4px 0 0;font:600 23px/1.05 var(--display);letter-spacing:-.025em}
.user{display:flex;align-items:center;gap:10px;cursor:pointer;outline:none}.user:focus-visible{box-shadow:0 0 0 3px rgba(49,91,69,.2);border-radius:20px}.user b{display:block;font-size:12px}.user small{display:block;margin-top:2px;color:#879189;font:8px var(--mono)}.user>.el-icon{color:#879189;font-size:11px}
.workspace>main{padding:31px 32px 50px}.menu-toggle{display:none;border:0;background:none;color:var(--ink);font-size:22px;cursor:pointer}.backdrop{display:none}
@media(max-width:920px){.sidebar{transform:translateX(-100%);transition:transform .25s}.sidebar.open{transform:translateX(0)}.backdrop{display:block;position:fixed;z-index:25;inset:0;background:rgba(10,20,15,.45)}.workspace{margin-left:0;width:100%}.menu-toggle{display:grid;place-items:center;padding:5px}.workspace>header{padding:0 18px}.workspace>main{padding:22px 16px}.user>div,.user>small,.user>.el-icon{display:none}}
</style>
<style scoped>
.sidebar{width:224px;padding:0 14px;background:#15271e}.logo{height:72px;gap:12px}.logo>span{border:0;background:#b7de6118;border-radius:10px;flex-basis:36px;height:36px}.logo b{font-size:21px}.logo small{font-size:11px;letter-spacing:0}
.main-nav{padding-top:20px}.sidebar nav{gap:6px}.sidebar nav a,.logout-button{font-size:14px;height:44px;gap:12px;color:#b3c1b8}.sidebar nav a.router-link-active{background:#315640;color:white}.sidebar nav a.router-link-active:before{display:none}.sidebar nav .el-icon,.logout-button .el-icon{font-size:18px}.support-nav,.profile-nav{margin-top:6px}
.workspace{margin-left:224px;width:calc(100% - 224px);--workspace-header:72px;--workspace-gap:24px}.workspace>header{height:var(--workspace-header);padding:0 28px;background:#ffffffec}.title-wrap h2{font-size:22px;line-height:1.4;margin:0;font-weight:600}.user b{font-size:14px;font-weight:500}.user>.el-icon{font-size:13px}.workspace>main{padding:var(--workspace-gap) 28px 32px}
.analysis-layout .workspace{height:100dvh;min-height:0;display:flex;flex-direction:column;overflow:hidden}.analysis-layout .workspace>header{flex:0 0 var(--workspace-header)}.analysis-layout .workspace>main{flex:1;min-height:0;display:flex;flex-direction:column;padding-bottom:var(--workspace-gap)}
@media(max-width:920px){.workspace{width:100%;margin-left:0;--workspace-header:64px;--workspace-gap:16px}.workspace>header{padding:0 18px}.workspace>main{padding:var(--workspace-gap) 16px 24px}.title-wrap h2{font-size:20px}.analysis-layout .workspace>main{padding-bottom:var(--workspace-gap)}}
</style>
