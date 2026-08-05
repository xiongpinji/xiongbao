# 平台 MCP Server：把 X-Agent 暴露给外部 Agent（V3-4）

> 对标 Codex CLI 的 MCP 双向能力。Claude Code / Codex / Cursor 等外部 agent
> 可以把 X-Agent 作为 MCP 工具源直接调用：跑任务、代码评审、技能匹配、技能导入。

## 暴露工具

| 工具 | 说明 | 关键参数 |
|---|---|---|
| `xagent_run` | 跑一次 agent 任务（内置编排循环），返回最终回答 | `goal`, `role?` |
| `xagent_code_review` | 逻辑/安全/规范三维并行评审 | `diff` 或 `repo`+`base`(+`head`) |
| `xagent_skill_match` | 技能库匹配 + prompt 注入文本 | `goal` |
| `xagent_skill_import` | SKILL.md（agentskills.io）导入，**强制质量门禁** | `content`, `origin?` |

## 传输模式

### 1. stdio（默认，同机宿主拉起）

外部 agent 的配置示例（Claude Code `.mcp.json` / Codex `config.toml` 语义相同）：

```json
{
  "mcpServers": {
    "xagent-platform": {
      "command": "python",
      "args": ["-m", "xagent.adapters.mcp.platform_server"],
      "cwd": "<repo>/apps/api"
    }
  }
}
```

### 2. streamable HTTP（网络可达部署）

```bash
# 直接运行（默认仅绑 127.0.0.1:8100）
python -m xagent.adapters.mcp.platform_server --http --port 8100

# 可选：强制 Bearer 校验
export XAGENT_PLATFORM_MCP_TOKEN=<random-token>
```

外部 agent 指向 `http://<host>:8100/mcp`（HTTP 模式），带 token 时加
`Authorization: Bearer <token>` 头。

### 3. Compose 一键启用（full 部署形态）

```bash
docker compose --profile mcp up -d platform-mcp   # 在 deploy/compose/ 下
```

`platform-mcp` 服务复用 api 镜像，`depends_on` api 健康后启动，
`XAGENT_PLATFORM_MCP_TOKEN` 写入 `deploy/compose/.env` 即开启鉴权。

## 安全边界

- `xagent_run` / `xagent_code_review` 走平台既有权限与工具注册表：
  shell/python 默认禁用、沙箱 fail-closed 等安全默认不变；
- HTTP 模式默认仅本机绑定；跨机部署必须设置 `XAGENT_PLATFORM_MCP_TOKEN`；
- 技能导入与 Web 面板/API 共用同一 `gate_candidate` 门禁，外部导入不会绕过质量标准。

## 验证

`apps/api/tests/test_platform_mcp_server.py`（9 项：工具注册面 / 参数校验 /
导入+匹配链路 / 评审无 LLM 诚实降级 / Bearer 中间件 / 应用构建）。
