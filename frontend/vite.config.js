import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // In dev (npm run dev), forward /api to the local Cloud backend
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,   // also proxy WebSocket upgrades
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
