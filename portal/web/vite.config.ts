import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// em desenvolvimento a API Flask do portal roda na 8096
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8096', '/health': 'http://localhost:8096' } },
})
