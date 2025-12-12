import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/city': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/building': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/troop': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/movement': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/alliance': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/message': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ranking': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/report': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/protection': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/premium': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/chat': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/notification': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/event': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/season': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/quest': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/wiki': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/public-api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/shop': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/map': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/theme': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/admin': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/hero': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/adventure': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/market': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/forum': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/worlds': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    }
  }
});
