import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev proxy: the app calls same-origin `/api/*`, forwarded verbatim to the
// FastAPI backend on :8000 — which mounts its own routes under /api, so there
// is nothing to rewrite and dev and production address the API identically.
// Keeps the browser same-origin, so no CORS config is needed here (ADR-002).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
