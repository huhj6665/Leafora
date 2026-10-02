import http from './http'

// 私有图片读取：以 blob 方式通过 axios 携带 Bearer Token 获取，
// 再交由组件用 URL.createObjectURL 展示。普通 <img src> 无法携带鉴权头。
export const imageApi = {
  getFile(imageId: string) {
    return http.get(`/image/${imageId}/file`, { responseType: 'blob' }) as Promise<Blob>
  },
}
