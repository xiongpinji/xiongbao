# 测试指南

X-Agent 的测试分四层，从快到慢、从单元到端到端。

## 1. 单元 + 集成测试（pytest）

```bash
cd apps/api
pip install -e ".[dev]"
pytest -q                    # 94 个测试，<10s
ruff check xagent tests      # lint
```

覆盖：鉴权/JWT、RBAC、越权回归、租户隔离、orchestration、工作流补偿/审批/回放、
审计链篡改检测、计费配额、DB 持久化迁移、SSE 流、metrics、限流、安全头、Worker、
用户注册/改密、对象存储、短剧 LLM 编排、开源发现评分。

## 2. 安全自动化扫描

```bash
# 先启动后端
xagent serve  # 或 docker run

python tests/security/scan.py --host http://localhost:8000
```

检查项（全部通过 = PASS）：
- 健康探针无鉴权（豁免）
- 安全响应头（X-Content-Type-Options / X-Frame-Options）
- 业务端点鉴权（full 模式 401）
- 跨租户头注入防护（X-Tenant-Id 不一致 → 403）
- 租户记忆隔离（A 的数据 B 检索不到）
- SQL 注入防护（参数化）
- 限流触发（429）

## 3. 负载测试（Locust）

```bash
pip install locust
# 启动后端后
locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --headless -u 50 -r 5 -t 60s
```

模拟：登录 → 角色列表 → agent 运行 → 记忆检索 → 开源发现 → 短剧草稿。
关注：P95 延迟、错误率、429 比例。

## 4. E2E 测试（Playwright）

```bash
cd tests/e2e
npm install
npx playwright install chromium

# 前提：前端 dev（:3000）+ 后端（:8000）运行中
npm test                     # 无头
npm run test:headed          # 有头
```

覆盖全链路：页面加载 → 对话 → 智能体 → 工作流 → 短剧工厂(React Flow) →
开源发现 → 知识库写入检索 → 设置。

## 5. 三链路冒烟

```bash
xagent smoke   # LLM 调用 → trace → 向量读写
```

## 6. 执行 agent 验证

```bash
python scripts/verify_exec_agents.py   # 浏览器/桌面/编码 stub 降级验证
python scripts/verify_langfuse.py       # Langfuse trace（需配置 key）
```
