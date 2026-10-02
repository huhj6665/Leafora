import http from './http'
import type { TokenData } from '@/types'

export const authApi = {
  register(username: string, password: string) {
    return http.post('/auth/register', { username, password }) as Promise<{
      user_id: number
      nickname: string
    }>
  },
  login(username: string, password: string) {
    return http.post('/auth/login', { username, password }) as Promise<TokenData>
  },
  sendPhoneCode(phone: string) {
    return http.post('/auth/send-phone-code', { phone }) as Promise<{
      phone: string
    }>
  },
  loginPhone(phone: string, code: string) {
    return http.post('/auth/login-phone', { phone, code }) as Promise<TokenData>
  },
  loginPhonePassword(phone: string, password: string) {
    return http.post('/auth/login-phone-password', { phone, password }) as Promise<TokenData>
  },
  sendPhonePasswordCode(phone: string) {
    return http.post('/auth/phone-password/send-code', { phone }) as Promise<{ phone: string }>
  },
  resetPhonePassword(phone: string, code: string, newPassword: string) {
    return http.post('/auth/phone-password/reset', { phone, code, new_password: newPassword }) as Promise<{ password_reset: boolean }>
  },
  setPhonePassword(phone: string, code: string, newPassword: string) {
    return http.post('/auth/phone-password/set', { phone, code, new_password: newPassword }) as Promise<{ password_set: boolean }>
  },
  createQrSession() {
    return http.post('/auth/qr-sessions') as Promise<{
      type: 'tld_web_login'; version: string; login_session_id: string
      scan_token: string; poll_token: string; expires_at: string
    }>
  },
  pollQrSession(loginSessionId: string, pollToken: string) {
    return http.get(`/auth/qr-sessions/${loginSessionId}`, { params: { poll_token: pollToken } }) as Promise<{
      login_session_id: string; status: string; expires_at: string; access_token?: string; user_id?: number
    }>
  },
  forgotPassword(email: string) {
    return http.post('/auth/forgot-password', { email }) as Promise<{
      message: string
    }>
  },
  resetPassword(email: string, code: string, newPassword: string) {
    return http.post('/auth/reset-password', {
      email,
      code,
      new_password: newPassword,
    }) as Promise<{ message: string }>
  },
}
