import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.XAGENT_DEV_API_TARGET || "http://localhost:8000";
const wsTarget = apiTarget.replace(/^http/, "ws");

// 后端默认 http://localhost:8000；dev 用 Vite proxy 转发 /api 与 /ws
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        // SSE 长连接不能超时断开（Agent 任务可能跑 5+ 分钟）
        timeout: 0,
        proxyTimeout: 0,
      },
      "/ws": { target: wsTarget, ws: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
