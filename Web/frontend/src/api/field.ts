import http from './http'
import type { FieldItem, LiveData, SpatialResult } from '@/types'

export const fieldApi = {
  list() { return http.get('/fields') as Promise<FieldItem[]> },
  detail(fieldId: string) { return http.get(`/fields/${fieldId}`) as Promise<FieldItem> },
  live(deviceId: string) { return http.get(`/devices/${deviceId}/live`) as Promise<LiveData> },
  spatial(inspectionId: string, signal?: AbortSignal) {
    return http.get(`/inspections/${inspectionId}/spatial`, { signal }) as Promise<SpatialResult>
  },
}
