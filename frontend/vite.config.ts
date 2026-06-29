import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBaseUrl = env.VITE_API_BASE_URL || '/api'
  // If VITE_API_BASE_URL is a full URL (e.g. http://localhost:8000/api),
  // extract the origin as the proxy target.
  const proxyTarget = apiBaseUrl.startsWith('http')
    ? new URL(apiBaseUrl).origin
    : 'http://localhost:8000'

  return {
    plugins: [
      vue(),
      AutoImport({ resolvers: [ElementPlusResolver()] }),
      Components({ resolvers: [ElementPlusResolver()] }),
    ],
    resolve: {
      alias: { '@': '/src' },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: proxyTarget.replace(/^http/, 'ws'),
          ws: true,
        },
      },
    },
  }
})
