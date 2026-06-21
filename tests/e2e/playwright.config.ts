import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  timeout: 30_000,
  retries: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    // 前端地址（dev 模式 :3000 或 compose web :3000）
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium", channel: "chrome" } },
  ],
  // 可选：自动起后端（需 web dev server 运行）
  // webServer: { command: "npm run dev", port: 3000, reuseExistingServer: true },
});
