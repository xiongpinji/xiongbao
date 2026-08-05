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

## V3-3 并行子代理 worktree 隔离 — 待启动

现状：`parallel.py`（run_parallel_agents / auto_decompose_and_run）与
`supervisor.py`（拓扑依赖并行）已具备进程内并行子代理。

补齐项：

- [ ] 编码类并行任务可选 git worktree 隔离执行（每子代理独立工作区，结果以 diff 汇总）
- [ ] 子代理执行证据链（sub_run 与父 run 的关联已在 run_id 命名体现，需落 evidence）

## V3-4 X-Agent as MCP Server — 待启动

现状：MCP client 完备（stdio/sse/streamable_http，工具发现注册进 ToolRegistry）；
仅有若干独立 stdio 小 server（filesystem/github/playwright）。

补齐项：

- [ ] 主服务能力以 MCP server（streamable HTTP）暴露：run 任务、code-review、skills match/exec
- [ ] 外部 agent（Claude Code / Codex）可直接把 X-Agent 当工具源调用

## 维护约定

- 每轨道完成须：测试证据 + 本文件状态勾选 + SOT 同步（如涉及对外口径）
- 门禁纪律沿用 v2：全量 pytest / ruff 基线 / CI 全绿后才算闭环
