import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  const response = await page.request.post("/api/v1/auth/login", {
    data: { username: "admin", password: "admin" },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  await page.goto("/");
  await page.evaluate((token) => localStorage.setItem("xagent_token", token), body.access_token);
}

test("Creative Studio canvas smoke", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (text.includes("Failed to load resource") && text.includes("404")) return;
    consoleErrors.push(text);
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await login(page);
  await page.goto("/creative", { waitUntil: "networkidle" });

  await expect(page.getByText("短剧工厂自由画布")).toBeVisible();
  await page.locator('input:not([type="file"]):visible').first().fill("霸总逆袭短剧");
  await page.getByRole("button", { name: "生成画布" }).click();

  await expect(page.locator(".react-flow")).toBeVisible({ timeout: 30_000 });
  await expect.poll(async () => page.locator(".react-flow__node").count(), {
    timeout: 30_000,
  }).toBeGreaterThan(0);

  await page.getByRole("button", { name: "运行画布" }).click();
  await expect(page.getByText(/工作流|运行|审核|pending|awaiting|completed|failed/).first()).toBeVisible({
    timeout: 30_000,
  });

  expect(consoleErrors).toEqual([]);
});

test("Canvas batch media task can be polled", async ({ page }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem("xagent_token"));
  const headers = { Authorization: `Bearer ${token}` };

  const canvasResponse = await page.request.post("/api/v1/canvas", {
    data: { title: "E2E media", brief: "" },
    headers,
  });
  expect(canvasResponse.ok()).toBeTruthy();
  const canvas = await canvasResponse.json();

  const addResponse = await page.request.post(`/api/v1/canvas/${canvas.canvas_id}/nodes`, {
    data: { node_type: "关键帧", title: "关键帧" },
    headers,
  });
  expect(addResponse.ok()).toBeTruthy();
  const node = (await addResponse.json()).nodes.at(-1);

  const patchResponse = await page.request.patch(
    `/api/v1/canvas/${canvas.canvas_id}/nodes/${node.node_id}`,
    { data: { settings: { prompt: "E2E keyframe", resolution: "1024x1024" } }, headers },
  );
  expect(patchResponse.ok()).toBeTruthy();

  const batchResponse = await page.request.post(`/api/v1/canvas/${canvas.canvas_id}/batch-generate`, {
    data: { node_types: ["关键帧"] },
    headers,
  });
  expect(batchResponse.ok()).toBeTruthy();
  const batch = await batchResponse.json();
  const taskId = batch.results[0]?.task_id;
  expect(taskId).toBeTruthy();

  const pollResponse = await page.request.get(`/api/v1/creative-studio/media/tasks/${taskId}`, { headers });
  expect(pollResponse.ok()).toBeTruthy();
  const task = await pollResponse.json();
  expect(task.status).toBe("succeeded");
});

test("Creative Run Console exposes runtime recovery panel", async ({ page }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem("xagent_token"));
  const headers = { Authorization: `Bearer ${token}` };

  const response = await page.request.post("/api/v1/creative-studio/produce", {
    data: { brief: "Run Console Creative Smoke", with_video: false },
    headers,
  });
  expect(response.ok()).toBeTruthy();
  const result = await response.json();
  const runId = result.run_id ?? result.task_id ?? result.storyboard_id;
  expect(runId).toBeTruthy();

  await page.goto(`/runs/${encodeURIComponent(runId)}`, { waitUntil: "networkidle" });

  await expect(page.getByText("Run Console", { exact: true })).toBeVisible();
  await expect(page.getByText("验证 · 风险 · 恢复")).toBeVisible();
  await expect(page.getByText("Replay", { exact: true })).toBeVisible();
});
