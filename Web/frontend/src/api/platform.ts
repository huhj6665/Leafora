import http from './http'
import type { AnalysisOverview, EventDetail, InspectionEventItem, MapData } from '@/types'

export const platformApi = {
  overview() {
    return http.get('/platform/analysis/overview') as Promise<AnalysisOverview>
  },
  events(params?: { status?: string; device_id?: string; page?: number; page_size?: number }) {
    return http.get('/platform/events', { params }) as Promise<{
      total: number; page: number; page_size: number; items: InspectionEventItem[]
    }>
  },
  event(inspectionId: string, includeSeries = true, signal?: AbortSignal) {
    return http.get(`/platform/events/${inspectionId}`, {
      params: { include_series: includeSeries }, signal,
    }) as Promise<EventDetail>
  },
  createEvent(body: { device_id: string; name: string; location_name?: string }) {
    return http.post('/platform/events', body) as Promise<InspectionEventItem>
  },
  updateEvent(inspectionId: string, status: string, failure_reason?: string) {
    return http.patch(`/platform/events/${inspectionId}/status`, { status, failure_reason }) as Promise<EventDetail>
  },
  map(inspectionId?: string) {
    return http.get('/platform/map', { params: { inspection_id: inspectionId } }) as Promise<MapData>
  },
  ask(question: string, inspectionId?: string) {
    return http.post('/platform/assistant/ask', { question, inspection_id: inspectionId }) as Promise<{
      answer: string; provider: string; model: string
    }>
  },
}
