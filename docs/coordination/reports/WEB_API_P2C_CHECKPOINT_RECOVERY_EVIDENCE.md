# Web/API P2-C Checkpoint 恢复与受控回滚证据

## 结论

- 审计日期：2026-08-07。
- 分支：`feature/webapi-release-hardening`。
- 审计范围：数据库 checkpoint、会话恢复、父子 run 谱系、租户隔离、受控 Git 回滚、Web 时间线和重复恢复幂等性。
- 排除范围：短剧、Tauri 桌面、任意文件快照回滚和未审查任务回滚。
- 结论：P2-C 通过。恢复会创建新的子 run，不覆盖历史；回滚只接受同租户、同 run、已应用且路径受控的开发任务 commit/patch。下一阶段为 P2-D MCP 会话、运行、审批与事件接口。

## 数据模型与安全边界

| 验证 | 结果 |
|---|---|
| 数据库事实源 | `checkpoints` 保存 tenant、conversation、run、parent checkpoint、step、状态、脱敏消息、workspace 相对变更路径、恢复 run 和回滚结果 |
| 自动 checkpoint | 内置编排每 5 步及取消时使用独立事务落库；成功后保留历史，不再依赖用户目录 30 分钟 JSON |
| 敏感信息 | Bearer、API key/token/secret/password/authorization 和 provider token 在 checkpoint 写入前递归脱敏；消息数量、正文长度和 JSON 总量均有上限 |
| 路径约束 | 只保存 workspace 内相对路径，拒绝 workspace 外路径；回滚 artifact 路径必须是 checkpoint 变更路径的子集 |
| 租户隔离 | checkpoint list/detail/resume/rollback、会话消息/read/delete/continue 均按 Principal tenant 约束，跨租户返回 404 |
| 恢复谱系 | 恢复复制经过脱敏的消息、goal、step 和 changed files，创建新 run/子 checkpoint；完成或失败状态独立写回 |
| 重复恢复 | 父 checkpoint 通过数据库条件更新原子认领；已有 `resumed_run_id` 或处于 pending/running 时返回 409，Web 同步禁用按钮 |
| 受控回滚 | 仅允许同 run、已 apply、分支匹配的开发任务 commit 或受控 patch；要求干净工作区，成功生成新的 Git commit，失败写回结构化原因 |

## API、Web 与真实浏览器

| 验证 | 结果 |
|---|---|
| API 契约 | list/detail 不泄露其他租户；resume 要求精确 checkpoint ID；rollback 还要求开发任务 ID、来源类型和 admin `agent/manage` 权限 |
| Web 时间线 | Chat 按 conversation 展示紧凑时间线；Run Console 按 run 展示状态、step、变更文件、父 checkpoint、恢复 run 链接、回滚 commit/error |
| 人工确认 | 恢复使用确认对话框并创建新 run；回滚需要开发任务 ID、commit/patch 来源和危险操作确认 |
| Playwright 同链 | 独立 SQLite 从空库迁移至 head，写入 checkpoint 和 run 后启动隔离 API/Vite；真实登录、打开 Run Console、确认创建恢复 run、进入子 run 页面均成功 |
| 浏览器结果 | 父 checkpoint `79a5942637de4ae7bb138407bf81ba06` 创建子 run `e316e14c43c94359befc7b2b502c3364`；子 checkpoint `d54a6ea035864f0ca71f6326b6d92350` 显示“恢复完成”和父来源 |
| 后端回读 | API 回读父 `resumed_run_id`、子 `parent_checkpoint_id`、`completed` 状态和 run `succeeded` 全部一致 |
| 控制台 | Run Console 与恢复后子 run 页面均为 0 error、2 条 React Router 既有 warning；登录页最初仅有 favicon 404，导航后新页面错误为 0 |

浏览器截图、独立数据库和服务日志位于仓库外 `C:\Users\canqu\AppData\Local\Temp\xagent-p2c-browser-evidence-20260807-043746`。回滚按钮在真实页面完成渲染；为避免对当前仓库制造无必要 Git 变更，实际 commit/patch 回滚由隔离临时 Git 仓库测试提供证据，浏览器链未执行破坏性回滚。

## 新鲜验证

| 验证 | 结果 |
|---|---|
| 后端关联回归 | `test_checkpoints.py`、`test_checkpoints_api.py`、`test_checkpoint_rollback.py`、`test_checkpoint_resume_orchestration.py`、`test_conversation_tenant.py` 共 11/11 通过 |
| Runtime 回归 | `test_runtime_runs.py` 23/23 通过 |
| TDD 幂等性 | 新增重复 resume 用例先得到 202 并失败；原子认领修复后返回 409，完整关联链通过 |
| 目标静态检查 | Checkpoint domain/API Ruff 0；目标 mypy（`--follow-imports=skip`）0 |
| 全仓静态门禁 | Ruff `262 <= 286`；mypy `65 <= 74` |
| fresh migration | 空 SQLite 完整升级到 `20260807_checkpoints (head)`，`checkpoints` 表和列已回读 |
| Web 回归 | 21/21、typecheck、lint 0 error / 100 条存量 warning、生产 build（2379 modules）全部通过 |
| 差异审计 | `git diff --check` 和分文件提交检查通过；Playwright 临时快照已从工作树清除，API/Vite 监听进程已停止 |

## P2-C 实现提交

- `40433d8`：增加数据库 checkpoint、会话恢复、父子 run 和受控回滚后端链。
- `81aa2f2`：以数据库原子认领阻止重复创建恢复 run。
- `4f95d23`：增加 Web checkpoint 时间线、恢复确认、回滚控制和状态测试。

## 已知剩余风险

- Web 仍有 100 条存量 ESLint warning；R1 必须归零或形成逐项 owner、理由与失效日期豁免。
- 完整 mypy 仍保留 65 项基线债务；当前门禁阻止新增，但 R1 需要确认发布豁免清单。
- SQLite 单机路径已用原子条件更新阻止重复 resume；多机 HA 不在本轮范围，生产 PostgreSQL/部署拓扑仍需在 R1 明确。
- P2-D MCP 和 R1 全量发布门禁尚未完成，因此不能判定整个 Web/API 已达到最终发布标准。
