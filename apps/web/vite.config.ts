/// <reference types="vitest" />
import { fileURLToPath, URL } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Dev proxy so the SPA talks to a running bbz-api. Host dev uses the
    // default; inside docker-compose set VITE_API_PROXY_TARGET=http://api:8000.
    proxy: (() => {
      const target = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000';
      return {
        '/api': { target, changeOrigin: true },
        '/health': { target, changeOrigin: true },
        '/cluster': { target, changeOrigin: true },
      };
    })(),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.ts'],
  },
});
