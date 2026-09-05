import { createHash, randomBytes } from "node:crypto";
import { mkdir, readFile, rm } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = process.env.E2E_API_URL ?? "http://127.0.0.1:18000";
const evidenceDir = process.env.E2E_EVIDENCE_DIR
  ? resolve(process.env.E2E_EVIDENCE_DIR)
  : resolve(process.cwd(), "../../output/e2e-local");
const screenshotDir = resolve(evidenceDir, "screenshots");
const expectedScreenshots = [
  "r2-chat.png",
  "r2-run-console.png",
  "r2-reload.png",
  "r2-scheduler.png",
  "r2-skill.png",
  "r2-development-task.png",
];
const forbiddenRoutePatterns = [
  "/api/v1/canvas",
  "/api/v1/creative-studio",
  "/api/v1/editor",
  "/media/generate",
  "/media/tasks",
  "/produce",
];

let username = "";
let password = "";
let token = "";
let tenantId = "";
let otherTenantId = "";
let checkpointId = "";
let packageId = "";
let developmentTaskId = "";
let developmentPatchHash = "";
let chatRunId = "";
let schedulerJobId = "";
let consoleErrors: string[] = [];
let pageErrors: string[] = [];
let forbiddenCalls: string[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ request }) => {
  await mkdir(screenshotDir, { recursive: true });
  await Promise.all(expectedScreenshots.map((name) => rm(resolve(screenshotDir, name), { force: true })));
  const tenantNonce = `${Date.now()}-${randomBytes(3).toString("hex")}`;
  tenantId = `r2-trial-${tenantNonce}`;
  otherTenantId = `r2-other-${tenantNonce}`;
  username = `r2-e2e-${Date.now()}-${randomBytes(3).toString("hex")}`;
  password = `R2-${randomBytes(24).toString("base64url")}!`;
  token = await register(request, username, password, tenantId);
});

test.beforeEach(async ({ page }) => {
  consoleErrors = [];
  pageErrors = [];
  forbiddenCalls = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = request.url();
    if (forbiddenRoutePatterns.some((pattern) => url.includes(pattern))) {
      forbiddenCalls.push(`${request.method()} ${url}`);
    }
  });
});

test.afterEach(async () => {
  expect(consoleErrors, "console.error count").toEqual([]);
  expect(pageErrors, "pageerror count").toEqual([]);
  expect(forbiddenCalls, "short-drama and media API calls").toEqual([]);
});

test("deep health 覆盖 PostgreSQL Redis Qdrant", async ({ page, request }) => {
  await login(page);
  const response = await request.get(`${API_BASE}/health/deep`);
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.status).toBe("healthy");
  expect(body.checks.database.status).toBe("healthy");
  expect(body.checks.redis.status).toBe("healthy");
  expect(body.checks.qdrant.status).toBe("healthy");
});

test("真实 Ollama 对话进入 Run Console 并可刷新恢复", async ({ page }) => {
  test.setTimeout(480_000);
  const chatGoal = "请只回复：R2-WEB-OLLAMA-OK";
  const historyRequests: string[] = [];
  const historyResponses: Array<{ path: string; status: number }> = [];
  const conversationHistoryPath = (url: string) => {
    const path = new URL(url).pathname;
    return /^\/api\/v1\/stream\/conversations\/[^/]+\/messages$/.test(path) ? path : "";
  };
  page.on("request", (request) => {
    const path = conversationHistoryPath(request.url());
    if (request.method() === "GET" && path) historyRequests.push(path);
  });
  page.on("response", (response) => {
    const path = conversationHistoryPath(response.url());
    if (response.request().method() === "GET" && path) {
      historyResponses.push({ path, status: response.status() });
    }
  });

  await login(page);
  await page.goto("/chat", { waitUntil: "networkidle" });
  await page.getByPlaceholder("描述一个任务...").fill(chatGoal);
  await page.getByRole("button", { name: "发送" }).click();
  const runLink = page.getByText("运行详情", { exact: true }).last();
  await expect(runLink).toBeVisible({ timeout: 360_000 });
  await page.waitForLoadState("networkidle");
  const conversationId = await page.evaluate(() => localStorage.getItem("xagent_conversation_id") ?? "");
  expect(conversationId).toMatch(/^[a-f0-9]{32}$/);
  const historyPath = `/api/v1/stream/conversations/${conversationId}/messages`;
  expect(
    historyRequests.filter((path) => path === historyPath),
    "new conversation history requests before the stream settled",
  ).toEqual([]);
  expect(
    historyResponses.filter((response) => response.status === 404),
    "conversation history 404 responses",
  ).toEqual([]);
  const runHref = await runLink.evaluate((element) =>
    element.closest("a")?.getAttribute("href") ?? "",
  );
  expect(runHref).toMatch(/^\/runs\/[a-f0-9_]+$/);

  const reloadHistory = page.waitForResponse((response) =>
    new URL(response.url()).pathname === historyPath &&
      response.request().method() === "GET",
  );
  const [reloadHistoryResponse] = await Promise.all([
    reloadHistory,
    page.reload({ waitUntil: "networkidle" }),
  ]);
  expect(reloadHistoryResponse.status()).toBe(200);
  await expect(page.getByRole("button", { name: chatGoal, exact: true }).first()).toBeVisible();
  await expect(page.getByText("R2-WEB-OLLAMA-OK", { exact: true }).last()).toBeVisible();

  await page.getByRole("link", { name: "新建对话", exact: true }).click();
  const sidebarConversation = page.getByRole("button", { name: chatGoal, exact: true }).first();
  await expect(sidebarConversation).toBeVisible();
  const sidebarHistory = page.waitForResponse((response) =>
    new URL(response.url()).pathname === historyPath &&
      response.request().method() === "GET",
  );
  await sidebarConversation.click();
  expect((await sidebarHistory).status()).toBe(200);
  await expect(page.getByText("R2-WEB-OLLAMA-OK", { exact: true }).last()).toBeVisible();
  expect(
    historyResponses.filter((response) => response.path === historyPath).map((response) => response.status),
  ).toEqual([200, 200]);
  await page.screenshot({ path: resolve(screenshotDir, "r2-chat.png"), fullPage: true });
  await page.goto(runHref, { waitUntil: "networkidle" });
  await expect(page.getByText("Run Console", { exact: true })).toBeVisible({ timeout: 30_000 });
  chatRunId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1) ?? "";
  expect(chatRunId).toMatch(/^[a-f0-9_]+$/);
  await expect(page.getByText(/checkpoint/i).first()).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: resolve(screenshotDir, "r2-run-console.png"), fullPage: true });

  const checkpoints = await page.request.get(`/api/v1/checkpoints?run_id=${encodeURIComponent(chatRunId)}`, {
    headers: authHeaders(),
  });
  expect(checkpoints.ok()).toBeTruthy();
  const checkpointBody = await checkpoints.json();
  expect(checkpointBody.total).toBeGreaterThan(0);
  checkpointId = checkpointBody.checkpoints[0].checkpoint_id;
  expect(checkpointId).toBeTruthy();

  const runDetail = await page.request.get(`/api/v1/runs/${encodeURIComponent(chatRunId)}`, {
    headers: authHeaders(),
  });
  expect(runDetail.ok()).toBeTruthy();
  const runBody = await runDetail.json();
  expect(JSON.stringify(runBody)).not.toContain("MockLLM");

  const runUrl = page.url();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page).toHaveURL(runUrl);
  await expect(page.getByText("Run Console", { exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(screenshotDir, "r2-reload.png"), fullPage: true });
});

test("调度任务运行 暂停并刷新后保持", async ({ page }) => {
  test.setTimeout(240_000);
  await login(page);
  await page.goto("/scheduler", { waitUntil: "networkidle" });
  const name = `R2 restart probe ${Date.now()}`;
  await page.getByPlaceholder("任务名称").fill(name);
  await page.getByPlaceholder("Agent 目标").fill("请只回复 R2-SCHEDULER-OK");
  const created = page.waitForResponse((response) =>
    response.url().includes("/api/v1/scheduler/jobs") && response.request().method() === "POST" && response.status() === 200,
  );
  await page.getByRole("button", { name: "创建" }).click();
  schedulerJobId = (await (await created).json()).job_id;
  expect(schedulerJobId).toMatch(/^[a-f0-9]{12}$/);
  await expect(page.getByText("调度任务已创建")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(schedulerJobId, { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByText(schedulerJobId, { exact: true }).click();

  const runNow = await page.request.post(`/api/v1/scheduler/jobs/${schedulerJobId}/run`, {
    data: { confirm_job_id: schedulerJobId },
    headers: authHeaders(),
  });
  expect(runNow.ok()).toBeTruthy();
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/scheduler/jobs/${schedulerJobId}/runs`, {
      headers: authHeaders(),
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    const run = body.runs?.find((item: { attempt: number }) => item.attempt === 1);
    return run?.status ?? "";
  }, { timeout: 180_000 }).toBe("succeeded");

  const runsResponse = await page.request.get(`/api/v1/scheduler/jobs/${schedulerJobId}/runs`, {
    headers: authHeaders(),
  });
  expect(runsResponse.ok()).toBeTruthy();
  const runsBody = await runsResponse.json();
  const completedRun = runsBody.runs?.find((item: { attempt: number }) => item.attempt === 1);
  expect(completedRun?.result?.trim()).toBe("R2-SCHEDULER-OK");
  expect(completedRun?.error ?? "").toBe("");

  const pause = await page.request.patch(`/api/v1/scheduler/jobs/${schedulerJobId}/toggle`, {
    data: { confirm_job_id: schedulerJobId, enabled: false },
    headers: authHeaders(),
  });
  expect(pause.ok()).toBeTruthy();
  expect((await pause.json()).enabled).toBe(false);

  const jobsResponse = await page.request.get("/api/v1/scheduler/jobs", { headers: authHeaders() });
  expect(jobsResponse.ok()).toBeTruthy();
  const jobsBody = await jobsResponse.json();
  const persistedJob = jobsBody.jobs?.find((job: { job_id: string }) => job.job_id === schedulerJobId);
  expect(persistedJob?.name).toBe(name);
  expect(persistedJob?.enabled).toBe(false);

  await page.reload({ waitUntil: "networkidle" });
  const persistedJobButton = page.getByRole("button").filter({ hasText: name }).first();
  await expect(persistedJobButton).toBeVisible({ timeout: 20_000 });
  await persistedJobButton.click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(page.getByText(schedulerJobId, { exact: true })).toBeVisible();
  await expect(page.getByText("已暂停").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "恢复", exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(screenshotDir, "r2-scheduler.png"), fullPage: true });
});

test("完整技能包导入后在 Web 可见", async ({ page }) => {
  const archive = process.env.E2E_SKILL_PACKAGE;
  if (!archive) {
    throw new Error("E2E_SKILL_PACKAGE is required");
  }
  await login(page);
  await page.goto("/settings?section=skills", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "导入 SKILL.md" }).click();
  const imported = page.waitForResponse((response) =>
    response.url().includes("/api/v1/skill-packages/import") && response.status() === 201,
  );
  await page.locator('input[type="file"][accept*=".zip"]').setInputFiles(archive);
  await page.getByRole("button", { name: "安全校验并导入 ZIP" }).click();
  const importedBody = await (await imported).json();
  expect(importedBody.imported).toBe(true);
  packageId = importedBody.package.package_id;
  expect(importedBody.package.manifest.files.map((file: { path: string }) => file.path).sort()).toEqual([
    "SKILL.md",
    "assets/badge.txt",
    "references/checklist.md",
    "scripts/verify.py",
  ]);
  await expect(page.getByText("R2 持久化验收技能")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("完整技能包", { exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(screenshotDir, "r2-skill.png"), fullPage: true });
});

test("开发任务产物可审查和下载", async ({ page }) => {
  test.setTimeout(660_000);
  await login(page);
  const parallel = await page.request.post("/api/v1/agents/parallel-run", {
    data: {
      tasks: [
        {
          goal: "必须调用 file_write 工具在当前工作区创建 R2_AGENT_RESULT.md，文件内容必须精确为 R2-DEVELOPMENT-TASK-OK（允许末尾换行），不得只用文字回答。",
          capabilities: ["file_write"],
        },
      ],
      coordinator_goal: "验证隔离开发任务结果",
      use_worktrees: true,
    },
    headers: authHeaders(),
    timeout: 600_000,
  });
  expect(parallel.ok()).toBeTruthy();
  const parallelBody = await parallel.json();
  const sub = parallelBody.sub_results?.[0];
  expect(sub?.status).toBe("succeeded");
  expect(sub?.error).toBe("");
  expect(sub?.steps).toBeGreaterThan(0);
  expect(sub?.isolated).toBe(true);
  expect(sub?.development_task_status).toBe("awaiting_review");
  expect(sub?.diff_stat).toContain("R2_AGENT_RESULT.md");
  expect(sub?.diff).toContain("R2-DEVELOPMENT-TASK-OK");
  developmentTaskId = sub.development_task_id;
  expect(developmentTaskId).toBeTruthy();

  const detail = await page.request.get(`/api/v1/development-tasks/${developmentTaskId}`, {
    headers: authHeaders(),
  });
  expect(detail.ok()).toBeTruthy();
  const detailBody = await detail.json();
  expect(detailBody.status).toBe("awaiting_review");
  expect(detailBody.base_commit).toMatch(/^[a-f0-9]{40}$/);
  expect(detailBody.result_commit).toMatch(/^[a-f0-9]{40}$/);
  expect(detailBody.result_commit).not.toBe(detailBody.base_commit);
  expect(detailBody.diff_stat).toContain("R2_AGENT_RESULT.md");

  const patchResponse = await page.request.get(`/api/v1/development-tasks/${developmentTaskId}/patch`, {
    headers: authHeaders(),
  });
  expect(patchResponse.ok()).toBeTruthy();
  const patch = (await patchResponse.json()).patch;
  expect(patch).toContain("R2-DEVELOPMENT-TASK-OK");
  developmentPatchHash = createHash("sha256").update(patch).digest("hex");

  await page.goto("/development-tasks", { waitUntil: "networkidle" });
  await page.getByText(developmentTaskId, { exact: false }).first().click();
  await expect(page.getByText("待审查").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("R2_AGENT_RESULT.md").first()).toBeVisible();
  await expect(page.getByText("R2-DEVELOPMENT-TASK-OK").first()).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 Patch", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`${developmentTaskId}.patch`);
  const downloadDir = resolve(evidenceDir, "downloads");
  await mkdir(downloadDir, { recursive: true });
  const downloadedPatchPath = resolve(downloadDir, download.suggestedFilename());
  await download.saveAs(downloadedPatchPath);
  const downloadedPatch = await readFile(downloadedPatchPath, "utf8");
  expect(downloadedPatch).toBe(patch);
  expect(createHash("sha256").update(downloadedPatch).digest("hex")).toBe(developmentPatchHash);
  await page.screenshot({ path: resolve(screenshotDir, "r2-development-task.png"), fullPage: true });
});

test("第二租户不能读取第一租户资源", async ({ page, request }) => {
  await login(page);
  expect(packageId, "package id from skill test").toBeTruthy();
  expect(checkpointId, "checkpoint id from chat test").toBeTruthy();
  expect(developmentTaskId, "development task id from artifact test").toBeTruthy();

  const otherUsername = `r2-isolation-${Date.now()}-${randomBytes(3).toString("hex")}`;
  const otherPassword = `R2-${randomBytes(24).toString("base64url")}!`;
  const otherToken = await register(request, otherUsername, otherPassword, otherTenantId);
  const headers = { Authorization: `Bearer ${otherToken}` };
  for (const path of [
    `/api/v1/skill-packages/${packageId}`,
    `/api/v1/checkpoints/${checkpointId}`,
    `/api/v1/development-tasks/${developmentTaskId}`,
  ]) {
    const response = await request.get(`${API_BASE}${path}`, { headers });
    expect([403, 404]).toContain(response.status());
  }
});

async function register(
  request: APIRequestContext,
  user: string,
  secret: string,
  tenantId: string,
): Promise<string> {
  const response = await request.post(`${API_BASE}/api/v1/auth/register`, {
    data: { username: user, password: secret, tenant_id: tenantId },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.tenant_id).toBe(tenantId);
  expect(body.access_token).toBeTruthy();
  return body.access_token;
}

async function login(page: Page) {
  if (!token) {
    throw new Error("R2 auth token was not initialized");
  }
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.evaluate((accessToken) => localStorage.setItem("xagent_token", accessToken), token);
}

function authHeaders() {
  return { Authorization: `Bearer ${token}` };
}

export const r2RunEvidence = {
  get checkpointId() {
    return checkpointId;
  },
  get packageId() {
    return packageId;
  },
  get developmentTaskId() {
    return developmentTaskId;
  },
  get developmentPatchHash() {
    return developmentPatchHash;
  },
  get chatRunId() {
    return chatRunId;
  },
  get schedulerJobId() {
    return schedulerJobId;
  },
};
