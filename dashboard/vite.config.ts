import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.OPS_DASHBOARD_API_PROXY_TARGET || 'http://127.0.0.1:9600'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 9700,
    proxy: {
      '/api': proxyTarget,
    },
  },
})
