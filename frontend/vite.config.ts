import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Tailwind v4 is configured through this plugin plus the `@theme` block in
// src/styles/index.css. There is deliberately no tailwind.config.js - v4 removed
// it, and adding one back would silently do nothing.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // Configurable so a developer whose port 8000 is already taken can point
  // elsewhere without editing tracked files: set VITE_API_PROXY_TARGET in .env.
  const apiTarget = env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: Number(env.VITE_PORT ?? 5173),
      // Proxying keeps the browser same-origin in development, so CORS never
      // enters the picture locally.
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
      },
    },
  }
})
