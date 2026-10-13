import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/tutor': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (_proxyReq, _req, res) => {
            const headers = res.headers || {};
            const contentType = headers['content-type'] || '';
            if (contentType.includes('text/event-stream')) {
              headers['x-accel-buffering'] = 'no';
              headers['cache-control'] = 'no-cache';
            }
          });
        },
      },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});