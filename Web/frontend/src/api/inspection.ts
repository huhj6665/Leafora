import http from './http'
import type {
  InspectionFull,
  InspectionListData,
  ReprocessResult,
  UploadImageResult,
} from '@/types'

export const inspectionApi = {
  list(params?: { device_id?: string; page?: number; page_size?: number }) {
    return http.get('/inspection/list', { params }) as Promise<InspectionListData>
  },

  stats(params?: { device_id?: string }) {
    return http.get('/inspection/stats', { params }) as Promise<{
      total: number
      by_device: { device_id: string; count: number }[]
    }>
  },

  get(dataId: string) {
    return http.get(`/inspection/${dataId}`) as Promise<InspectionFull>
  },

  uploadImage(deviceId: string, dataId: string, file: File) {
    const form = new FormData()
    form.append('device_id', deviceId)
    form.append('data_id', dataId)
    form.append('image', file)
    return http.post('/inspection/upload-image', form) as Promise<UploadImageResult>
  },

  reprocess(dataId: string) {
    return http.post(`/inspection/${dataId}/reprocess`) as Promise<ReprocessResult>
  },
}
