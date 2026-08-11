# X-Agent Web/API R3-A 真实模型可靠性基线

## 结论

- 终态：`passed`，R3-A 可从 `PARTIAL` 转为 `REVIEW`，但尚未标记 `DONE`。
- 正式批次：`20260811T230626Z-f9a73d`。
- 样本执行时间：2026-08-11 23:06:26 UTC 至 23:38:10 UTC（北京时间 2026-08-12 07:06:26 至 07:38:10）。
- 批次启动 HEAD：`6241b0de4b5b113ced5f9c39cb9a05861533b84b`。
- Worktree：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\webapi-release-hardening`。
- Compose project：`xagent-r2`，本机单实例，真实模型 `qwen3:4b`。

本批次来自一次未中断、严格串行的正式运行，完整记录 50/50 个固定样本，没有补样、拼接、替换、业务重提、模型切换或容器重启。Chat、Scheduler、file_write 的精确成功率与 P95 均达到冻结 SLO；假成功、MockLLM、短剧/媒体 forbidden route 和跨租户读取均为 0。

历史失败批次 `20260811T064937Z-2ec342` 继续独立保留，没有续写或并入本批次。R3-B 定向修复后的新批次证明 Chat 截断假成功和 file_write 180 秒超时缺口在当前候选上均未复现。

## 固定样本矩阵与 SLO

| 类型 | 已记录 | 精确成功 | 成功门槛 | P50 秒 | P95 秒 | Max 秒 | P95 门槛 | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Chat | 30 | 30 | 29 | 6.060 | 8.152 | 11.754 | 120 | 通过 |
| Scheduler | 10 | 10 | 9 | 36.285 | 38.346 | 38.346 | 180 | 通过 |
| file_write | 10 | 10 | 9 | 127.127 | 177.452 | 177.452 | 240 | 通过 |

- JSONL 恰有 50 行，`sample_id` 恰有 50 个且全部唯一；顺序固定为 30 Chat、10 Scheduler、10 file_write。
- `false_success=0`、`failed_sample_count=0`、`hard_failures=[]`。
- 本批次没有非成功样本，因此 fail-closed 指标为 `not_applicable`，按冻结规则视为通过。
- nearest-rank P95 已从 JSONL 独立重算，与 `summary.json` 一致。

## 业务链与终态审计

### Chat

- 30/30 状态为 `succeeded`，final 与持久化消息均与各自 marker 精确相等。
- 30/30 显式记录 `tool_mode=none`、`route=chat_no_tools`，工具调用为 0。
- 30 个 conversation 和 30 个唯一 checkpoint 均存在。

### Scheduler

- 10/10 attempt 1 状态为 `succeeded`，result 与 marker 精确相等，error 为空。
- 10/10 job 当前 `enabled=false`。
- 数据库中每个 run-now 另保留一条 attempt 0 `retried/manual run requested` 管理记录；它没有 started/finished/model result，不是第二次模型执行。

### file_write

- 10/10 sub run 为 `succeeded` 且隔离执行，development task 曾到达 `awaiting_review`。
- 10/10 result commit 可解析，diff、patch、目标文件名和 marker 均存在；patch 当前 SHA-256 与 JSONL 逐一一致。
- 验证后 10/10 development task 均为 `rejected`；worktree 和 `agent/<task_id>` 分支全部已清理，审计 patch 保留。
- 当前没有 `pending` 或 `running` development task。

## 隔离、日志与现场

- 第二租户对第一租户 Chat run、checkpoint 和 development task 的读取探针通过，未跨租户暴露。
- `MockLLM` 命中：0；Forbidden short-drama/media route 命中：0；Traceback 命中：0；`qwen3:4b` 路由命中：172。
- 批次后 deep health 的 database、Redis、Qdrant 均为 healthy；Worker pong 正常，active/reserved/scheduled 均为空。
- API 与 Worker effective model 均为 `ollama/qwen3:4b`；Platform MCP 无 token 返回 401，Prometheus/Grafana 健康端点返回 200。
- 批次前后 API、Worker、Web、PostgreSQL、Redis、Qdrant、Platform MCP、Prometheus、Grafana 以及受保护 `aicg-minio`、`aicg-postgres` 容器身份保持不变。

## 提交前验证

- R3 可靠性合同：37 passed，另 10 subtests passed。
- R2 release contracts：40/40 passed。
- Web/API 后端发布范围：exit 0；10 项既有显式跳过，1 条测试用短 HMAC key 告警，无失败。
- R3 脚本 Ruff、format、`git diff --check`、敏感字段扫描与 `uv.lock` 门在最终提交前复验。

## 原始证据

原始正文位于被 Git 忽略的本机目录，不提交：

- `output/reliability/20260811T230626Z-f9a73d/samples.jsonl`，SHA-256 `82a8062407c495f851fd03e33955884bd77f5f1fe72c071c254b4b85a248a750`。
- `output/reliability/20260811T230626Z-f9a73d/summary.json`，SHA-256 `0077cfff45367f0d70fd3eac7ef53abcb8c069c4e8d8de2829da69b5ee3effd2`。
- `output/reliability/20260811T230626Z-f9a73d/logs-audit.json`，SHA-256 `cc716f3f6391be294082e9b2a10673574ca63ca7f38d01c660e43e15a138b223`。

原始目录已由 `.gitignore` 排除；脱敏扫描未发现 password、token、Authorization、private key、reasoning 或 system prompt。

## 边界与下一门

本结果证明的是当前 Windows 主机、单实例 `xagent-r2` Compose、当前 `qwen3:4b` 与当前候选代码下的 50 样本基线。它不验证短剧/媒体链、Tauri 桌面、多机 HA、E2B、付费 provider、远程 push、部署或生产发布。

R3-A 与 R3-B 当前可保持 `REVIEW`，等待独立规格/质量复审与 Owner 决定是否转 `DONE`；本轮未执行 push、tag、远程发布或生产动作。
