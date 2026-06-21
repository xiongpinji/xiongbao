import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 后端默认 http://localhost:8000；dev 用 Vite proxy 转发 /api 与 /ws
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
