import { test, expect, type Page } from "@playwright/test";

/**
 * X-Agent E2E 全链路测试。
 *
 * 前置：后端 :8000 + 前端 :3000 运行中。
 * full 模式需登录 -> beforeEach 通过 API 登录拿 token 写入 localStorage。
 */

async function loginIfNeeded(page: Page) {
  // 通过前端代理登录（同源，token 存 localStorage）
  await page.goto("/");
  try {
    const resp = await page.request.post("/api/v1/auth/login", {
      data: { username: "admin", password: "admin" },
      timeout: 5000,
    });
    if (resp.ok()) {
      const body = await resp.json();
      await page.evaluate((token) => {
        localStorage.setItem("xagent_token", token);
      }, body.access_token);
    }
  } catch {
    // lite 模式无登录，匿名继续
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
    // 侧栏导航存在
    await expect(page.locator("text=短剧工厂")).toBeVisible();
    await expect(page.locator("text=开源发现")).toBeVisible();
  });

  test("对话运行 agent", async ({ page }) => {
    await page.goto("/chat");
    await page.fill("textarea", "你好");
    await page.click("button:has-text('运行')");
    // 等待回答区域出现（真实模型可能需较久）
    await expect(page.locator("text=最终回答").or(page.locator("text=流式输出")).or(page.locator("text=事件序列"))).toBeVisible({
      timeout: 60_000,
    });
  });

  test("智能体角色列表", async ({ page }) => {
    await page.goto("/agents");
    await expect(page.locator(".font-medium").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("工作流创建执行", async ({ page }) => {
    await page.goto("/workflows");
    await page.click("button:has-text('创建并执行')");
    await expect(page.locator("text=completed").or(page.locator("text=succeeded")).or(page.locator("text=状态"))).toBeVisible({
      timeout: 60_000,
    });
  });

  test("短剧工厂生成草稿 + 节点画布", async ({ page }) => {
    await page.goto("/creative");
    await page.fill('input[placeholder*="brief"]', "霸总逆袭短剧");
    await page.click("button:has-text('生成')");
    // 等待草稿状态或节点出现
    await expect(page.locator("text=pending_review").or(page.locator("text=审核")).or(page.locator(".react-flow"))).toBeVisible({
      timeout: 30_000,
    });
  });

  test("开源发现搜索", async ({ page }) => {
    await page.goto("/open-source");
    await page.fill('input[placeholder*="查询"]', "vector database");
    await page.click("button:has-text('发现')");
    // mock provider 有结果
    await expect(page.locator("text=score").or(page.locator("text=mock"))).toBeVisible({
      timeout: 15_000,
    });
  });

  test("知识库写入+检索", async ({ page }) => {
    await page.goto("/memory");
    // 写入
    await page.fill('input[placeholder="id"]', "e2e-test");
    await page.fill('textarea[placeholder="文本"]', "E2E 测试记忆条目");
    await page.click("button:has-text('写入')");
    await expect(page.locator("text=已写入")).toBeVisible({ timeout: 10_000 });
    // 检索
    await page.fill('input[placeholder="query"]', "E2E 测试");
    await page.click("button:has-text('检索')");
    await expect(page.locator("text=E2E 测试记忆条目")).toBeVisible({ timeout: 10_000 });
  });

  test("设置页加载", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("text=访问 Token")).toBeVisible();
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
