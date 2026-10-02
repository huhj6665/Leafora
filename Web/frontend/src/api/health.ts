import http from './http'
import type { HealthInfo } from '@/types'

export const healthApi = {
  check() {
    return http.get('/health') as Promise<HealthInfo>
  },
}
