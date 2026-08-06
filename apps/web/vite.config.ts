import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.XAGENT_DEV_API_TARGET || "http://localhost:8000";
const wsTarget = apiTarget.replace(/^http/, "ws");
const chunkPackages: Array<[string, string[]]> = [
  ["vendor", ["react", "react-dom", "react-router-dom"]],
  ["query", ["@tanstack/react-query", "zustand"]],
  ["ui", ["axios", "clsx"]],
  ["reactflow", ["reactflow", "@reactflow"]],
  ["markdown", ["react-markdown", "remark-gfm", "rehype-highlight", "highlight.js"]],
];

function manualChunks(moduleId: string): string | undefined {
  const normalized = moduleId.replaceAll("\\", "/");
  for (const [chunkName, packages] of chunkPackages) {
    if (packages.some((packageName) => normalized.includes(`/node_modules/${packageName}/`))) {
      return chunkName;
    }
  }
  return undefined;
}

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
    minify: "oxc",
    rollupOptions: {
      output: {
        // Rolldown 不再支持 Rollup 的对象形式，函数形式保留相同拆包边界。
        manualChunks,
        minify: process.env.NODE_ENV === "production"
          ? { compress: { dropConsole: true, dropDebugger: true }, mangle: true }
          : true,
      },
    },
    chunkSizeWarningLimit: 500,
  },
});
