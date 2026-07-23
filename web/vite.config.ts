import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev proxy: the app calls same-origin `/api/*`, forwarded to the FastAPI
// backend on :8000 (stripping the `/api` prefix). Keeps the browser
// same-origin, so no CORS config on the backend (ADR-002: zero backend change).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
