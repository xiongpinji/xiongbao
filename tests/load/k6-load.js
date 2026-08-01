/**
 * X-Agent k6 负载测试脚本。
 *
 * 用法：
 *   k6 run tests/load/k6-load.js
 *   k6 run --env BASE_URL=http://staging:8000 tests/load/k6-load.js
 *
 * CI 集成：
 *   在 GitHub Actions 中通过 load-test job 自动运行。
 */

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

// 自定义指标
const errorRate = new Rate("errors");
const apiLatency = new Trend("api_latency", true);

// 配置
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  scenarios: {
    // 渐进加压
    ramp_up: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 10 },   // 预热
        { duration: "1m", target: 50 },    // 正常负载
        { duration: "30s", target: 100 },  // 峰值
        { duration: "30s", target: 0 },    // 冷却
      ],
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<200", "p(99)<500"],
    errors: ["rate<0.05"],
    api_latency: ["p(95)<300"],
  },
};

export default function () {
  group("健康检查", () => {
    const res = http.get(`${BASE_URL}/health`);
    check(res, {
      "health 200": (r) => r.status === 200,
      "health body": (r) => r.json("status") === "ok",
    });
    errorRate.add(res.status !== 200);
  });

  group("指标端点", () => {
    const res = http.get(`${BASE_URL}/metrics`);
    check(res, {
      "metrics 200": (r) => r.status === 200,
      "metrics prometheus": (r) => r.body.includes("xagent_"),
    });
    errorRate.add(res.status !== 200);
  });

  group("性能端点", () => {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/perf`);
    apiLatency.add(Date.now() - start);
    check(res, {
      "perf 200": (r) => r.status === 200,
    });
    errorRate.add(res.status !== 200);
  });

  group("API 版本", () => {
    const res = http.get(`${BASE_URL}/api/versions`);
    check(res, {
      "versions 200": (r) => r.status === 200,
      "has current": (r) => r.json("current") === "v1",
    });
    errorRate.add(res.status !== 200);
  });

  group("认证端点（无效凭据）", () => {
    const res = http.post(
      `${BASE_URL}/api/v1/auth/login`,
      JSON.stringify({ username: "k6_test", password: "invalid" }),
      { headers: { "Content-Type": "application/json" } }
    );
    check(res, {
      "auth reject": (r) => [401, 404, 422].includes(r.status),
    });
    // 401 不算错误
    errorRate.add(res.status >= 500);
  });

  sleep(0.1); // 100ms 间隔
}

export function handleSummary(data) {
  return {
    stdout: textSummary(data),
  };
}

function textSummary(data) {
  const metrics = data.metrics;
  const p95 = metrics.http_req_duration?.values?.["p(95)"] || 0;
  const p99 = metrics.http_req_duration?.values?.["p(99)"] || 0;
  const errs = metrics.errors?.values?.rate || 0;
  const rps = metrics.http_reqs?.values?.rate || 0;
  return `
╔══════════════════════════════════════╗
║     X-Agent Load Test Summary        ║
╠══════════════════════════════════════╣
║  RPS:       ${rps.toFixed(1).padStart(10)} req/s        ║
║  P95:       ${p95.toFixed(1).padStart(10)} ms           ║
║  P99:       ${p99.toFixed(1).padStart(10)} ms           ║
║  Errors:    ${(errs * 100).toFixed(2).padStart(9)}%            ║
╚══════════════════════════════════════╝
`;
}
