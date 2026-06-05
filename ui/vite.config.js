import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8000,
    host: '0.0.0.0', // Expose to local network
    proxy: {
      '/system': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/logs': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
});
