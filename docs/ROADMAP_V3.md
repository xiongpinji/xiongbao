# Roadmap v3：竞品差距补齐（2026-08-05 立项）

> 背景：Roadmap v2 四方向（P0/P1/P2/P4）全闭环、P3 两个变体包落地后，
> 对照 Codex / Hermes Agent 的竞品分析（2026-08-05 会话）确认三块能力短板。
> 模型能力不在补齐范围（X-Agent 可接入任意顶尖模型）。本文件为 v3 唯一计划源。

## 差距认定（竞品分析结论）

| 差距 | 竞品标杆 | v3 轨道 |
|---|---|---|
| 技能生态不兼容外部格式 | Hermes agentskills.io / Claude Code SKILL.md 生态 | V3-1 |
| 技能自进化深度不足（GEPA 代差） | Hermes GEPA：轨迹反思→变体→评测→人工 PR | V3-2 |
| 并行子代理无 worktree 隔离 | Codex multi-agent worktrees | V3-3 |
| 主服务不能作为 MCP server 被外部 agent 调用 | Codex CLI 可作 MCP server（MCP 双向） | V3-4 |

明确不做（维持 v2 边界）：云端沙箱托管任务队列（与私有化交付冲突）、DSPy/GEPA 重依赖引入。

## V3-1 SKILL.md 生态导入 ✅（2026-08-05）

- 交付：`core/skills/importer.py`（frontmatter 解析 + 触发词派生 + 映射），
  `POST /api/v1/skills/import/skillmd[/batch]` 端点，**强制过 gate_candidate 门禁**
  （与 auto_distill 同标准；存量 JSON 导入不过门禁的问题保持原样并在此声明）。
- 效果：Hermes/Claude Code/Cursor 社区技能（awesome-hermes-skills、ai-agent-skills 等
  191+ 技能）可直接导入；重复/缺字段/超容量逐条拒绝并给原因。
- 证据：`tests/test_skill_import.py` 10 项。

## V3-2 技能进化闭环硬化（轻量 GEPA 补全）✅（2026-08-05）

现状（v2 已有雏形）：`generate_variants` / `generate_eval_tasks` / `evaluate_fields` /
`evolve_auto`（变体得分 ≥ 父代+0.1 自动采纳）。

补齐项：

- [x] 变体独立留证：evolve-auto 端点每次判定全量落 evidence_records（kind=skill.evolve_auto），可回溯
- [x] 人工审核流：`require_review=true` 评测通过 → 挂起 `_pending_evolutions.json` → 人工 approve 才 evolve（对标 Hermes 人工 PR 门禁；
  保留当前自动采纳为可选模式）。端点：`GET /skills/evolutions/pending` + approve/reject；队列落盘跨重启
- [x] 失败轨迹反思：`distill_from_failure`（失败根因分析→避坑技能候选→同一门禁入库，source=failure_distilled），
  已接线 loop.py 循环级异常路径（成功走 auto_distill / 失败走反思），从"只从成功提炼"补到"从失败学习"

证据：`tests/test_skill_evolve_review.py` 9 项（挂起/批准/拒绝/跨重启持久化/向后兼容/失败提炼三态）。

## V3-3 并行子代理 worktree 隔离 ✅（2026-08-05）

现状：`parallel.py`（run_parallel_agents / auto_decompose_and_run）与
`supervisor.py`（拓扑依赖并行）已具备进程内并行子代理。

交付：

- [x] 工作区 contextvar 化（新模块 `core/workspace.py`）：loop.py / codex_tools.py /
  power_tools.py 全部从模块级常量改为每任务可覆盖解析，asyncio 任务间隔离
- [x] `run_parallel_agents(use_worktrees=True)`：每子代理独立 git worktree + 临时分支执行，
  结束采集各自 diff（stat + 全文截断）→ 清理 worktree/分支；主工作区零污染；
  非 git 工作区诚实降级（isolated=False）
- [x] 端点参数：`POST /agents/parallel-run` 增 `use_worktrees`
- [x] 子代理执行留证：worktree 路径 / diff_stat / isolated 进 ParallelRunResult.to_dict

证据：`tests/test_parallel_worktrees.py` 6 项（含真实 git 仓库双子代理隔离、主工作区
git status 零污染断言、分支/worktree 清理断言、降级路径）。

## V3-4 X-Agent as MCP Server ✅（2026-08-05）

现状：MCP client 完备（stdio/sse/streamable_http，工具发现注册进 ToolRegistry）；
仅有若干独立 stdio 小 server（filesystem/github/playwright）。

交付：

- [x] `adapters/mcp/platform_server.py`（MCPServer 高层 API）：四个平台工具
  `xagent_run` / `xagent_code_review` / `xagent_skill_match` / `xagent_skill_import`
- [x] 双传输：stdio（宿主 agent 拉起）+ streamable HTTP（`--http --port`，无状态模式，
  默认仅绑 127.0.0.1，`XAGENT_PLATFORM_MCP_TOKEN` 可选 Bearer 校验）
- [x] 安全边界：run/review 走平台既有权限与工具注册表，安全默认不变

证据：`tests/test_platform_mcp_server.py` 9 项（工具注册面/参数校验/导入+匹配链路/
评审无 LLM 诚实降级/Bearer 中间件 401·200/HTTP 应用构建）。

## R3 Web/API 可靠性硬化 ✅（2026-08-12 本地独立验收）

- Chat 截断响应只允许一次有界恢复，二次截断 fail-closed；严格隔离 file_write 使用 270 秒执行预算，普通并行仍为 180 秒。
- 单一不可变真实 Ollama 批次 `20260811T230626Z-f9a73d` 完成 50/50：Chat 30/30、Scheduler 10/10、file_write 10/10；三类 P95 均低于冻结门槛，假成功、MockLLM、forbidden route、租户泄漏和 cleanup failure 均为 0。
- 独立验收复算原始 JSONL、复读数据库与 10 份 patch/清理证据，并重新通过 R3/R2 合同、Web/API 后端发布范围和精确静态质量门。
- 当前只证明本机单实例受控私有部署候选；远端 push/CI、新版本发布、多机 HA、E2B、付费 provider 和客户现场仍不在本结论内。

证据：`docs/coordination/reports/WEB_API_R3_INDEPENDENT_ACCEPTANCE.md`。

## 维护约定

- 每轨道完成须：测试证据 + 本文件状态勾选 + SOT 同步（如涉及对外口径）
- 门禁纪律沿用 v2：全量 pytest / ruff 基线 / CI 全绿后才算闭环
