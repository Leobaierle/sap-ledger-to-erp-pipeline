import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  // em desenvolvimento a API Flask roda na 8090
  server: { proxy: { '/api': 'http://localhost:8090', '/health': 'http://localhost:8090' } },
})
