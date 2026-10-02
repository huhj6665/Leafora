import http from './http'
import type { EmailStatus, UserProfile } from '@/types'

export const userApi = {
  profile() {
    return http.get('/user/profile') as Promise<UserProfile>
  },
  updateProfile(payload: { nickname?: string; avatar?: string | null }) {
    return http.patch('/user/profile', payload) as Promise<UserProfile>
  },
  sendBindPhoneCode(phone: string) {
    return http.post('/user/phone/send-code', { phone }) as Promise<{
      phone: string
    }>
  },
  bindPhone(phone: string, code: string) {
    return http.post('/user/phone/bind', { phone, code }) as Promise<{
      phone: string
      bound: boolean
    }>
  },
  sendCurrentPhonePasswordCode() {
    return http.post('/user/security/phone-password/send-code', {}) as Promise<{
      phone: string
    }>
  },
  setCurrentPhonePassword(code: string, newPassword: string) {
    return http.post('/user/security/phone-password', {
      code,
      new_password: newPassword,
    }) as Promise<{ phone: string; password_set: boolean }>
  },
  emailStatus() {
    return http.get('/user/email') as Promise<EmailStatus>
  },
  sendBindEmailCode(email: string) {
    return http.post('/user/email/send-code', { email }) as Promise<{
      email: string
    }>
  },
  bindEmail(email: string, code: string) {
    return http.post('/user/email/bind', { email, code }) as Promise<{
      email: string
      verified: boolean
    }>
  },
}
