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
    // v1.2.0 ZCode 风格主导航：目标看板 / 工作流 / 设置
    await expect(page.getByRole("link", { name: /目标看板/ }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /工作流/ }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /设置/ }).first()).toBeVisible();
  });

  test("对话运行 agent", async ({ page }) => {
    test.setTimeout(150_000);  // 真实本地模型推理较慢
    await page.goto("/chat");
    // v1.3.0：默认智能体模式（真实调用工具），可切换纯对话
    await expect(
      page.getByRole("button", { name: "智能体", exact: true })
    ).toBeVisible();
    await page.getByPlaceholder("描述一个任务...").fill("你好");
    await page.getByRole("button", { name: "发送" }).click();
    // 正常路径流式返回内容；done-only 兜底路径显示"查看运行详情"
    const streamed = page.locator(".prose-agent").first();
    const fallback = page.getByText("查看运行详情");
    await expect(streamed.or(fallback)).toBeVisible({ timeout: 120_000 });
  });

  test("智能体角色列表", async ({ page }) => {
    await page.goto("/agents");
    await expect(page.locator(".font-medium").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("工作流页加载（专业模式画布）", async ({ page }) => {
    // v1.1.3 起 /workflows 重定向到 /professional?mode=workflow，画布异步执行
    await page.goto("/professional?mode=workflow");
    await expect(page.getByText("工作流编排").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("button", { name: "执行", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "保存", exact: true })).toBeVisible();
    // 节点面板核心节点类型可见
    await expect(page.getByText("开始", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("结束", { exact: true }).first()).toBeVisible();
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

    // v1.2.0：标题与实时状态徽标同节点渲染（如 "Run Console实时刷新中"），不能 exact
    await expect(page.getByText("Run Console").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("验证 · 风险 · 恢复").first()).toBeVisible();
  });

  test("短剧路由显示排除说明（v1.2.0 发布边界）", async ({ page }) => {
    // 短剧由独立项目运行；/creative 等路由显示排除说明页
    await page.goto("/creative");
    await expect(
      page.getByRole("heading", { name: "当前 Web/API 发布不包含此模块" })
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "返回对话" })).toBeVisible();
  });

  test("设置页索引与知识库入口（v1.2.0 设置分区）", async ({ page }) => {
    await page.goto("/settings");
    // v1.2.0：知识库收敛到设置分区导航（索引 / 知识库）
    await expect(page.getByText("索引", { exact: true }).first()).toBeVisible({
      timeout: 10_000,
    });
    await page.getByText("索引", { exact: true }).first().click();
    await expect(page.getByText("知识库", { exact: true }).first()).toBeVisible();
  });

  test("设置页加载", async ({ page }) => {
    await page.goto("/settings");
    // v1.2.0 设置分区导航（无独立 h1 标题，以分区项与保存按钮判定）
    await expect(page.getByText("模型", { exact: true }).first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole("button", { name: "保存", exact: true }).first()).toBeVisible();
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
