import http from './http'
import type { DeviceItem } from '@/types'

export const deviceApi = {
  list() {
    return http.get('/device/list') as Promise<DeviceItem[]>
  },
  bind(deviceId: string) {
    return http.post('/device/bind', { device_id: deviceId }) as Promise<{ device_id: string; bound: boolean }>
  },
  unbind(deviceId: string) {
    return http.post('/device/unbind', { device_id: deviceId }) as Promise<{ device_id: string; bound: boolean }>
  },
}
