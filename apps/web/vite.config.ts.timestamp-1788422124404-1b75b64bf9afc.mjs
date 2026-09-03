// vite.config.ts
import { fileURLToPath, URL } from "node:url";
import vue from "file:///app/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import { defineConfig } from "file:///app/node_modules/vite/dist/node/index.js";
var __vite_injected_original_import_meta_url = "file:///app/vite.config.ts";
var vite_config_default = defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", __vite_injected_original_import_meta_url)) }
  },
  server: {
    port: 5173,
    // Vite 5.4+ blocks a Host header it does not recognise and answers with a
    // bare "Blocked request" page — which looks exactly like a broken build
    // (the compose stack is reached over localhost, 127.0.0.1, the edge proxy,
    // the LAN IP, host.docker.internal, …). This is the **dev convenience
    // server only** — production serves a static build behind Caddy — so accept
    // any host. Set VITE_ALLOWED_HOSTS (comma-separated) to restore the check.
    allowedHosts: process.env.VITE_ALLOWED_HOSTS ? process.env.VITE_ALLOWED_HOSTS.split(",").filter(Boolean) : true,
    // Dev proxy so the SPA talks to a running bbz-api. Host dev uses the
    // default; inside docker-compose set VITE_API_PROXY_TARGET=http://api:8000.
    proxy: (() => {
      const target = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";
      return {
        "/api": { target, changeOrigin: true },
        "/health": { target, changeOrigin: true },
        "/cluster": { target, changeOrigin: true }
      };
    })()
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.spec.ts"]
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvYXBwXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCIvYXBwL3ZpdGUuY29uZmlnLnRzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9hcHAvdml0ZS5jb25maWcudHNcIjsvLy8gPHJlZmVyZW5jZSB0eXBlcz1cInZpdGVzdFwiIC8+XG5pbXBvcnQgeyBmaWxlVVJMVG9QYXRoLCBVUkwgfSBmcm9tICdub2RlOnVybCc7XG5pbXBvcnQgdnVlIGZyb20gJ0B2aXRlanMvcGx1Z2luLXZ1ZSc7XG5pbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJztcblxuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgcGx1Z2luczogW3Z1ZSgpXSxcbiAgcmVzb2x2ZToge1xuICAgIGFsaWFzOiB7ICdAJzogZmlsZVVSTFRvUGF0aChuZXcgVVJMKCcuL3NyYycsIGltcG9ydC5tZXRhLnVybCkpIH0sXG4gIH0sXG4gIHNlcnZlcjoge1xuICAgIHBvcnQ6IDUxNzMsXG4gICAgLy8gVml0ZSA1LjQrIGJsb2NrcyBhIEhvc3QgaGVhZGVyIGl0IGRvZXMgbm90IHJlY29nbmlzZSBhbmQgYW5zd2VycyB3aXRoIGFcbiAgICAvLyBiYXJlIFwiQmxvY2tlZCByZXF1ZXN0XCIgcGFnZSBcdTIwMTQgd2hpY2ggbG9va3MgZXhhY3RseSBsaWtlIGEgYnJva2VuIGJ1aWxkXG4gICAgLy8gKHRoZSBjb21wb3NlIHN0YWNrIGlzIHJlYWNoZWQgb3ZlciBsb2NhbGhvc3QsIDEyNy4wLjAuMSwgdGhlIGVkZ2UgcHJveHksXG4gICAgLy8gdGhlIExBTiBJUCwgaG9zdC5kb2NrZXIuaW50ZXJuYWwsIFx1MjAyNikuIFRoaXMgaXMgdGhlICoqZGV2IGNvbnZlbmllbmNlXG4gICAgLy8gc2VydmVyIG9ubHkqKiBcdTIwMTQgcHJvZHVjdGlvbiBzZXJ2ZXMgYSBzdGF0aWMgYnVpbGQgYmVoaW5kIENhZGR5IFx1MjAxNCBzbyBhY2NlcHRcbiAgICAvLyBhbnkgaG9zdC4gU2V0IFZJVEVfQUxMT1dFRF9IT1NUUyAoY29tbWEtc2VwYXJhdGVkKSB0byByZXN0b3JlIHRoZSBjaGVjay5cbiAgICBhbGxvd2VkSG9zdHM6IHByb2Nlc3MuZW52LlZJVEVfQUxMT1dFRF9IT1NUU1xuICAgICAgPyBwcm9jZXNzLmVudi5WSVRFX0FMTE9XRURfSE9TVFMuc3BsaXQoJywnKS5maWx0ZXIoQm9vbGVhbilcbiAgICAgIDogdHJ1ZSxcbiAgICAvLyBEZXYgcHJveHkgc28gdGhlIFNQQSB0YWxrcyB0byBhIHJ1bm5pbmcgYmJ6LWFwaS4gSG9zdCBkZXYgdXNlcyB0aGVcbiAgICAvLyBkZWZhdWx0OyBpbnNpZGUgZG9ja2VyLWNvbXBvc2Ugc2V0IFZJVEVfQVBJX1BST1hZX1RBUkdFVD1odHRwOi8vYXBpOjgwMDAuXG4gICAgcHJveHk6ICgoKSA9PiB7XG4gICAgICBjb25zdCB0YXJnZXQgPSBwcm9jZXNzLmVudi5WSVRFX0FQSV9QUk9YWV9UQVJHRVQgPz8gJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCc7XG4gICAgICByZXR1cm4ge1xuICAgICAgICAnL2FwaSc6IHsgdGFyZ2V0LCBjaGFuZ2VPcmlnaW46IHRydWUgfSxcbiAgICAgICAgJy9oZWFsdGgnOiB7IHRhcmdldCwgY2hhbmdlT3JpZ2luOiB0cnVlIH0sXG4gICAgICAgICcvY2x1c3Rlcic6IHsgdGFyZ2V0LCBjaGFuZ2VPcmlnaW46IHRydWUgfSxcbiAgICAgIH07XG4gICAgfSkoKSxcbiAgfSxcbiAgdGVzdDoge1xuICAgIGVudmlyb25tZW50OiAnanNkb20nLFxuICAgIGdsb2JhbHM6IHRydWUsXG4gICAgaW5jbHVkZTogWyd0ZXN0cy8qKi8qLnNwZWMudHMnXSxcbiAgfSxcbn0pO1xuIl0sCiAgIm1hcHBpbmdzIjogIjtBQUNBLFNBQVMsZUFBZSxXQUFXO0FBQ25DLE9BQU8sU0FBUztBQUNoQixTQUFTLG9CQUFvQjtBQUhtRixJQUFNLDJDQUEyQztBQUtqSyxJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsSUFBSSxDQUFDO0FBQUEsRUFDZixTQUFTO0FBQUEsSUFDUCxPQUFPLEVBQUUsS0FBSyxjQUFjLElBQUksSUFBSSxTQUFTLHdDQUFlLENBQUMsRUFBRTtBQUFBLEVBQ2pFO0FBQUEsRUFDQSxRQUFRO0FBQUEsSUFDTixNQUFNO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUEsSUFPTixjQUFjLFFBQVEsSUFBSSxxQkFDdEIsUUFBUSxJQUFJLG1CQUFtQixNQUFNLEdBQUcsRUFBRSxPQUFPLE9BQU8sSUFDeEQ7QUFBQTtBQUFBO0FBQUEsSUFHSixRQUFRLE1BQU07QUFDWixZQUFNLFNBQVMsUUFBUSxJQUFJLHlCQUF5QjtBQUNwRCxhQUFPO0FBQUEsUUFDTCxRQUFRLEVBQUUsUUFBUSxjQUFjLEtBQUs7QUFBQSxRQUNyQyxXQUFXLEVBQUUsUUFBUSxjQUFjLEtBQUs7QUFBQSxRQUN4QyxZQUFZLEVBQUUsUUFBUSxjQUFjLEtBQUs7QUFBQSxNQUMzQztBQUFBLElBQ0YsR0FBRztBQUFBLEVBQ0w7QUFBQSxFQUNBLE1BQU07QUFBQSxJQUNKLGFBQWE7QUFBQSxJQUNiLFNBQVM7QUFBQSxJQUNULFNBQVMsQ0FBQyxvQkFBb0I7QUFBQSxFQUNoQztBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
