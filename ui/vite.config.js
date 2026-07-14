import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0', // Expose to local network
    proxy: {
      '/system': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/logs': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/api': {
        target: 'http://146.190.84.136:8080',
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            proxyReq.removeHeader('Origin');
          });
        }
      }
    }
  }
});
