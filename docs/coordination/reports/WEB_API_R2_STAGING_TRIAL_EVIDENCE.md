# Web/API R2 本地试运行证据报告

> 日期：2026-08-10
> 分支：`feature/webapi-r2-staging-readiness`
> 最终功能候选：`2ad8a1d`
> 环境：Windows + Docker Desktop，`xagent-r2` 本地 Full Compose，真实本地 `qwen3:4b`
> 结论：R2 Web/API 范围达到本地受控试运行发布标准；不等同于正式商用 GA、远端 CI 签发或生产部署。

## 1. 范围与判定

本轮覆盖 Web、API、Worker、PostgreSQL、Redis、Qdrant、Platform MCP、Prometheus、Grafana，以及真实 Ollama 对话、调度、技能包、隔离开发任务、租户隔离、重启、故障恢复和备份恢复。

明确排除：短剧业务链、媒体生成、Tauri 桌面端、多机 HA、E2B、付费 provider、客户现场与生产环境。排除项没有被写成已验证能力，也没有为通过门禁而调用短剧或媒体 API。

最终判定：

- R2-A 至 R2-E 均满足各自本地试运行完成标准，转为 `DONE`。
- 本地候选可以进入 reviewer/owner 的后续发布决策。
- 未执行 push、tag、PR 合并、远端部署或生产写入。

## 2. 源码、镜像与测试

### 2.1 API/Worker

- 最终候选 API 镜像原始全量收集 860 项：`832 passed / 14 failed / 14 skipped`。
- 14 项失败全部位于明确排除的短剧/媒体路径：audio pipeline 4 项、creative studio 6 项、media 1 项、pipeline 2 项、runtime creative status 1 项；`network=none` 下外部 Pollinations 路由不可用。本报告不把原始全仓结果描述为全绿。
- 使用 14 个精确 node id 排除上述范围后，R2 Web/API 镜像结果为 `832 passed / 14 skipped / 2 warnings`，用时 477.4 秒。
- 14 项 skip：可选 `edge_tts` 5 项、可选 `moviepy` 1 项、默认关闭的 Docker integration 8 项。
- 2 条 warning：passlib `crypt` 弃用；OIDC 伪造 HS256 安全测试故意使用短 HMAC key。
- 当前源码相关回归：checkpoint、resume、orchestration、evidence、ops 共 `80/80`；evidence/ops 独立 `25/25`；release unittest `38/38`。
- 最终镜像包含且只包含所需运维脚本；安装布局和源码布局均可导入 evidence/ops 脚本。

### 2.2 静态与发布门

- 关键 Ruff `F821,F822,F823,B023`：通过。
- 完整 Ruff：精确基线通过；E501 为 187 条固定指纹，exception fallback 17、subprocess 15、async 6，均未漂移。
- mypy：仅剩 4 条短剧排除项固定指纹，Web/API 范围 0 条新增错误。
- Python 许可证门：通过。
- API、Web、README 版本：均为 `v1.0.0`。
- Compose R2 release contracts：`38/38`。
- `scripts/r2-preflight.ps1 -AllowRunningProject`：13 个端口均确认属于目标 project，退出 0。
- Compose `config --quiet`：通过。

### 2.3 Web

- 标准 Web 测试：`35/35`。
- `npm run typecheck`：通过。
- `npm run lint`：0 error / 99 warnings。
- `npm run lint:release`：89 条 React compiler migration + 10 条 effect dependency，精确指纹通过。
- `npm run build`：通过。
- `npm run audit:release`：生产依赖 0 漏洞。

## 3. Compose 与运行态

最终本地 project 为 `xagent-r2`。最终浏览器轮前后：

| 服务 | 容器 ID | 状态 |
| --- | --- | --- |
| api | `49aeb2a5f83c` | running / healthy |
| worker | `36371148e0f2` | running / healthy |
| web | `0c04e51d5054` | running / healthy |
| postgres | `718b16067ca6` | running / healthy |
| redis | `d4c436c4f4db` | running / healthy |
| qdrant | `1b4098d037b2` | running / healthy |
| platform-mcp | `8d41785c2a5c` | running / healthy |
| prometheus | `e3cc8e1cf4db` | running，端点已验收 |
| grafana | `61a2dd886d6c` | running，端点已验收 |

受保护的 `aicg-minio` / `aicg-postgres` 保持原容器 ID `07e3c2aef1a1` / `3af4cf4c653d`，均 healthy，未被本轮重建。

最终健康复验：

- `/health/deep`：overall、database、redis、qdrant 均 `healthy`。
- Worker Celery inspect：1 node `pong`。
- API/Worker strict warmup：`qwen3:4b`，route=`ollama`，成功。
- Web 宿主构建与容器 bundle SHA-256 一致。
- API、Worker、数据库、扩展和受保护容器未因两次 Web-only 修复被替换。

## 4. 真实 Ollama 与浏览器同轮证据

最终证据轮命令固定为 headed Chromium、`workers=1`、`retries=0`，使用随机新租户和临时 ZIP。结果：`6/6 passed`，总用时 1.8 分钟。

| 场景 | 结果 |
| --- | --- |
| PostgreSQL / Redis / Qdrant deep health | 通过，1.1 秒 |
| 真实 Ollama Chat → Run Console → reload/history | 精确 `R2-WEB-OLLAMA-OK`，通过，9.6 秒 |
| durable scheduler create/run/pause/reload | attempt 1 `succeeded`，result 精确 `R2-SCHEDULER-OK`，error 为空，32.3 秒 |
| 完整 Skill ZIP 导入 | `SKILL.md`、assets、references、scripts 四文件可见，2.1 秒 |
| 隔离开发任务 | 真实 `file_write`、worktree、commit、diff、patch、下载/审查链通过，59.9 秒 |
| 第二租户隔离 | Skill、checkpoint、development task 均 403/404，1.8 秒 |

同轮附加合同：

- Chat 请求使用 `tool_mode=none` / `route=chat_no_tools`，无工具事件，最终回复可刷新恢复。
- 开发任务必须先调用 `file_write`，只有真实 diff 和成功终态才能进入 `awaiting_review`。
- 浏览器 `console.error=0`、`pageerror=0`、短剧/媒体 forbidden request=0。
- API/Worker 当前窗口 `MockLLM=0`，真实 route 为 Ollama。
- 临时技能 ZIP 在 `finally` 中删除，未进入仓库。

## 5. 截图与客观视觉复核

六张截图均为 1280×720，并逐张人工查看：

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `r2-chat.png` | 50,667 | `97adc9298ee0987ec7a402e5fae4273b18b8f82fb5bf7cdeb2139d819030620f` |
| `r2-run-console.png` | 67,841 | `445d023700864a9445da8884c7b528665b98e20d9fc1f90adf945f3604432057` |
| `r2-reload.png` | 67,841 | `445d023700864a9445da8884c7b528665b98e20d9fc1f90adf945f3604432057` |
| `r2-scheduler.png` | 69,626 | `15d7d52413f6793c76384680faed29d13fa4b3ded3739fb71ec136a73762ed1a` |
| `r2-skill.png` | 82,881 | `b3aac4fb98af89a450a9138e9cdec205e1dbc85bbfd478263c36ee3c5cd0633c` |
| `r2-development-task.png` | 82,839 | `db850393d8072e8efa9e391c719b5c8c91d63cb2178dea7cec8ff5a2af78018d` |

截图审计发现并修复两项发布可见问题：

1. 右侧预览曾默认硬编码并加载 `http://localhost:5175`；现默认为空状态，只有用户输入 URL 后才创建 iframe。
2. 开发任务窄详情区曾被全局 `xl` 断点强制成四列，元数据逐字竖排；现固定为可读的 2×2 网格。

`r2-run-console.png` 与 reload 后的 `r2-reload.png` 哈希相同，代表持久化页面稳定，不是遗漏截图。仓库没有对应 `reference.png` 或正式视觉规格，因此这里只判定客观可读性、无破图和功能状态可见；不宣称像素级对标完成。

## 6. 重启、故障与持久化

R2-C 已完成：

- API/Worker restart 后，Web HTTP/WS 代理可恢复；发现的 Nginx Docker DNS 固定解析和 `/ws` 尾斜杠问题均以 TDD 修复。
- Worker pause 时任务保持非终态，unpause 后唯一成功终态和 checkpoint 可读。
- Redis pause 2 秒后，deep health 在有界超时内返回 Redis degraded；unpause 后恢复 healthy。
- `docker compose down` 未带 `-v`，再 `up` 后四个项目卷保留；Chat、Run、Checkpoint、Scheduler、Skill、Development Patch 锚点一致。
- Celery 单任务异步生命周期统一为一个 event loop，dispose 异常不再覆盖业务终态。

## 7. MCP 与观测

R2-D 已完成：

- Platform MCP initialize 成功，可列出 15 个工具。
- 同租户 conversation/run/events/approval 可读；无 token 与真实第二租户 JWT 均 401；跨租户 run 返回 `run_not_found`。
- Prometheus target `api:8000/metrics` 为 up；`/metrics` 已绕过响应缓存并保持实时文本响应。
- 唯一真实 `qwen3:4b` metrics 探针形成 run counter。
- Grafana datasource uid=`prometheus`、X-Agent Overview 和 datasource query 均通过；provisioning mount 为只读。

## 8. 备份恢复

R2-E 已完成：

- 在停止源 Web/API/Worker/MCP 写入面后，生成 PostgreSQL、Qdrant、Redis、xagentdata 四件仓库外备份并记录 SHA-256；manifest 无 secret。
- 在独立 project、network、端口、secret 和四个 fresh volume 中恢复 migration、租户表计数、Qdrant 27 points、Skill 四文件和 Development Patch。
- 首次 restore 模型运行因 qwen3 Thinking 两次耗尽 512 tokens 而 fail-closed；修复只在 `finish_reason=length` 时把恢复预算提高到 1024，并保留空响应失败语义。
- 新镜像下唯一 restore run 精确返回 `R2-RESTORE-OK`，工具事件 0、MockLLM 0；源 DB 未出现该 run。
- restore project 已执行 `down`，未使用 `-v`；恢复卷和仓库外备份保留。

## 9. 日志与敏感信息审计

最终 15 分钟 API/Worker/Web/MCP/Prometheus/Grafana 日志计数：

- Traceback 0
- Unhandled 0
- MockLLM 0
- 502 Bad Gateway 0
- cross-event-loop 0
- terminal checkpoint failure 0
- `model_empty_response_after_retry` 0
- 本地 env 中 secret/password/token/API key 实际值命中 0

浏览器截图未见密码、JWT、API key；`git diff --check` 通过；`apps/api/uv.lock` 不存在；最终只提交白名单文档和六张脱敏截图。

## 10. Codex / Hermes 差距收敛与剩余差距

本轮已收敛的产品差距：

- 对 Codex 类编码 Agent：隔离 worktree、强制首工具、真实 diff/commit/patch、人工审查、apply/reject、状态和 checkpoint 证据链已形成。
- 对 Hermes 类长程自治 Agent：durable scheduler、重试/暂停、Skill Package、checkpoint 恢复、Platform MCP、观测和备份恢复已形成 Web/API 主链。
- 普通 Chat 与工具型任务已分路，避免把全工具 schema 注入简单对话。

仍存在的差距和风险：

- 本地 `qwen3:4b` 仍有偶发空响应历史；当前系统会 fail-closed，不会伪装成功，但尚无长期稳定性/SLO 数据。
- 尚未完成客户现场、生产流量、多机 HA、远程沙箱、Tauri 桌面或付费 provider 验收。
- 缺少正式视觉基准，不能宣称与竞品像素级一致。
- 14 个原始全仓失败属于本轮明确排除的短剧/媒体路径；短剧独立项目接入后需另做同级真实验收。

## 11. 最终结论

R2 Web/API 本地 Full Compose 试运行形成了同一候选上的源码、镜像、真实模型、浏览器、状态回写、可下载开发产物、租户隔离、故障恢复、MCP、观测和备份恢复证据。就用户批准的 Web 优先范围而言，可以转 `DONE` 并进入后续 reviewer/owner 发布决策。

该结论不包含生产部署、正式商用 GA、短剧链、桌面端或多机能力。
