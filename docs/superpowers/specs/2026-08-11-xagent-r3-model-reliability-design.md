# X-Agent Web/API R3-A 真实模型可靠性基线设计

> 日期：2026-08-11
>
> 状态：Owner 已批准 50 次方案，待书面规格复核后进入实施
>
> 基线：`feature/webapi-r2-staging-readiness` / `3d2403a`

## 1. 目标

为 R2 已完成的 Web/API 本地发布候选建立第一版真实 Ollama 可靠性基线和服务等级目标（Service Level Objective，SLO）门禁。

R3-A 不增加业务功能。它回答以下问题：

1. `qwen3:4b` 在真实产品入口中的成功率和延迟是多少；
2. Chat、Scheduler、file_write 三类任务是否存在假成功；
3. 模型失败时，状态、错误和产物是否保持 fail-closed；
4. 同一批次结果能否重复执行、自动汇总并用于后续发布判断。

## 2. 范围边界

### 2.1 本阶段包含

- 当前 `xagent-r2` 本地 Full Compose 环境。
- 宿主机 Ollama `qwen3:4b`，不使用 MockLLM 或付费 provider。
- 30 次无工具 Chat、10 次 Scheduler、10 次隔离 file_write，共 50 个统计样本。
- 产品 API、数据库终态、checkpoint、Scheduler run、Git worktree、commit 和 patch 的真实链路。
- 每样本原始结果、批次汇总、日志审计和脱敏 Markdown 报告。
- 自动化合同、静态门和现有 R2 回归。

### 2.2 本阶段不包含

- 短剧、媒体生成、画布、剪辑和供应商链路。
- Tauri 桌面端、多机 HA、E2B 或客户现场演练。
- 新模型下载、模型切换、隐藏 fallback 或付费 provider。
- 远程 CI、push、tag、GitHub Release 或生产部署。
- 通过额外补跑覆盖失败样本。

## 3. 当前缺口

R2 已具备以下基础：

- 普通 Chat 使用 `tool_mode=none` / `route=chat_no_tools`；
- 空响应在一次产品内恢复后仍为空时返回 `model_empty_response_after_retry`；
- API、SSE、Celery 和开发任务会拒绝非成功终态；
- Prometheus 已记录通用 HTTP、LLM 和 Agent 计数；
- R2 同轮浏览器和备份恢复均有真实 `qwen3:4b` 成功证据。

但当前没有固定样本矩阵、不可变批次、按任务类型统计的成功率、P95 延迟、假成功计数或自动 SLO 判定。已有指标也不能单独证明答案精确、Scheduler result 正确或 patch 可下载。

## 4. 方案选择

### 4.1 方案 A：产品 API 黑盒基线（选定）

通过正常注册、SSE Chat、Scheduler API 和 parallel development task API 执行完整产品链。优点是能覆盖鉴权、编排、模型、持久化和产物；代价是执行时间较长，provider 内部字段只记录产品实际暴露的部分。

### 4.2 方案 B：直接调用 LiteLLM/Ollama

直接调用 provider 能更快获得 token 和响应元数据，但绕过状态回写、Scheduler、worktree 和租户边界，不能作为产品 SLO。它只允许在基线失败后用于限定诊断，且诊断请求不能并入 50 个正式样本。

### 4.3 方案 C：先扩展产品观测

先修改产品以持久化 finish reason、恢复次数和 reasoning 长度，数据最完整，但会把观测改造和基线测量耦合。本轮不先扩大生产代码；产品未暴露的字段在报告中记为 `unknown`，不得推断。

## 5. 批次模型

一次执行生成唯一 `batch_id`，格式为 UTC 时间戳加随机后缀。批次包含固定的 50 个样本：

| 类型 | 数量 | 并发 | 单样本产品请求 |
| --- | ---: | ---: | ---: |
| Chat | 30 | 1 | 1 次 SSE run |
| Scheduler | 10 | 1 | 1 次创建 + 1 次 run-now |
| file_write | 10 | 1 | 1 次 parallel-run |

执行顺序固定为 Chat → Scheduler → file_write。全批次严格串行，避免本机 CPU、内存和显存竞争改变统计口径。

每个样本只允许一次业务提交。状态轮询、读取详情、下载 patch 和 reject 清理不算业务重试。产品内部已有的有界恢复属于同一个样本，不能被测试工具再次提交来替代。

50 个样本之外，批次末尾固定执行 1 次无模型租户隔离探针：创建第二 tenant，读取第一 tenant 的 Chat run、checkpoint 和 development task，三项均必须返回 403/404。运行前后还要执行 deep health、Worker pong、受保护容器身份和日志审计；这些检查不进入成功率或延迟样本。

### 5.1 批次中断

- 预检在样本 1 前失败：不创建正式批次结果。
- 样本 1 开始后发生工具崩溃、Docker 中断或人工终止：批次标记 `aborted`。
- `aborted` 批次不得与后续批次拼接，也不得进入 SLO 通过判定。
- 修复测试工具后必须生成新的完整 50 样本批次；旧批次和失败原因保留。

## 6. 样本合同

### 6.1 Chat

每次使用唯一公开 marker：`R3-CHAT-<batch>-<index>`。

必须满足：

- 请求显式使用 `tool_mode=none`；
- started/input 记录 `route=chat_no_tools`；
- 最终状态为 `succeeded`；
- final 和持久化 assistant message 均与 marker 精确相等；
- tool call、tool result 和 MockLLM 均为 0；
- 错误响应不得发送 done 或伪造 final。

### 6.2 Scheduler

每次创建唯一且默认启用的 interval job，`interval_seconds=86400`，goal 只要求回复唯一 marker：`R3-SCHEDULER-<batch>-<index>`。创建后立即 run-now，等待 attempt 1 终态。

必须满足：

- attempt 1 为 `succeeded`；
- result 与 marker 精确相等；
- error 为空；
- agent run 有真实模型证据；
- 样本结束后 job 被暂停，避免后续自动执行。

### 6.3 file_write

每次通过 `parallel-run` 提交单个隔离任务，要求 `file_write` 创建唯一文件 `R3_RELIABILITY_<batch>_<index>.md`，正文为唯一 marker。

必须满足：

- capability 仅为 `file_write`；
- sub run 为 `succeeded`，且 `isolated=true`；
- development task 为 `awaiting_review`；
- worktree、result commit、diff 和 patch 均存在；
- patch 同时包含目标文件名和 marker；
- 下载 patch 后记录 SHA-256；
- 验证完成后调用 reject，清理 worktree 和分支；数据库审计记录保留。

## 7. 结果数据

每个样本写入一行 JSONL，至少包含：

- `batch_id`、`sample_id`、`kind`、`index`；
- `started_at`、`finished_at`、`duration_seconds`；
- `http_status`、`terminal_status`、`success`；
- `marker`、`exact_match`、`false_success`；
- `model`、`route`、`tool_mode`；
- `run_id`、`task_id`、`checkpoint_id`、`job_id`、`development_task_id`；
- `error_code`、`finish_reason`；
- `tool_call_count`、`artifact_count`、`patch_sha256`；
- `mock_detected`、`forbidden_route_detected`。

`finish_reason` 只读取产品真实暴露值；缺失时必须写 `unknown`。JSONL 不记录密码、token、Authorization header、完整 reasoning 或系统 prompt。

批次结束后生成：

```text
output/reliability/<batch_id>/samples.jsonl
output/reliability/<batch_id>/summary.json
output/reliability/<batch_id>/logs-audit.json
docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md
```

`output/reliability` 保存本机原始证据，不默认加入 Git。提交范围只包含脱敏报告、测试、工具、规格和任务板。

## 8. SLO 门禁

完整批次只有同时满足以下条件才能判定 `passed`：

| 指标 | 门槛 |
| --- | ---: |
| Chat 精确成功 | 至少 29/30 |
| Scheduler 精确成功 | 至少 9/10 |
| file_write 完整产物成功 | 至少 9/10 |
| 假成功 | 0 |
| 非成功样本明确 fail-closed | 100% |
| MockLLM | 0 |
| 短剧/媒体 forbidden route | 0 |
| 跨租户读取 | 0 |
| Chat P95 | 不高于 120 秒 |
| Scheduler P95 | 不高于 180 秒 |
| file_write P95 | 不高于 240 秒 |

P95 使用 nearest-rank：将同类持续时间升序排列，取 `ceil(0.95 × n)` 对应的值。数量和公式固定，不能在运行后更改。

若一个批次没有非成功样本，fail-closed 指标记为 `not_applicable` 并视为通过；一旦存在非成功样本，其明确失败终态覆盖率必须为 100%。

任何假成功、MockLLM、短剧/媒体请求或跨租户读取都属于硬失败，不受成功率门槛抵消。

## 9. 失败分类

失败必须归入以下一种，不允许只记录自由文本：

- `http_error`
- `timeout`
- `model_empty_response`
- `wrong_final`
- `false_success`
- `missing_persistence`
- `missing_checkpoint`
- `scheduler_terminal_error`
- `missing_artifact`
- `patch_mismatch`
- `cleanup_failed`
- `mock_detected`
- `forbidden_route`
- `tenant_isolation_breach`
- `harness_error`

产品返回失败且状态、error 和产物均一致时，记为真实失败并视为 fail-closed；它仍计入成功率分母。产品状态为 succeeded 但答案或产物错误时，必须同时标记 `false_success`，整个批次失败。

## 10. 安全与清理

- 通过正常注册创建唯一 `r3-reliability-<batch>` 用户和 tenant。
- 随机密码与 token 只保存在进程内，不接受命令行明文密码参数。
- 输出只保留公开 marker、资源 ID、状态、耗时、错误码和哈希。
- Scheduler 样本完成后全部暂停。
- file_write 样本下载并验证 patch 后全部 reject；cleanup 失败单独计入结果。
- 不删除数据库历史、不执行 `down -v`、不清理其他项目容器或卷。
- 运行前后核对受保护的 `aicg-minio` 和 `aicg-postgres` 容器身份与健康。

## 11. 实现边界

第一版只增加一个专用测试工具及合同测试，不修改模型路由、恢复策略、数据库 schema 或生产 API。

建议文件边界：

- `scripts/run_r3_model_reliability.py`：CLI、预检、批次编排和退出码。
- `scripts/r3_model_reliability.py`：结果类型、样本执行、统计和报告生成。
- `tests/release/test_r3_model_reliability.py`：纯逻辑与 fake HTTP 边界合同。
- `.gitignore`：忽略 `output/reliability/` 原始批次目录。
- `docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md`：真实批次脱敏报告。
- `docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`：R3-A 状态与证据。

工具使用项目现有 Python/httpx 依赖，不新增依赖或锁文件。

## 12. TDD 与验证

实现必须先建立以下红灯：

1. 固定生成 30/10/10 样本计划；
2. Chat 精确匹配与错误 final 分类；
3. succeeded + 错误答案/产物触发 `false_success`；
4. 失败状态满足 fail-closed；
5. nearest-rank P95 和三类阈值判定；
6. 测试工具不自动重提业务请求；
7. Scheduler 暂停和 development task reject 清理；
8. token、密码和 reasoning 不进入结果；
9. 中断批次不能与其他批次拼接；
10. 第二 tenant 不能读取第一 tenant 的三类资源；
11. CLI 根据 `passed`、`failed`、`aborted` 返回不同退出码。

绿灯后必须运行：

- R3-A 定向合同；
- R2 release contracts；
- Web/API 后端发布范围；
- Ruff、format、静态质量和 `git diff --check`；
- 当前 Compose preflight、deep health、worker pong、MCP/Prometheus/Grafana 健康；
- 唯一一次正式 50 样本批次。

## 13. 状态规则

- 规格和计划通过：R3-A 进入 `READY`。
- 工具和离线门通过、真实批次未开始：`CLAIMED`。
- 正式批次满足全部 SLO：`REVIEW`。
- 正式批次完成但未满足 SLO：`PARTIAL`，报告精确失败分布。
- 正式批次因产品故障无法继续：`BLOCKED`，不得补跑掩盖。
- 只有独立复审、证据与工作树收口完成后才能转 `DONE`。

## 14. 完成标准

R3-A 只有同时满足以下条件才能进入 `REVIEW`：

1. 50 个样本来自一个未中断的不可变批次；
2. 三类成功率和 P95 均满足第 8 节门槛；
3. 假成功、MockLLM、forbidden route 和租户泄漏均为 0；
4. 所有非成功样本具有一致的失败终态和错误；
5. Scheduler 与 file_write 清理合同通过；
6. 原始 JSONL、汇总、日志审计和脱敏报告一致；
7. 当前 R2 回归、静态门、Compose 健康和工作树审计通过；
8. 报告明确本机单实例边界、失败样本和未验证范围；
9. 未执行 push、tag、远程发布或生产动作。
