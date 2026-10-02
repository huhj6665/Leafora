import http from './http'
import { getToken } from '@/utils/token'

export interface AssistantContext {
  field_id?: string | null
  inspection_id?: string | null
  crop: string
  variety?: string
  growth_stage: string
  location: string
}
export interface Evidence {
  id: string
  title: string
  kind: string
  url?: string | null
  retrieved_at: string
  page?: number
  locator?: string
  data: unknown
}
export interface AssistantMessage {
  id: string
  run_id?: string
  role: 'user' | 'assistant'
  content: string
  status: string
  attachment_ids: string[]
  evidence: Evidence[]
  created_at: string
}
export interface Conversation {
  id: string
  title: string
  context: AssistantContext
  active_run_id: string | null
  updated_at: string
  messages?: AssistantMessage[]
}
export interface Attachment {
  id: string
  title: string
  kind: 'IMAGE' | 'DOCUMENT'
  mime_type: string
  byte_size: number
  chunk_count: number
}
export interface Capabilities {
  model: string
  model_configured: boolean
  weather_configured: boolean
  search_configured: boolean
  vision_supported: boolean
  limits: { images: number; document_mb: number; image_mb: number; run_seconds: number }
}
export interface Run {
  id: string
  status: string
  assistant_message_id?: string
  message?: AssistantMessage
  error?: string
  model?: string
  usage?: Record<string, number>
}
export interface StreamEvent {
  id: number
  kind: string
  payload: { text?: string; items?: Evidence[]; status?: string; error?: string }
}
const prefix = '/platform/assistant'

function request<T>(url: string, method = 'GET', data?: unknown, options: Record<string, unknown> = {}) {
  return http.request<unknown, T>({ url: prefix + url, method, data, ...options })
}

export const assistantApi = {
  capabilities: () => request<Capabilities>('/capabilities'),
  list: (q = '') => request<Conversation[]>('/conversations', 'GET', undefined, { params: { q } }),
  create: (context: AssistantContext) => request<Conversation>('/conversations', 'POST', { context }),
  detail: (id: string) => request<Conversation>(`/conversations/${id}`),
  update: (id: string, data: { title?: string; context?: AssistantContext }) => request<Conversation>(`/conversations/${id}`, 'PATCH', data),
  delete: (id: string) => request(`/conversations/${id}`, 'DELETE'),
  run: (id: string, data: unknown) => request<Run>(`/conversations/${id}/runs`, 'POST', data),
  runDetail: (id: string) => request<Run>(`/runs/${id}`),
  cancel: (id: string) => request<Run>(`/runs/${id}/cancel`, 'POST'),
  attachments: () => request<Attachment[]>('/attachments'),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Attachment>('/attachments', 'POST', form, { timeout: 60000 })
  },
  removeAttachment: (id: string) => request(`/attachments/${id}`, 'DELETE'),
  fieldContext: (id: string) => request<AssistantContext & { variety: string }>(`/field-context/${id}`),
  saveFieldContext: (id: string, data: unknown) => request(`/field-context/${id}`, 'PATCH', data),
  export: (id: string, format: 'md' | 'csv') => request<Blob>(`/runs/${id}/export`, 'GET', undefined, { params: { format }, responseType: 'blob' }),
  file: (id: string) => request<Blob>(`/attachments/${id}`, 'GET', undefined, { responseType: 'blob' }),
}

export function parseEventBlock(block: string): StreamEvent | null {
  let kind = 'message', id = 0
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) kind = line.slice(6).trim()
    if (line.startsWith('id:')) id = Number(line.slice(3).trim())
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!data.length) return null
  return { id, kind, payload: JSON.parse(data.join('\n')) }
}

export async function watchRun(id: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void) {
  let after = 0
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(`/api${prefix}/runs/${encodeURIComponent(id)}/events?after=${after}`, {
        headers: { Authorization: `Bearer ${getToken()}` }, signal,
      })
      if (!response.ok || !response.body) {
        if (response.status === 401) await assistantApi.capabilities() // use existing auth-reset behavior
        throw new Error('回答连接暂时不可用')
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      try {
        while (true) {
          const { value, done } = await reader.read()
          buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, '\n')
          let boundary: number
          while ((boundary = buffer.indexOf('\n\n')) !== -1) {
            const event = parseEventBlock(buffer.slice(0, boundary))
            buffer = buffer.slice(boundary + 2)
            if (event && event.id > after) {
              after = event.id
              onEvent(event)
              if (event.kind === 'done' || event.kind === 'error') return
            }
          }
          if (done) break
        }
      } finally { reader.releaseLock() }
      const run = await assistantApi.runDetail(id)
      if (!['QUEUED', 'RUNNING'].includes(run.status)) return
      throw new Error('回答连接已中断，正在恢复')
    } catch (error) {
      if (signal.aborted) throw error
      if (attempt === 2) throw error
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, 700 * (attempt + 1))
        function abort() { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }
        signal.addEventListener('abort', abort, { once: true })
      })
    }
  }
}
