import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api/': {
          target: 'http://127.0.0.1:8000',
          rewrite: path => path.slice('/api'.length),
        },
      },
      allowedHosts: env.NGROK_HOST ? [env.NGROK_HOST] : [],
    },
  }
})
