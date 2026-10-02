import { defineStore } from 'pinia'

// 开发调试页使用的最近 API 调用记录。
export interface ApiCallRecord {
  name: string
  ok: boolean
  status?: number
  message: string
  at: string
}

export const useDevToolsStore = defineStore('devtools', {
  state: () => ({
    calls: [] as ApiCallRecord[],
  }),
  actions: {
    record(record: ApiCallRecord) {
      this.calls.unshift(record)
      if (this.calls.length > 20) {
        this.calls.pop()
      }
    },
    clear() {
      this.calls = []
    },
  },
})
