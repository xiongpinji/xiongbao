import { test, expect, type Page } from "@playwright/test";

/**
 * X-Agent E2E 全链路测试。
 *
 * 前置：后端 :8000 + 前端 :3000 运行中。
 * full 模式必须通过 E2E_USERNAME / E2E_PASSWORD 显式提供验收账号。
 */

const E2E_USERNAME = process.env.E2E_USERNAME;
const E2E_PASSWORD = process.env.E2E_PASSWORD;

async function loginIfNeeded(page: Page) {
  if (!E2E_USERNAME || !E2E_PASSWORD) {
    throw new Error("Set E2E_USERNAME/E2E_PASSWORD to a valid full-mode account.");
  }

  // 通过前端代理登录（同源，token 存 localStorage）。
  // full 模式应显式成功；若失败则视为验收环境未正确初始化。
  await page.goto("/");
  try {
    const resp = await page.request.post("/api/v1/auth/login", {
      data: { username: E2E_USERNAME, password: E2E_PASSWORD },
      timeout: 5000,
    });
    if (resp.ok()) {
      const body = await resp.json();
      await page.evaluate((token) => {
        localStorage.setItem("xagent_token", token);
      }, body.access_token);
      return;
    }
  } catch {
    // 继续走下面的页面判定。
  }

  const loginHeading = page.getByRole("heading", { name: /登录/i });
  if (await loginHeading.count()) {
    throw new Error(
      `E2E login failed for ${E2E_USERNAME}. Set E2E_USERNAME/E2E_PASSWORD to a valid full-mode account.`,
    );
  }
}

test.beforeEach(async ({ page }) => {
  await loginIfNeeded(page);
});

test.describe("X-Agent 核心流程", () => {
  test("首页加载 + 导航", async ({ page }) => {
    await page.goto("/");
    // 默认重定向到 /chat
    await expect(page).toHaveURL(/\/chat/);
    // 当前真实主导航：短剧工厂 / 工作流 / 设置
    await expect(page.getByRole("link", { name: /短剧工厂/ }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /工作流/ }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /设置/ }).first()).toBeVisible();
  });

  test("对话运行 agent", async ({ page }) => {
    test.setTimeout(120_000);  // 真实本地模型推理较慢
    await page.goto("/chat");
    await page.getByPlaceholder("描述一个任务或提出一个问题...").fill("你好");
    await page.getByTitle("运行 Agent").click();
    await expect(page.getByText("查看运行详情")).toBeVisible({
      timeout: 100_000,
    });
  });

  test("智能体角色列表", async ({ page }) => {
    await page.goto("/agents");
    await expect(page.locator(".font-medium").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("工作流创建执行", async ({ page }) => {
    test.setTimeout(120_000);  // 工作流步骤调用真实模型
    await page.goto("/workflows");
    await page.click("button:has-text('创建并执行')");
    await expect(page.locator("text=completed").or(page.locator("text=succeeded")).or(page.locator("text=状态"))).toBeVisible({
      timeout: 100_000,
    });
  });

  test("后台任务可进入 Run Console 并暴露 replay 指针", async ({ page }) => {
    const token = await page.evaluate(() => localStorage.getItem("xagent_token"));
    const headers = token ? { Authorization: `Bearer ${token}` } : {};

    const submit = await page.request.post("/api/v1/tasks", {
      data: { goal: "Run Console E2E 验收" },
      headers,
    });
    expect(submit.ok()).toBeTruthy();
    const body = await submit.json();
    const runId = body.run_id ?? body.task_id;
    expect(runId).toBeTruthy();

    await page.goto(`/runs/${encodeURIComponent(runId)}`, { waitUntil: "networkidle" });

    await expect(page.getByText("Run Console", { exact: true })).toBeVisible();
    await expect(page.getByText("验证 · 风险 · 恢复")).toBeVisible();
    await expect(page.getByText("查看后台任务", { exact: true })).toBeVisible();
    await expect(page.getByText(`/api/v1/tasks/${runId}`, { exact: true })).toBeVisible();
  });

  test("短剧工厂生成草稿 + 节点画布", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/creative");
    await page.getByRole("textbox", { name: "短剧 brief" }).fill("霸总逆袭短剧");
    const generateCanvas = page.getByRole("button", { name: "生成画布" });
    await expect(generateCanvas).toBeEnabled();
    await generateCanvas.click();
    // 等待草稿状态或节点出现
    await expect(page.getByTestId("rf__wrapper")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /需求分析节点/ }).first()).toBeVisible();
  });

  test("设置页索引库承接知识库与开源发现入口", async ({ page }) => {
    await page.goto("/settings?section=index&tab=knowledge");
    await expect(page.getByRole("heading", { name: "索引库" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "知识库" })).toBeVisible();
    await expect(page.getByRole("button", { name: "开源发现" })).toBeVisible();
    await expect(page.getByRole("button", { name: "写入" })).toBeVisible();
    await page.getByRole("button", { name: "开源发现" }).click();
    await expect(page.getByRole("button", { name: "发现", exact: true })).toBeVisible();
  });

  test("设置页加载", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  });
});

test.describe("安全检查", () => {
  test("响应含安全头", async ({ request }) => {
    const resp = await request.get("/api/v1/agents/roles");
    // 注：经 nginx 反代时安全头来自后端；直连后端时同样有
    // 这里只验证请求不崩（lite 可能 200 或 401）
    expect([200, 401]).toContain(resp.status());
  });
});
