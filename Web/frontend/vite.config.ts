import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const devApiTarget = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
  host: '0.0.0.0',
  allowedHosts: true,
  port: 5173,
  proxy: {
    '/api': {
      target: devApiTarget,
      changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/echarts/') || id.includes('\\echarts\\')) return 'charts'
          if (id.includes('/element-plus/') || id.includes('\\element-plus\\')) return 'element'
          if (/node_modules[\\/](vue|vue-router|pinia)[\\/]/.test(id)) return 'vue'
          return 'vendor'
        },
      },
    },
  },
})
