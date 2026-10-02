import { defineStore } from 'pinia'

import { authApi } from '@/api/auth'
import { userApi } from '@/api/user'
import type { UserProfile } from '@/types'
import { clearToken, getToken, setToken } from '@/utils/token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken(),
    user: null as UserProfile | null,
    initialized: false,
  }),
  getters: {
    authenticated: (state) => !!state.token,
    userId: (state) => state.user?.user_id ?? null,
  },
  actions: {
    _applyToken(token: string) {
      setToken(token)
      this.token = token
    },

    async loginByPassword(phone: string, password: string) {
      const data = await authApi.loginPhonePassword(phone, password)
      this._applyToken(data.access_token)
      await this.fetchProfile()
    },

    async loginByPhone(phone: string, code: string) {
      const data = await authApi.loginPhone(phone, code)
      this._applyToken(data.access_token)
      await this.fetchProfile()
    },

    async applyQrToken(token: string) {
      this._applyToken(token)
      await this.fetchProfile()
    },

    async fetchProfile() {
      const profile = await userApi.profile()
      this.user = profile
      this.initialized = true
      return profile
    },

    async updateProfile(payload: { nickname?: string; avatar?: string | null }) {
      const profile = await userApi.updateProfile(payload)
      this.user = profile
      return profile
    },

    reset() {
      clearToken()
      this.token = ''
      this.user = null
      this.initialized = false
    },

    logout() {
      this.reset()
    },
  },
})
