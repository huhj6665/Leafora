import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/Login.vue'),
      meta: { public: true },
    },
    { path: '/register', redirect: '/login' },
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('@/views/ForgotPassword.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/Home.vue'),
      meta: { public: true },
    },
    {
      path: '/platform',
      component: () => import('@/layouts/AdminLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/platform/overview' },
        {
          path: 'overview',
          name: 'dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { title: '巡检总览', eyebrow: 'OPERATIONS' },
        },
        {
          path: 'inspections',
          name: 'inspections',
          component: () => import('@/views/Inspections.vue'),
          meta: { title: '巡检记录', eyebrow: 'FIELD MISSIONS' },
        },
        {
          path: 'inspections/:inspectionId',
          name: 'inspection-detail',
          component: () => import('@/views/InspectionDetail.vue'),
          meta: { title: '巡检详情', eyebrow: 'MISSION DETAIL' },
        },
        { path: 'map', redirect: '/platform/fields' },
        {
          path: 'fields', name: 'fields', component: () => import('@/views/Fields.vue'),
          meta: { title: '烟田管理', eyebrow: 'FIELD ASSETS' },
        },
        {
          path: 'fields/:fieldId', name: 'field-detail', component: () => import('@/views/FieldDetail.vue'),
          meta: { title: '烟田详情', eyebrow: 'FIELD DETAIL' },
        },
        {
          path: 'analysis',
          name: 'analysis',
          component: () => import('@/views/Analysis.vue'),
          meta: { title: '智能分析', eyebrow: 'INTELLIGENCE' },
        },
        {
          path: 'devices',
          name: 'devices',
          component: () => import('@/views/Devices.vue'),
          meta: { title: '设备管理' },
        },
        {
          path: 'live', name: 'live-data', component: () => import('@/views/LiveData.vue'),
          meta: { title: '实时数据', eyebrow: 'LIVE TELEMETRY' },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('@/views/Profile.vue'),
          meta: { title: '个人中心' },
        },
        {
          path: 'profile/security',
          redirect: { path: '/platform/profile', hash: '#security' },
        },
        {
          path: 'profile/miniprogram',
          redirect: { path: '/platform/profile', hash: '#miniprogram' },
        },
        {
          path: 'account-security',
          redirect: { path: '/platform/profile', hash: '#security' },
        },
        {
          path: 'help',
          name: 'help',
          component: () => import('@/views/HelpFeedback.vue'),
          meta: { title: '帮助与反馈' },
        },
        {
          path: 'dev-tools',
          name: 'dev-tools',
          component: () => import('@/views/DevTools.vue'),
          meta: { title: '开发调试' },
        },
      ],
    },
    { path: '/dashboard', redirect: '/platform/overview' },
    { path: '/devices', redirect: '/platform/devices' },
    { path: '/profile', redirect: '/platform/profile' },
    { path: '/account-security', redirect: { path: '/platform/profile', hash: '#security' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // 仅开发模式可访问 devOnly 页面
  if (to.meta.devOnly && !import.meta.env.DEV) {
    return { path: '/platform/overview' }
  }

  if (to.meta.requiresAuth) {
    if (!auth.token) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
    // 刷新页面后主动向后端校验 token，恢复登录态
    if (!auth.initialized) {
      try {
        await auth.fetchProfile()
      } catch {
        auth.reset()
        return { path: '/login', query: { redirect: to.fullPath } }
      }
    }
  }

  // 首页在登录前后均可访问；已登录用户仅在进入认证页时跳转到工作台
  if (auth.authenticated && to.name === 'login') {
    return { path: '/platform/overview' }
  }
})

export default router
