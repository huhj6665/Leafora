import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

import { clearToken, getToken } from '@/utils/token'
import { getSafeInternalRedirect } from '@/utils/redirect'

// 后端统一响应：{ code, message, data }，code === 0 表示成功。
// 拦截器在成功时直接解包 data，失败时统一弹错并处理 401。
const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) {
        return body.data
      }
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  async (error: AxiosError) => {
    const status = error.response?.status
    const data = error.response?.data as { message?: string } | undefined
    const message = data?.message || error.message || '网络错误'

    if (status === 401) {
      clearToken()
      // 动态导入避免与 auth store / router 形成循环依赖
      const { useAuthStore } = await import('@/stores/auth')
      useAuthStore().reset()
      const { default: router } = await import('@/router')
      const currentRoute = router.currentRoute.value
      if (currentRoute.meta.requiresAuth && currentRoute.path !== '/login') {
        const redirect = getSafeInternalRedirect(currentRoute.fullPath)
        await router.replace({ path: '/login', query: { redirect } })
      } else if (currentRoute.path === '/login') {
        ElMessage.error(message)
      }
    } else {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  },
)

export default http
