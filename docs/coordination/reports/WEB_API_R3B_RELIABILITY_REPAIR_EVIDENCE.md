# Web/API R3-B 可靠性缺陷修复证据

> 日期：2026-08-11
>
> 分支：`feature/webapi-r2-staging-readiness`
>
> 最终候选：`dd32a36958d3f8fd4a0d296d56d221eca7b7b0ef`
>
> 结论：R3-B 修复与定向 Live 验证通过；R3-A 统计门仍为 PARTIAL，需新的完整 50 样本批次重算。

## 1. 修复范围

- `58e7620`：无工具 Chat 首答非空但 `finish_reason=length` 或 completion tokens 达到请求上限时，只允许一次 1024-token 恢复；恢复再次截断则 `model_incomplete_response_after_retry`，不发 final。
- `dd32a36`：普通并行任务保持 180 秒；只有真实 worktree 且 capability 精确为 `[file_write]` 的严格任务使用 270 秒 Agent 执行预算，超时错误使用实际预算。
- 未修改模型、provider、提示词、API schema、Web、Worker、短剧/媒体或桌面端。

## 2. TDD 与离线验证

- 初始红灯：4 个聚焦合同中 3 failed / 1 passed，分别命中截断前缀伪成功、二次截断伪成功和严格任务仍使用 180 秒；普通并行保持 180 秒已通过。
- 修复后聚焦合同：6/6 通过，包括既有空响应 length 恢复和严格超时清理。
- 提交后相关回归：191 项通过，覆盖 orchestration、parallel worktree、Runtime/SSE、Worker、provider、checkpoint、development task 与 automation。
- R2/R3 release contracts：77 passed，另含 87 subtests。
- Ruff `F821,F822,F823,B023,I001`、`git diff --check`、secret scan 通过；`apps/api/uv.lock` 不存在，工作树干净。
- `loop.py` 完整 Ruff 仍有 129 条 HEAD 既存 legacy 告警，本任务没有新增或扩大清理。

## 3. API-only 部署门

- 仅执行 `docker compose ... build api` 与 `up -d --no-deps api`。
- API：`49aeb2a5f83c` → `3c9d78992d0f`；新镜像健康。
- Web `0c04e51d5054`、Worker `36371148e0f2`、Platform MCP `8d41785c2a5c`、Grafana `61a2dd886d6c`、Prometheus `e3cc8e1cf4db`、PostgreSQL `718b16067ca6`、Redis `d4c436c4f4db`、Qdrant `1b4098d037b2` 与受保护 `aicg-minio 07e3c2aef1a1`、`aicg-postgres 3af4cf4c653d` 均未替换。
- 宿主/容器源码 SHA-256 一致：`loop.py=83cc15d4…972d3`，`parallel.py=8f01485f…b1011`。
- deep health 三依赖 healthy；Worker pong；API Ollama warmup `qwen3:4b/ollama` 成功；Web root 与 Web→API OIDC 代理均为 200。

## 4. 单次真实定向探针

探针 ID：`r3b-live-20260811T143737Z-4d3af0`。每种业务只提交一次，无补样或重试。

### Chat

- run/task：`b186609c0b9c482c97d0ba04531b8e9b`；conversation：`c970aa6bece44c0fa1e33c40038a4f53`。
- HTTP 200，10.905 秒，`succeeded`，route=`chat_no_tools`，tool_mode=`none`。
- final 与唯一 marker 精确一致；false_success=false；tool calls=0。
- checkpoint `74d7ac53d8524a2981007f965ee1eba3`，step 1，status=`available`。

### file_write

- parent/sub run：`0ac298d021be46baa6fc12112dd332ef` / `0ac298d021be46baa6fc12112dd332ef_sub0`。
- development task：`10f70eb54bcb4b84841a6fb5ff211468`。
- HTTP 200，149.775 秒，sub run `succeeded`；worktree、result commit、diff、patch 四项产物全部通过。
- patch SHA-256：`c245ca3dfa3ea9b2e78a1557df284cbd715542e0eedbce6124ac7eca20ad396c`。
- 验证后正常 reject；DB 状态 `rejected`，worktree、patch 与临时 branch 均不存在。

## 5. 日志与剩余边界

- 探针窗口 API/Worker MockLLM=0；API Traceback=0；短剧/媒体 forbidden 命中=0；`model_degraded=false`。
- 本次真实 file_write 在 180 秒内完成，因此它验证的是新镜像和完整产物/清理链，并不单独证明 180–270 秒任务的成功率。
- R3-A 原批次仍保持 50/50 不可变失败证据；Chat 29/30 和 file_write 5/10 不因本次定向探针被改写。
- 下一门是基于同一冻结设计执行一个全新的完整 50 样本批次，重新计算成功率、P95、假成功与 fail-closed；不得拼接旧批次或本次两条探针。
- 未 push、tag、远程发布或生产部署。
