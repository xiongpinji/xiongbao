# X-Agent 正式商用 GA 收口设计

- 日期：2026-07-23
- 目标：将当前可内部试点 / 受控私有部署状态收口为正式商用 GA
- 首发范围：方案 A
- 发布形态：单实例 Docker Compose `full`
- 环境证据：可复现的 staging Compose `full` 演练
- 发布策略：先完成门禁，再生成版本候选、发布签字与 GA 材料

## 1. GA 首发范围

### 纳入

- Web 工作台：登录、对话、智能体、工作流、Run Console、设置
- 短剧工厂自由画布及其工作流执行
- 企业鉴权、RBAC、租户隔离、审计
- API、worker、web 的 Docker Compose `full` 部署
- Postgres、Redis、Qdrant、Langfuse/LiteLLM 声明的依赖链
- 至少一条真实 LLM、一个图像 provider、一个视频 provider

### 不纳入

- Helm/Kubernetes 平台化及 enterprise secretRef
- Tauri 桌面端正式交付
- 多实例 HA、多地域部署、SaaS 级容量承诺
- 实验性 provider 的厂商级兼容承诺
- 跨多个历史版本的数据库直接升级

## 2. GA 硬门禁

任一 P0 门禁未通过，不得发布 GA。

### P0-A：候选与范围冻结

- 建立独立 GA 发布分支、版本号和 Git tag 计划
- 工作区清洁；未提交改动必须明确排除或纳入候选
- 首发页面、接口、能力域和明确不支持范围冻结
- README、状态事实源、ROADMAP、已知问题和交付索引口径一致
- 当前候选的远端 CI 证据与候选提交一一对应

### P0-B：安全与密钥

- 立即轮换工作区中暴露过的 DeepSeek、图像和视频 provider key，并确认旧 key 失效
- 任何 staging/prod secret 不进入 Git、构建产物、日志和截图
- `full` 模式拒绝弱 JWT secret、关闭鉴权、通配 CORS 和默认管理员
- Compose 启动要求显式 JWT、Langfuse、数据库和必要 provider secret
- 安全扫描验证鉴权、租户隔离、SQL 注入防护、限流和安全响应头
- 数据库、Redis、Qdrant 不直接公网暴露；明确 HTTPS/TLS 终止位置

### P0-C：质量门禁

后端：

- `ruff check xagent tests` 通过
- `mypy xagent --ignore-missing-imports` 通过，不允许 `|| true` 吞错
- `PYTHONPATH` 或可编辑安装后的 `pytest -q` 入口可直接复现
- pytest 全部通过，无未解释失败和超时

前端：

- `npm run lint` 通过
- `npm run typecheck` 通过
- `npm run build` 通过

集成：

- 关键 Playwright E2E 覆盖登录、对话/SSE、运行详情、工作流、短剧画布和设置
- E2E 在 staging Compose full 环境通过
- 许可证门禁和生产依赖审计通过；dev 工具链风险有明确处置结论

### P0-D：staging Full 演练

使用全新 staging 环境和显式 secret 完成：

1. Compose 配置校验与从零部署
2. Postgres/Redis/Qdrant/Langfuse/LiteLLM/worker 健康检查
3. 显式账号登录和权限验证
4. 文本主链、工作流、Run Console、短剧画布执行
5. 真实 LLM、图像 provider、视频 provider 调用
6. 失败、重试、恢复和日志排障演练
7. 发布后 smoke 验收
8. 相邻 GA 版本升级、迁移和回滚演练

必须归档命令输出、版本信息、配置摘要、日志、截图和结果，不得以本地 lite 证据替代。

### P0-E：数据恢复

- Postgres、Qdrant、审计数据具备备份方案
- 完成真实备份与恢复演练
- RPO ≤ 24 小时
- RTO ≤ 4 小时
- 记录恢复步骤、耗时、数据完整性和责任人
- GA 只承诺相邻 GA 版本升级；升级前必须备份，失败可回滚

### P0-F：容量与运行基线

在单实例 Compose 环境完成 50 并发负载测试并记录：

- API P95 延迟
- 错误率
- 429 限流比例和触发阈值
- worker backlog、任务耗时和失败率
- LLM、Redis、Qdrant、数据库的主要瓶颈
- 明确超出基线后的行为和扩容建议

### P0-G：交付与支持签发

- 管理员部署、运维、升级/回滚、备份恢复、已知问题和边界文档齐全
- 定义健康检查、指标、日志、Langfuse trace 和告警责任人
- P0 事件：30 分钟响应，4 小时内给出恢复方案
- P1 事件：4 小时响应
- 完成 PR/release review package
- TL、QA、DevOps、Owner 分别基于证据签字

## 3. 任务分层与依赖

### 阶段 0：候选清理与安全止血

依赖：无。必须最先完成。

- 轮换并撤销已暴露 provider key
- 标记或清理工作区未跟踪/未提交产物
- 建立 GA release 分支和候选范围清单
- 统一互相矛盾的 GA / 试点状态文档
- 修复 CI 中吞掉 mypy 失败的门禁逻辑

出口：无活动密钥暴露、范围冻结草案、质量门禁真实失败可见。

### 阶段 1：代码质量与可复现验证

依赖：阶段 0 的范围确定。

- 修复当前 16 个 mypy 错误
- 修正 pytest 直接入口，使文档命令可复现
- 固化后端、前端、许可证和依赖审计命令
- 补齐关键 E2E 和安全扫描脚本的 staging 参数化

出口：本地全套门禁通过，且命令无需临时手工环境修补。

### 阶段 2：Staging Compose full 验收

依赖：阶段 1。

- 准备隔离 staging 主机、域名/TLS 或明确终止方案
- 通过 secret manager/CI secret 注入配置
- 从零启动全依赖链并保存证据
- 验收核心链路、真实 provider、失败恢复和安全边界
- 完成 Playwright、security scan 和发布 smoke

出口：形成完整 R4 类演练包，所有关键链路有可追溯证据。

### 阶段 3：恢复、升级与容量

依赖：阶段 2 已有可用 staging 数据。

- 执行 Postgres/Qdrant/审计备份恢复
- 执行相邻版本升级、迁移和回滚
- 执行 50 并发负载测试
- 形成 RPO/RTO、P95、错误率、backlog 和容量边界报告

出口：恢复、升级、回滚和容量四类报告通过负责人复核。

### 阶段 4：发布包与 GA 签发

依赖：阶段 0-3 全部出口通过。

- 生成版本 manifest、变更说明和兼容性声明
- 组装 PR/release evidence matrix
- 清理并重新验证候选 tag 的 CI
- 完成支持联系人、升级路径和事件响应材料
- TL/QA/DevOps/Owner 签字
- 发布 GA tag；发布后执行 smoke 和观察窗口

出口：GA 发布包可由管理员独立部署、验证、升级、回滚和求助。

## 4. 失败处理规则

- 任一 P0 失败，候选回到对应阶段，不得以文档声明覆盖运行证据
- staging 与本地结果冲突时，以 staging full 结果为准
- 发现 secret 泄露时立即停止发布，先撤销/轮换，再重新执行受影响验证
- 发现数据迁移不可逆或回滚失败时，暂停 GA，恢复到备份并重新设计迁移
- 50 并发未达到基线时，只能降低并公开承诺范围，不得默认为通过
- 未签字的 REVIEW 证据不计入 GA 通过条件

## 5. GA 通过判定

只有同时满足以下条件，才允许对外称为正式商用 GA：

1. P0-A 至 P0-G 全部通过
2. staging Compose full 演练完整归档
3. 所有关键质量、安全、恢复、升级和容量报告无未解释阻断项
4. 版本 tag 与所有证据提交一致
5. 四类发布角色完成签字

否则口径只能是：**内部试点可用**或**受控私有部署候选**。

## 6. GA 后明确不承诺

- 多实例 HA、多地域容灾和 SaaS 级规模
- Helm/Kubernetes secretRef 平台化
- Tauri 桌面端正式分发
- 跨多个历史版本直接升级
- 超过 50 并发基线的固定 SLA
- 未列入验收矩阵的 provider 厂商兼容性
