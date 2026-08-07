# Web/API R1 发布审计证据

## 结论

`feature/webapi-release-hardening` 已达到本阶段定义的 Web/API 本地发布候选标准。Codex 对标的开发任务闭环，以及 Hermes 对标的持久调度、完整 Skill Package、会话恢复与 checkpoint 闭环，均已通过源码、自动化测试、发布镜像和真实浏览器验证。

本结论不代表已经推送、打 tag 或部署生产；短剧、Tauri 桌面端、多机 HA、E2B 和客户现场演练继续排除。

## 候选修复

| Commit | 修复 |
| --- | --- |
| `91255ab` | 修复侧栏会话首次挂载被清空，以及完整刷新无法从持久状态恢复的问题；新增 3 项生命周期测试。 |
| `b2afce7` | API 发布镜像加入 Git，使开发任务提交、回滚和并行 worktree 在容器中可运行。 |
| `1107307` | Webhook 注册/删除改为等待 SQLite 持久化完成后才返回，消除成功响应与落库之间的竞态。 |
| `e10878b` | 修复 1037px 视口下长 run ID 与统计卡重叠；新增响应式布局合同测试。 |
| `6c9ccc9` | 复用现有品牌资产修复 favicon 与 Web Manifest 图标 404。 |

## 自动化与发布物验证

| 门禁 | 新鲜结果 |
| --- | --- |
| 最终 API 镜像全量测试 | `720 passed / 15 skipped`，退出码 0；跳过项为 6 个可选 TTS/媒体依赖测试和 9 个需显式启用的实机 Docker sandbox 集成测试。 |
| Web 默认测试 | `25/25` 通过。 |
| Web 类型与构建 | `tsc -b --noEmit`、`tsc -b && vite build` 通过；Vite `8.2.1`，2366 modules transformed。 |
| Web 精确 lint 门禁 | React compiler 89 项、effect dependencies 10 项；精确文件/规则/行列指纹通过，owner=`web-platform`，到期日 `2026-09-30`。 |
| API 精确静态门禁 | E501 189、exception fallback 17、controlled subprocess 15、async blocking 6；精确指纹通过，均有 owner、理由和 `2026-09-30` 到期日。 |
| mypy | Web/API 范围 0；仅排除的短剧模块保留 4 项精确指纹，到期日 `2026-12-31`。 |
| 生产依赖 | `npm run audit:release` 通过。仅接受 React Router RSC 公告 `GHSA-qwww-vcr4-c8h2`；源码无 RSC/SSR surface，发布镜像为纯 Nginx static dist，owner=`web-platform`，到期日 `2026-09-30`。 |
| 许可证与版本 | `scripts/license_check.py` 通过；API、Web、README 版本均为 `1.0.0`。 |
| 最终 API 镜像 | `xagent-api:webapi-r1` 构建成功；fresh SQLite 迁移至 `20260807_checkpoints`，`/health` 返回 `status=ok, version=1.0.0`，镜像内 Git `2.47.3`。 |
| 开发任务镜像回归 | checkpoint rollback、development task lifecycle、evidence archive、parallel worktrees 共 `17/17` 通过。 |

最终全量测试仅保留两条非失败警告：Python 3.13 将移除 `crypt` 的第三方依赖弃用提示；OIDC 伪造测试刻意使用短 HMAC key 触发的安全提示。此前出现的 `aiosqlite` 未处理线程异常已通过 Webhook 耐久性修复消除。

## 真实 Web/API 同链验证

使用独立 Docker 网络、fresh SQLite、最终 API 镜像、Nginx Web 镜像和 headed Playwright 完成：

1. lite 测试账号登录并进入聊天主页。
2. 创建 run `6a5184950bd8498297788ef4b159432d`，运行成功；运行台显示 3 项证据、replay pointer、空 validation risks 和 checkpoint 时间线。
3. 创建 durable scheduler job `c00520101ce9`，暂停后完整刷新仍显示“已暂停”。
4. 创建 Skill“R1 发布审计复核”，刷新后 v1、trigger、instructions 和 manifest 均保留。
5. 从运行页点击最近会话可恢复消息；完整浏览器刷新后仍恢复同一会话及 checkpoint，最终控制台 `0 errors / 0 warnings`。
6. Web Nginx `/api` 反向代理到 API 成功，client error 接收接口返回 `received=true`。
7. 最终 Web 镜像创建 run `5fbd2e85535543daa292f377cd659245`，在 1037×767 视口验证长 run ID 与统计卡无重叠；登录页 favicon 404 已消失，最终控制台 `0 errors / 0 warnings`。

浏览器证据：

- [聊天主页](../../../output/playwright/r1-chat-home.png)
- [开发任务](../../../output/playwright/r1-development-tasks.png)
- [调度暂停并持久化](../../../output/playwright/r1-scheduler-paused.png)
- [Skill 持久化](../../../output/playwright/r1-skill-persisted.png)
- [聊天运行](../../../output/playwright/r1-chat-run.png)
- [运行台 1037px 最终视觉复验](../../../output/playwright/r1-run-console-final-1037.png)
- [侧栏点击恢复会话](../../../output/playwright/r1-session-click-restored.png)
- [完整刷新恢复会话](../../../output/playwright/r1-session-reload-restored.png)

## 竞品差距收敛

| 对标面 | 本阶段状态 | 证据边界 |
| --- | --- | --- |
| Codex：隔离开发任务、Git 产物、review/apply/conflict/rollback | 已收敛 | 持久任务模型、显式确认、worktree/branch/commit/full patch、容器 Git 与生命周期测试。 |
| Codex：运行证据、审批与 MCP 操作面 | 已收敛 | 15 个租户受控 MCP 工具、run/evidence/checkpoint 浏览器链。 |
| Hermes：持久调度、暂停/恢复、重试 | 已收敛 | 数据库 job/run、租约、恢复和刷新后状态保持。 |
| Hermes：完整技能包 | 已收敛 | SKILL.md、references、scripts、assets、manifest/hash、运行时正文与租户门禁。 |
| Hermes：会话/运行恢复 | 已收敛 | 数据库 checkpoint、父子 run、点击和完整刷新恢复。 |

仍未纳入本阶段发布结论的差距：桌面原生体验、多机高可用、E2B 托管 sandbox、客户现场部署演练、短剧业务以及真实付费模型供应商验收。它们不是本轮 Web/API 候选的隐含已完成功能。

## 发布边界

- 当前可作为 Web/API `v1.0.0` 发布候选进入人工发布审批。
- 未创建或移动 tag，未 push，未部署生产，未写入外部或付费服务。
- 正式发布前仍应按部署环境注入非默认管理员凭据和 production secrets；lite `admin/admin` 仅用于本地浏览器验收。
