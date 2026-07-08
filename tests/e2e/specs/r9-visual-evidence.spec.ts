import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const repoRoot = resolve(process.cwd(), "../..");
const evidenceDir = resolve(repoRoot, "docs/coordination/reports/evidence/r9-key-pages");

const username = process.env.E2E_USERNAME;
const password = process.env.E2E_PASSWORD;

function evidencePath(fileName: string) {
  return resolve(evidenceDir, fileName);
}

async function login(page: Page) {
  if (!username || !password) {
    throw new Error("Set E2E_USERNAME/E2E_PASSWORD to a valid full-mode account.");
  }

  const response = await page.request.post("/api/v1/auth/login", {
    data: { username, password },
    timeout: 5_000,
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  await page.goto("/login");
  await page.evaluate((token) => localStorage.setItem("xagent_token", token), body.access_token);
}

test.beforeAll(async () => {
  await mkdir(evidenceDir, { recursive: true });
});

test("R9 key page visual evidence", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });

  await page.goto("/login", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "熊宝智能体系统" })).toBeVisible();
  await page.screenshot({ path: evidencePath("01-login.png"), fullPage: true });

  await login(page);

  await page.goto("/chat", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "对话" })).toBeVisible();
  await expect(page.getByText("今天想要构建什么？")).toBeVisible();
  await page.screenshot({ path: evidencePath("02-chat-workbench.png"), fullPage: true });

  await page.goto("/professional?mode=workflow", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "工作流" })).toBeVisible();
  await expect(page.getByRole("button", { name: /创建并执行/ })).toBeVisible();
  await page.screenshot({ path: evidencePath("03-workflow.png"), fullPage: true });

  const token = await page.evaluate(() => localStorage.getItem("xagent_token"));
  const submit = await page.request.post("/api/v1/tasks", {
    data: { goal: "R9 Run Console visual evidence" },
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  expect(submit.ok()).toBeTruthy();
  const task = await submit.json();
  const runId = task.run_id ?? task.task_id;
  expect(runId).toBeTruthy();

  await page.goto(`/runs/${encodeURIComponent(runId)}`, { waitUntil: "networkidle" });
  await expect(page.getByText("Run Console", { exact: true })).toBeVisible();
  await expect(page.getByText("验证 · 风险 · 恢复")).toBeVisible();
  await page.screenshot({ path: evidencePath("04-run-console.png"), fullPage: true });

  await page.goto("/settings?section=index&tab=knowledge", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "索引库" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "知识库" })).toBeVisible();
  await expect(page.getByRole("button", { name: "开源发现" })).toBeVisible();
  await page.screenshot({ path: evidencePath("05-settings-index.png"), fullPage: true });
});
