# Web/API P2-D Platform MCP 闭环证据

## 结论

- 审计日期：2026-08-07。
- 分支：`feature/webapi-release-hardening`。
- 审计范围：Platform MCP 会话、统一 Runtime、审批、调度历史、Skill Package、RBAC、租户隔离、审计、敏感信息与本机路径脱敏。
- 排除范围：短剧、Tauri 桌面、多机 HA 和客户现场部署。
- 结论：P2-D 通过。MCP 已从 4 个基础工具扩展为 15 个租户受控工具；同一 Principal、RBAC、tenant filter 和 audit 贯穿读写路径。非回环 HTTP 监听若未配置 Bearer token 会拒绝启动。下一阶段为 R1 全量发布审计。

## 工具面与事实链

| 能力 | 结果 |
|---|---|
| 会话 | `conversation_list/get/message`；读取和续聊都限定当前 Principal tenant，跨租户不可见 |
| 运行 | `run_get/cancel/events`；统一读取持久任务或工作流，MCP 新建 run 会先分配 ID 并持久化，使创建、详情和事件属于同一事实链 |
| 取消 | in-process 任务执行真实 `asyncio.Task.cancel()`；Celery 使用非 terminate revoke；终态不可重复取消，且必须精确确认 run ID |
| 事件 | 合并任务、工作流与证据事件，输出前递归脱敏；不信任存储中的来源字段，统一标记可信来源 |
| 审批 | `approval_list/resolve` 同时覆盖开发任务与工作流 gate；批准、拒绝或否决要求精确 approval ID，并记录审计 |
| 调度 | `scheduler_job_read/run_read` 只读取当前租户数据库事实，不读取其他租户历史 |
| 技能包 | 列表仅返回元数据；详情返回 manifest/frontmatter/body，但移除本机 root path 并递归脱敏 |
| 原有工具 | run、code review、skill match/import 也纳入相同 Principal、RBAC、tenant 和 audit 边界 |

## 安全边界

| 验证 | 结果 |
|---|---|
| Principal | 只从受信任进程环境 `XAGENT_PLATFORM_MCP_USER_ID/TENANT_ID/ROLES` 构造；工具参数不能覆盖 tenant |
| RBAC | reader/viewer 不可发送会话消息；管理、执行和审批动作按平台既有资源/动作授权 |
| 人工确认 | run cancel 与 approval resolve 均要求调用方回传精确资源 ID，错误确认不产生状态变更 |
| 输出脱敏 | token、secret、password、authorization 等递归脱敏；`root_path/worktree_path/patch_path/main_workspace` 不出 MCP 响应 |
| HTTP 鉴权 | 默认只监听 `127.0.0.1`；绑定 `0.0.0.0`、`::` 或其他非回环地址且无 token 时启动返回 2；设置 token 后 Bearer 错误或缺失返回 401 |
| 审计 | 读取和写入均记录 `mcp.*` action、tenant、actor、resource 与脱敏 detail |

## TDD 与新鲜验证

| 验证 | 结果 |
|---|---|
| 工具注册红灯 | 先把合同改为期望 15 个工具，旧实现只注册 4 个，测试失败；实现后通过 |
| HTTP 门禁红灯 | 非回环无 token 用例先因 `_http_token_required` 不存在失败；最小实现及入口测试完成后通过 |
| MCP 定向合同 | `test_platform_mcp_server.py` + `test_platform_mcp_contracts.py` 共 18/18 通过 |
| Runtime/worker 回归 | 相关运行时与 worker 套件 37/37 通过 |
| 目标 Ruff | Platform MCP、Runtime、worker 与合同测试 0 项 |
| 目标 mypy | 使用项目策略 `--follow-imports=skip --ignore-missing-imports`，4 个生产文件 0 项；不忽略第三方存根时只报告 Celery 缺少 `py.typed` |
| 全仓静态门禁 | Ruff `262 <= 286`；mypy `65 <= 74` |
| fresh migration | 独立空 SQLite 完整升级到 `20260807_checkpoints (head)` 后完成协议验证 |
| 真实 MCP 协议 | 独立 Streamable HTTP 服务由标准 MCP ClientSession 初始化，列出 15 个工具，并通过协议读取已播种会话；结果 `conversation_visible=true`、`is_error=false` |
| 真实 HTTP 鉴权 | 同一服务无 Authorization 请求返回 401；验证后服务已停止，端口不再监听 |
| 差异检查 | `git diff --check` 与分文件提交检查通过 |

真实 MCP 协议数据库、客户端脚本和服务日志位于仓库外 `C:\Users\canqu\AppData\Local\Temp\xagent-p2d-mcp-evidence-20260807-054654`。该目录不包含产品提交，也不作为运行时依赖。

## P2-D 实现提交

- `734f61d`：增加 in-process/Celery 可取消语义、统一 Runtime 取消和安全事件输出。
- `151bd80`：扩展 15 个 Platform MCP 工具，增加租户合同、RBAC、审计、脱敏和非回环 HTTP token 门禁。

## 已知限制与 R1 输入

- 既有完整 `test_workflow.py` 在当前 Windows 测试环境两次高 CPU 超时，未产生断言失败，也不能写成通过；本次新增的轻量真实 workflow approval gate 合同已验证等待审批、拒绝、取消和审计路径。R1 需要用有界超时重新分类该套件。
- Web 仍有 100 条存量 ESLint warning；完整 mypy 仍有 65 项基线债务。当前门禁确认没有新增，但 R1 必须归零或形成逐项 owner、原因和失效日期的发布豁免。
- HTTP Bearer token 是单服务身份边界，Principal 来自服务部署配置；不等于面向互联网的逐用户 OAuth/OIDC。非回环无 token 已硬阻断，生产部署仍必须通过 secret manager 注入 token 和 Principal 配置。
- 多机 HA、E2B 和客户现场演练不在当前用户授权范围。R1 不得据此宣称这些能力已发布。
- P2-D 完成不等于整个 Web/API 已发布；只有 R1 全量测试、依赖/安全、迁移、构建、同链浏览器、发布物和回滚审计全部通过，才可形成最终结论。
