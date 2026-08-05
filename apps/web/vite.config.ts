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
    sourcemap: false,
    target: "es2020",
    // esbuild 压缩：零额外依赖（terser 未安装会导致构建失败）且快 10x+
    minify: "esbuild",
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query", "zustand"],
          ui: ["axios", "clsx"],
          // 画布重型依赖：仅短剧/工作流页面懒加载时拉取
          reactflow: ["reactflow"],
          // Markdown 渲染栈：仅聊天消息需要
          markdown: ["react-markdown", "remark-gfm", "rehype-highlight", "highlight.js"],
        },
      },
    },
    chunkSizeWarningLimit: 500,
  },
  esbuild: {
    // 生产构建移除 console/debugger（等价于原 terser 配置）
    drop: process.env.NODE_ENV === "production" ? ["console", "debugger"] : [],
  },
});
