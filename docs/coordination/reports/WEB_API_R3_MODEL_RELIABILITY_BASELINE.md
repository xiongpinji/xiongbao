# X-Agent Web/API R3-A 真实模型可靠性基线

## 结论

- 终态：`failed`，任务板状态应为 `PARTIAL`，不能进入 `REVIEW`。
- 批次：`20260811T064937Z-2ec342`。
- 样本执行时间：2026-08-11 06:49:37 UTC 至 07:28:07 UTC。
- 批次启动 HEAD：`19b2285149fdf2842786001cab06cae89c3cef16`。
- Worktree：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\webapi-release-hardening`。
- Compose project：`xagent-r2`，本机单实例，真实模型 `qwen3:4b`。

本批次完整记录 50/50 个固定样本，没有补样、拼接、替换或业务重提。Chat 和 Scheduler 的数量、成功率与 P95 门槛通过，但 Chat 出现 1 条产品假成功；file_write 仅 5/10 完整成功，未达到 9/10 门槛。假成功属于硬失败，不能由其他成功率抵消。

上一批 `20260811T044822Z-9fb876` 继续保持 `aborted`，没有续写或并入本批次。

## 固定样本矩阵与 SLO

| 类型 | 已记录 | 精确成功 | 成功门槛 | P50 秒 | P95 秒 | Max 秒 | 延迟门槛 | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Chat | 30 | 29 | 29 | 7.305 | 9.139 | 17.071 | 120 | 成功率与延迟通过；存在 1 条假成功 |
| Scheduler | 10 | 10 | 9 | 38.376 | 40.381 | 40.381 | 180 | 通过 |
| file_write | 10 | 5 | 9 | 176.322 | 180.539 | 180.539 | 240 | 成功率失败；延迟通过 |

- JSONL 恰有 50 行，`sample_id` 恰有 50 个且全部唯一；顺序为 30 Chat、10 Scheduler、10 file_write。
- `false_success=1`，`failed_sample_count=6`。
- 失败码：`false_success: 1`、`missing_artifact: 5`。
- 5 条 file_write 非成功样本均为明确 `timeout`，error 为 `超时(>180s)`，`fail_closed=true`。
- Summary 的 `fail_closed=false` 来自 Chat 假成功：产品状态为 succeeded，但答案错误，不能视为 fail-closed。

## 失败语义审计

### Chat 假成功

- 样本：`chat-001`。
- 目标：`R3-CHAT-20260811T064937Z-2ec342-001`。
- API/DB task 状态：`succeeded`。
- 持久化 final 长度为 26，目标 marker 长度为 35；两者不相等。
- 持久化 final 是目标 marker 的截断前缀，conversation assistant message 同样不精确。
- `tool_call_count=0`，`finish_reason=unknown`；不从 token 或日志推断截断根因。
- 分类：`false_success`，属于批次硬失败。

### file_write 失败

- 失败样本：`file-write-002`、`003`、`006`、`007`、`010`。
- 五条均在约 180 秒进入 `timeout`，无 artifact、patch 或假成功。
- 数据库 development task 均为 `timeout`，error 非空；worktree、work branch 和临时 patch 均不存在。
- 分类：`missing_artifact`；五条均 `fail_closed=true`、`cleanup_ok=true`。

## Scheduler 与 file_write 产物清理

- Scheduler：10/10 `attempt=1` 为 succeeded、result 与各自 marker 精确相等、error 为空。
- Scheduler cleanup：10/10 job `enabled=false`，没有遗留启用任务。
- file_write 成功：5/10，成功样本为 `001`、`004`、`005`、`008`、`009`。
- 五个成功 patch 的当前 SHA-256 与 JSONL 记录逐一一致。
- 成功 development task 均已 reject；全部 10 个 worktree 和 work branch 均已清理。
- 五个 rejected patch 保留用于审计；五个 timeout patch 不存在。

## 隔离、日志与现场

- 第二租户读取探针：通过，Chat run、checkpoint 和 development task 均未跨租户暴露。
- `MockLLM` 命中：0。
- Forbidden short-drama/media route 命中：0。
- Traceback 命中：0。
- `qwen3:4b` 路由命中：242。
- 批次执行期间没有 build、restart、down、pause、prune 或 volume 操作。

## 原始证据

原始正文位于被 Git 忽略的本机目录，不提交：

- `output/reliability/20260811T064937Z-2ec342/samples.jsonl`，SHA-256 `344ef3786ea45fa8fdca495f939fe29cd70874632e7a93f1c6ca6f096e0d2a8a`。
- `output/reliability/20260811T064937Z-2ec342/summary.json`，SHA-256 `6849518838c4152f82225a18242ef17c9459fa4793f1139c6097712726fd4f86`。
- `output/reliability/20260811T064937Z-2ec342/logs-audit.json`，SHA-256 `9bb8623c64f9891978e0181e7b7d3fc982477d24fe558fdd57f43084b34b5042`。

## 未验证边界与下一门

本轮没有验证短剧/媒体链、Tauri 桌面、多机 HA、E2B、付费 provider、远程 push、部署或生产发布。

R3-A 当前只能标记为 `PARTIAL`。下一阶段应先分别诊断 Chat 截断假成功与 file_write 180 秒超时/无产物，不得直接重跑新批次碰运气；修复必须先建立可复现合同，再由 Owner 决定是否批准新的完整 50 样本批次。
