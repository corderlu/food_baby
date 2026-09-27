import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：本地开发时 Vite 把 /api 和 /uploads 代理过去，避免跨域
const BACKEND = process.env.VITE_BACKEND || 'http://127.0.0.1:8801'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 端口避让：8000/5173 常被其他项目占用
    port: 5273,
    host: true, // 让同局域网的手机能访问，真机预览用
    strictPort: false,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/uploads': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          vant: ['vant'],
        },
      },
    },
  },
})
