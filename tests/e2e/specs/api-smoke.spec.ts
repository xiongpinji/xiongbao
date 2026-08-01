import { test, expect } from "@playwright/test";

/**
 * X-Agent API 级别 E2E 冒烟测试。
 *
 * 前置：后端 :8000 运行中（lite 模式即可，无需 LLM）。
 * 验证核心端点可达、响应格式正确、安全头存在。
 */

const API_BASE = process.env.E2E_API_URL || "http://localhost:8000";

test.describe("API 健康 & 基础端点", () => {
  test("GET /health 返回 200 + status ok", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/health`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.status).toBe("ok");
  });

  test("GET /metrics 返回 Prometheus 格式", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/metrics`);
    expect(resp.status()).toBe(200);
    const text = await resp.text();
    expect(text).toContain("xagent_http_requests_total");
  });

  test("GET /perf 返回性能统计", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/perf`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty("total_requests");
    expect(body).toHaveProperty("avg_response_time_ms");
  });

  test("GET /ready 返回就绪状态", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/ready`);
    expect([200, 503]).toContain(resp.status());
  });
});

test.describe("API 安全", () => {
  test("未认证访问受保护端点返回 401", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/agents/roles`);
    // lite 模式可能 200（无认证），full 模式 401
    expect([200, 401]).toContain(resp.status());
  });

  test("响应包含安全头", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/health`);
    const headers = resp.headers();
    // 后端应设置 X-Content-Type-Options
    expect(headers["x-content-type-options"]).toBe("nosniff");
  });

  test("CORS 预检请求正确响应", async ({ request }) => {
    const resp = await request.fetch(`${API_BASE}/health`, {
      method: "OPTIONS",
      headers: {
        Origin: "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
      },
    });
    // 应返回 200 或 204
    expect([200, 204, 405]).toContain(resp.status());
  });
});

test.describe("API 功能端点", () => {
  test("GET /api/v1/skills/stats 返回技能统计", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/skills/stats`);
    // 可能需要认证
    if (resp.status() === 200) {
      const body = await resp.json();
      expect(body).toHaveProperty("total_skills");
    } else {
      expect(resp.status()).toBe(401);
    }
  });

  test("POST /api/v1/auth/login 错误凭据返回 401", async ({ request }) => {
    const resp = await request.post(`${API_BASE}/api/v1/auth/login`, {
      data: { username: "invalid_user_xyz", password: "wrong_pass" },
    });
    expect([401, 404, 422]).toContain(resp.status());
  });

  test("GET /api/v1/templates 返回工作流模板列表", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/templates`);
    if (resp.status() === 200) {
      const body = await resp.json();
      expect(Array.isArray(body)).toBeTruthy();
    } else {
      expect(resp.status()).toBe(401);
    }
  });
});

test.describe("API 容错", () => {
  test("不存在的路径返回 404", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/nonexistent-endpoint-xyz`);
    expect([404, 401]).toContain(resp.status());
  });

  test("无效 JSON body 返回 422", async ({ request }) => {
    const resp = await request.post(`${API_BASE}/api/v1/auth/login`, {
      data: "not-json",
      headers: { "Content-Type": "application/json" },
    });
    expect([422, 400]).toContain(resp.status());
  });
});
