# Claude Code × Codex 协作入口

> 适用范围：`xagent` 当前 readiness 收口阶段。  
> 目标：让 Claude Code 与 Codex 在同一仓库下共享同一任务板、同一任务包协议、同一验收语义，持续推进后续工作。

---

## 1. 先读什么

任何会话开始工作前，固定按这个顺序读取：

1. [README.md](../../README.md)
2. [COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md](../COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md)
3. [COMMERCIAL_RELEASE_CHECKLIST_V1.md](../COMMERCIAL_RELEASE_CHECKLIST_V1.md)
4. [TASK_BOARD.md](./TASK_BOARD.md)
5. [TASK_PACKAGE_PROTOCOL.md](./TASK_PACKAGE_PROTOCOL.md)
6. [EXECUTION_LIVE_OUTPUT_PROTOCOL.md](./EXECUTION_LIVE_OUTPUT_PROTOCOL.md)
7. [reports/delivery-report.md](./reports/delivery-report.md)

禁止跳过 `TASK_BOARD.md` 直接开工。

---

## 2. 当前目标

当前不是扩功能，而是完成 readiness 收口，形成：

- 可冻结的发布范围
- 可验证的修复包
- 可复核的证据链
- 可判断是否进入 PR / 是否可发布的统一门禁

当前 P0 收口重点：

1. orchestration await bug
2. 前端 lint 阻断
3. preview / demo / fallback 污染
4. 商用危险默认值
5. CI 最小门禁
6. 真实状态文档对齐

---

## 3. 角色分工

### Claude Code

适合：

- 仓内实现
- 本地验证
- 多文件修复
- 文档与门禁收口
- 总调度 / gate 判定

### Codex

适合：

- 领取边界清晰的任务包
- 并行推进独立修复
- 按协议补证据和回填交付
- 执行只读验证矩阵

两者都必须：

- 只从任务板领取任务
- 使用同一任务卡格式
- 完成后回填证据
- 未附证据不得转 `REVIEW`

---

## 4. 协作规则速记

- 先领取，再改动
- 一包一责任人
- 跨包修改，必须在任务板显式声明
- 未附证据，不得转 `REVIEW`
- 阻塞超过 30 分钟，必须写入 `Blocked`
- 文档 / 配置 / 门禁变化必须同步回填
- 不允许口头说“差不多可以发了”，只能给 gate 结论和证据

---

## 5. 文档关系

- `README.md`：项目总入口
- `COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`：真实状态唯一事实源
- `COMMERCIAL_RELEASE_CHECKLIST_V1.md`：发布阻断门禁
- `TASK_BOARD.md`：共享调度面
- `TASK_PACKAGE_PROTOCOL.md`：领取 / 实施 / 交付 / 验收协议
- `EXECUTION_LIVE_OUTPUT_PROTOCOL.md`：执行会话 live 状态暴露协议
- `reports/delivery-report.md`：交付记录沉淀

---

## 6. 当前建议工作方式

1. 进入任务板，只领取 `READY` 的任务包
2. 改动前先把任务卡改成 `CLAIMED`
3. 开始实现后把状态改成 `IN_PROGRESS`
4. 完成自测和证据回填后改成 `REVIEW`
5. 验收通过后改成 `DONE`
6. 如果发现范围失真，先回板拆包，不允许隐式扩大范围
7. 如果当前没有可领取任务，不要直接退出会话；保持驻留，按固定间隔重读 `TASK_BOARD.md`，直到领取到新任务或阶段明确结束
8. **不要等任务完全跑空再补单**：总调度应在执行包进入 `IN_PROGRESS` / `REVIEW` 时，就提前从剩余风险、reviewer 关注点、发布门禁里拆下一批包，保证执行会话连续有事可做

## 7. 无人中转前提

要实现“用户不做人肉中转”，必须满足三个条件：

1. **任务板是唯一通信总线**：任何状态变化、证据、阻塞、恢复条件都必须写入仓库文档。
2. **主调度必须自动拆解补单**：当执行会话做完任务、进入阻塞、或可领取任务水位过低时，总调度必须主动从既有事实源抽取下一批任务，避免 Claude Code 或 Codex 空转。
3. **执行会话必须自循环驻留**：会话不能在完成一个任务后直接停止；若没有 `READY` 任务，应按固定周期重新读取任务板并等待下一包。

这意味着：

- 文档总线可以替代消息中转
- 任务补单必须由主调度持续维护，而不是等用户再次分派
- 文档总线本身不会唤醒已经退出的会话
- 若执行会话已经停止，总调度必须先回收占用，再由存活会话接管或等待新的执行会话启动

## 8. 持续补单规则

主调度必须维持以下水位：

- **至少 2 张 Codex 可领取的 `READY` 卡**
- **至少 1 张 Claude Code 当前卡 / 解阻卡**

当出现以下任一情况时，立即补单：

1. `READY` 中 Codex 可领取任务少于 2 张
2. Claude Code 没有当前卡或解阻卡
3. 有任务进入 `DONE`
4. 有任务进入 `BLOCKED`
5. `delivery-report.md` 新增一节并暴露新的剩余风险

补单时优先从这些来源抽取新任务：

1. `docs/coordination/reports/delivery-report.md`
2. `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
3. `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
4. `docs/superpowers/plans/2026-07-05-commercial-readiness-execution-plan.md`
5. 已完成或待审任务的 `剩余风险` / `Reviewer 关注点`（例如未覆盖的 full-flow E2E、npm audit 风险、bundle 告警、SQLite/Alembic 漂移、页面截图验收缺口）
6. 任务板与交付记录之间的状态 / 证据漂移（例如任务板缺少 R13/R14 状态、交付证据已完成但任务卡未同步）
7. `docs/coordination/README.md` 与 `TASK_PACKAGE_PROTOCOL.md`（仅用于协议修正规则卡）

## 9. 收尾阶段等待规则

进入最终收尾阶段后，执行会话出现“等待”并不自动等于停滞。只有同时满足以下条件时，才判断为真正停滞：

1. 没有 `READY` 任务可领取；
2. 当前 `IN_PROGRESS` / `REVIEW` 任务没有人在推进或没有新证据；
3. 总调度也没有补出新的解阻包或后续包；
4. 阻塞条件没有被结构化写回任务板。

如果只是因为 gate 依赖未满足而暂时等待，且：
- 当前任务状态清楚，
- 阻塞原因明确，
- 恢复条件明确，
- READY 水位已提前补齐，
则这属于**依赖门控等待**，不是协调故障。

## 10. 让执行会话把状态主动展示给总调度

为了让总调度及时了解执行会话的真实状态，而不是只依赖任务板状态变化，每个执行会话在推进任务时必须把以下内容显式写入仓库：

1. **任务板状态**：`CLAIMED / IN_PROGRESS / BLOCKED / REVIEW / DONE`
2. **交付记录**：`delivery-report.md` 中的一包一节
3. **结构化问题记录**：当任务被退回、阻塞、或发现边界漂移时，必须把“问题 -> 原因 -> 影响 -> 下一步”写入对应交付节或专门报告文件
4. **恢复条件**：如果无法继续，不只写“卡住了”，还要写清楚恢复所需的 secret、账号、服务、命令或外部决策

总调度优先读取：
- `docs/coordination/TASK_BOARD.md`
- `docs/coordination/reports/delivery-report.md`
- 任务包专属报告（如 `R10_FULL_FLOW_E2E_TRIAGE.md`、`R16_FULL_MODE_REHEARSAL_PREP.md`）

原则：
- 不要求执行会话把全部推理过程都写出来
- 但要求它把总调度真正需要的状态、问题、风险、恢复条件写出来
- 若这些内容不落盘，总调度就无法准确判断当前是推进、阻塞、退回，还是可送审
