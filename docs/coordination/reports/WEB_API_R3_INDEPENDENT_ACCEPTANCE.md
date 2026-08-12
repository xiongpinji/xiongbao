# Web/API R3 独立验收报告

> 日期：2026-08-12
>
> 验收基线：本地 `master` / `d67d760d863071f6855806b6bcb6018c9f96cc9e`
>
> 结论：R3-A 与 R3-B 满足冻结规格和本地完成标准，可从 `REVIEW` 转为 `DONE`；远端 push、CI、tag、Release 与生产部署未执行。

## 1. 验收范围

- 规格：`2026-08-11-xagent-r3-model-reliability-design.md`、R3-B 修复规格与实现计划。
- 实现：Chat 截断终态、严格 file_write 超时、不可变批次工具及其合同测试。
- 原始证据：`output/reliability/20260811T230626Z-f9a73d/` 的 JSONL、汇总和日志审计。
- 当前现场：`xagent-r2` 九服务、PostgreSQL 锚点、Scheduler、checkpoint、development task、patch 与清理状态。
- 排除：短剧、媒体、Tauri、多机 HA、E2B、付费 provider、客户环境和远端发布。

## 2. 原始批次独立复算

- 三个原始文件 SHA-256 与基线报告逐字一致：
  - `samples.jsonl`：`82a8062407c495f851fd03e33955884bd77f5f1fe72c071c254b4b85a248a750`
  - `summary.json`：`0077cfff45367f0d70fd3eac7ef53abcb8c069c4e8d8de2829da69b5ee3effd2`
  - `logs-audit.json`：`cc716f3f6391be294082e9b2a10673574ca63ca7f38d01c660e43e15a138b223`
- JSONL 恰有 50 行和 50 个唯一 sample ID，顺序为 Chat 30、Scheduler 10、file_write 10。
- 独立 nearest-rank 复算结果：

| 类型 | 精确成功 | P50 秒 | P95 秒 | Max 秒 | 冻结门槛 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chat | 30/30 | 6.060 | 8.152 | 11.754 | 29/30，P95 ≤ 120 |
| Scheduler | 10/10 | 36.285 | 38.346 | 38.346 | 9/10，P95 ≤ 180 |
| file_write | 10/10 | 127.127 | 177.452 | 177.452 | 9/10，P95 ≤ 240 |

- `false_success`、MockLLM、forbidden route、cleanup failure 均为 0；批次无失败样本，fail-closed 为 `not_applicable`，符合冻结规则。
- 脱敏字段扫描未发现 password、Authorization、reasoning、system prompt 或 private key；原始目录由 `.gitignore` 排除。

## 3. 持久化与清理复读

- `agent_tasks`：30 条 R3 Chat，30 条 `succeeded`。
- `conversation_messages`：91 条含批次 marker 的消息；Chat assistant 精确 marker 全部存在。
- `checkpoints`：51 条相关记录，全部 `available`。
- `scheduled_jobs`：10 条，全部 `enabled=false`；`scheduled_job_runs` 为 10 条 attempt 0 管理记录和 10 条 attempt 1 精确成功记录。
- `development_tasks`：10 条，全部 `rejected`，无 pending/running/awaiting_review。
- 10 份 patch 的当前 SHA-256 与 JSONL 逐一一致；10 个 worktree 和 `agent/<task_id>` 分支均不存在。

file_write 样本的原始 `tool_call_count` 为 0，因为 parallel API 没有向批次工具暴露内部事件计数；成功门由产品代码的 required-first-tool 事件闸和 worktree/commit/diff/patch 四项真实产物共同证明。该字段不作为 file_write SLO 成功条件，后续观测改造应将不可见值改为显式 `unknown`，避免把未暴露误读为未调用。

## 4. 当前代码与质量门

- `pytest tests/release/test_r3_model_reliability.py -q`：`37 passed, 10 subtests passed`。
- `unittest discover -s tests/release -p "test_r2_*.py" -v`：`40/40`。
- `python scripts/run_webapi_release_tests.py`：退出码 0；10 项为明示 Docker/Windows 符号链接环境跳过，唯一告警来自故意使用短 HMAC key 的 OIDC 安全测试。
- `scripts/check_static_quality.py` 首次正确红灯：四组精确指纹与旧基线不一致。审计确认 Ruff 当前 225 条发现全部 blame 到基线提交 `22ef391` 或更早，四组数量未增加；偏差来自后续插入造成的行号移动，mypy 排除项则从 4 降为 0。更新精确指纹后同一命令退出 0。
- R3 工具统一 Ruff 门首次发现 3 个 import 排序问题和 1 个 `Sequence` 导入位置问题，format check 也要求规范化 3 个文件；按工具输出做纯机械最小修复后，Ruff check 与 format check 均退出 0，R3 合同重新通过。
- R3/R3-B 差异审查未发现会导致错误成功、突破租户边界、扩大超时或污染普通并行任务的阻断项。

## 5. 运行现场

- `xagent-r2` 九服务均 running；带 healthcheck 的核心服务为 healthy。
- deep health 返回 200 且 PostgreSQL、Redis、Qdrant 均 healthy；Web、Prometheus、Grafana 返回 200；Platform MCP 无 token 返回 401。
- 受保护的 `aicg-minio` 与 `aicg-postgres` 容器 ID 保持不变且 healthy。
- 当前 Git 只有 `master` 工作树；旧 feature worktree 与分支已移除。未执行 push、tag、远端发布或生产动作。

## 6. 规格与竞品差距结论

- R3-A：单一不可变 50 样本、成功率/P95、假成功、隔离、日志、清理和原始证据一致性全部满足冻结规格。
- R3-B：Chat 截断恢复与二次失败终态、严格 file_write 270 秒预算、普通并行 180 秒边界均有测试和真实批次证据。
- 在 2026-08-07 冻结的 Codex/Hermes 差距清单内，worktree 审查闭环、durable scheduler、完整 Skill Package、checkpoint/recovery 与 Platform MCP 已完成本地验收。
- 这不是对竞品当前全部能力的动态市场复核，也不证明多机、云沙箱、付费模型或客户生产环境等价。

## 7. 验收决定与下一门

R3-A、R3-B 转为 `DONE`。当前本地 `master` 可作为下一次 Web/API 发布候选的输入，但正式发布仍必须获得 Owner 对以下动作的单独授权：

1. push 当前 `master`；
2. 在远端对同一提交运行完整 CI；
3. 选择不可复用 `v1.0.0` 的新版本号并生成 tag/Release；
4. 按目标环境执行发布、回滚和签字。
