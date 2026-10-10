import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 纯 SPA 配置：开发服务器将 /tutor 与 /health 代理到 FastAPI 后端
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/tutor': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
