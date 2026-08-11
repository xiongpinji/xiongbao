# X-Agent Web/API R3-A 真实模型可靠性基线

## 结论

- 终态：`aborted`。
- 批次：`20260811T044822Z-9fb876`。
- 执行时间：2026-08-11 04:48:22 UTC 至 05:22:23 UTC。
- 批次启动 HEAD：`e987114b1b8bce294a7e5f4190ebff8a8eea99eb`。
- Harness 修复 HEAD：`81017685bf707056fbcc4b13494f5ed6681e4517`；修复后没有重跑或续写本批次。
- Worktree：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\webapi-release-hardening`。
- Compose project：`xagent-r2`，本机单实例，模型 `qwen3:4b`。

本批次在 33/50 个样本后由人工停止。原因是 Scheduler harness 把 `POST /run` 返回的 `attempt=0` 请求 ID 当成 `attempt=1` 的执行 ID；产品实际成功的 Scheduler run 因 ID 不同而被错误记录为 600 秒 timeout。首次工具层终止没有清掉子进程，第三条 Scheduler 误判随后写入，进程还创建并完成了第 4 个产品 job、但尚未写入 JSONL；发现后已精确终止两个批次 Python 进程并暂停该 job。继续执行会制造更多假失败，因此不能把本批次判为产品可靠性 `failed`，也不能判为 `passed`。

## 不可变样本矩阵

| 类型 | 计划 | 已记录 | 原始成功 | P50 秒 | P95 秒 | Max 秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Chat | 30 | 30 | 30 | 7.665 | 14.183 | 15.949 |
| Scheduler | 10 | 3 | 0 | 600.980 | 602.093 | 602.093 |
| file_write | 10 | 0 | 0 | 未执行 | 未执行 | 未执行 |

- JSONL 恰有 33 行，`sample_id` 恰有 33 个且全部唯一；顺序为 30 Chat、3 Scheduler。
- Chat 30/30 精确 marker 成功，满足本轮 Chat 成功率与 P95 门槛，但这不能替代未完成的 Scheduler、file_write 和租户隔离。
- 原始失败码为 `timeout: 3`，`false_success: 0`，cleanup failure 为 0。
- Summary 中 `fail_closed=false` 来自两条 harness 误记 timeout，不代表产品把失败伪装为成功。

## Scheduler 交叉审计

本批次创建了 4 个 Scheduler job；前三条被旧 harness 误记为 timeout，第 4 条在停止前已完成产品执行、但没有写入 JSONL。数据库中的真实 `attempt=1` 证据如下：

| 样本 | 产品状态 | 执行秒数 | 精确结果 | error | job enabled |
| --- | --- | ---: | --- | --- | --- |
| 001 | succeeded | 9.107 | `R3-SCHEDULER-20260811T044822Z-9fb876-001` | 空 | false |
| 002 | succeeded | 15.060 | `R3-SCHEDULER-20260811T044822Z-9fb876-002` | 空 | false |
| 003 | succeeded | 26.047 | `R3-SCHEDULER-20260811T044822Z-9fb876-003` | 空 | false |
| 004 | succeeded | 14.700 | `R3-SCHEDULER-20260811T044822Z-9fb876-004` | 空 | false |

四项产品结果均成功且精确，四个 job 最终均已暂停。Harness 缺陷已由测试复现并在 `8101768` 修复：对新建 job 的 `/runs` 只选择 `attempt=1`，不再要求它复用 manual request ID。修复后的 R3 合同为 `37 passed / 10 subtests passed`；按不可变批次规则未使用修复代码续跑旧批次。

## 日志、清理与隔离

- `MockLLM` 命中：0。
- Forbidden route 命中：0。
- Traceback 命中：0。
- `qwen3:4b` 路由命中：72。
- Scheduler cleanup：4/4 job `enabled=false`。
- file_write：尚未开始，因此无 worktree、branch 或 patch 可验收。
- 第二租户探针：尚未开始，状态为 `tenant_isolation_unverified`，不能写成隔离通过或隔离泄露。
- 核心、MCP、Prometheus、Grafana 与两个受保护容器在停止后保持运行；没有 build、restart、down、pause、prune 或 volume 操作。

## 原始证据

原始正文位于被 Git 忽略的本机目录，不提交：

- `output/reliability/20260811T044822Z-9fb876/samples.jsonl`，SHA-256 `0456411cd7dce7ac790f0ffe905e6a253a3daf0c7031a2c403fb7b955c94e7d9`。
- `output/reliability/20260811T044822Z-9fb876/summary.json`，SHA-256 `c3f06f4688eeb181ff8c49e3fad9c6679746ef5d20a5024c7cda68d4393e30fc`。
- `output/reliability/20260811T044822Z-9fb876/logs-audit.json`，SHA-256 `7ac088000649ffd2d2204ab4b33ae379e8fbf175ee6dc76b75df61394c6b2c04`。

## 未验证边界与下一门

本轮没有验证短剧/媒体链、Tauri 桌面、多机 HA、E2B、付费 provider、远程 push、部署或生产发布。R3-A 当前只能标记为 `BLOCKED`，不能标记为 `DONE` 或 `REVIEW`。

若要获得可发布的 50 样本结论，必须由 Owner 重新批准一个全新 batch ID；旧批次不得续写、拼接或补样。新批次开始前还需重新执行 clean Git、容器身份、Worker 空闲和 `--preflight-only` 门。
