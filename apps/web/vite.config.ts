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
    // Vite 5.4+ blocks a Host header it does not recognise and answers with a
    // bare "Blocked request" page — which looks exactly like a broken build
    // (the compose stack is reached over localhost, 127.0.0.1, the edge proxy,
    // the LAN IP, host.docker.internal, …). This is the **dev convenience
    // server only** — production serves a static build behind Caddy — so accept
    // any host. Set VITE_ALLOWED_HOSTS (comma-separated) to restore the check.
    allowedHosts: process.env.VITE_ALLOWED_HOSTS
      ? process.env.VITE_ALLOWED_HOSTS.split(',').filter(Boolean)
      : true,
    // Dev proxy so the SPA talks to a running bbz-api. Host dev uses the
    // default; inside docker-compose set VITE_API_PROXY_TARGET=http://api:8000.
    // `changeOrigin: false` keeps the browser's Host header on the proxied
    // request, so the API sees the SPA and itself as the *same origin* (as it
    // does in production behind Caddy) and the CSRF origin check (E23-05) passes
    // for whatever hostname the operator used.
    proxy: (() => {
      const target = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000';
      const opts = { target, changeOrigin: false };
      return { '/api': opts, '/health': opts, '/cluster': opts, '/ws': { ...opts, ws: true } };
    })(),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.ts'],
    setupFiles: ['tests/setup.ts'],
  },
});
