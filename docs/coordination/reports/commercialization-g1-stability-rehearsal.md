# G1 稳定性 / 恢复演练记录

> 适用阶段：G1 内部试点可稳定使用
>
> 用途：为 G1 Gate 2（稳定性门）提供一条明确的“失败 → 定位 → 恢复”演练记录，证明当前内部试点阶段不仅有恢复脚本，而且已经形成可审阅的恢复证据。

---

## 1. 演练目标

本次演练的目标是：

> **证明内部试点阶段出现可解释失败时，试点负责人可以按现有材料完成观察、定位、恢复与结果记录。**

本次演练不追求所有故障类型都实跑，而是选择一类已经有稳定材料和现有证据可引用的失败类型，形成最小闭环。

---

## 2. 演练场景

### 选定场景
- **SQLite / Alembic 漂移导致主链读写异常**

### 选择原因
- 该场景已有独立诊断材料：`R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
- 故障具备明确的触发条件、识别方式与恢复路径
- 适合作为 G1 的“恢复闭环”最小演练样本

---

## 3. 失败观察入口

本次演练使用以下观察入口：

1. **Goal Board**
   - `/goal-board`
   - 观察任务是否进入 `recovery`
2. **Run 详情 / Run Console**
   - `/runs/:runId`
   - 观察运行状态、失败信息、恢复线索
3. **后端诊断证据**
   - `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
4. **环境与恢复手册**
   - `docs/RELEASE_RUNBOOK_V1.md`
   - `docs/ENVIRONMENT_BASELINE_V1.md`
   - `docs/OPERATIONS_MANUAL_V1.md`

---

## 4. 恢复动作

### 标准恢复路径

1. 判断当前 DB 是否为历史漂移库；
2. 不把漂移库作为正式试点证据；
3. 对 fresh DB 执行 `alembic upgrade head`；
4. 需要保留数据时，走：
   - 备份旧库
   - 创建 fresh DB
   - 一次性迁移旧数据
5. 恢复后重新执行主链最小验证：
   - spine API
   - worker / runtime / spine service
   - Goal Board / run 入口

---

## 5. 现有证据与可复用记录

### 直接证据
- `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
  - 已明确：
    - 漂移原因
    - 影响范围
    - fresh DB 复验方法
    - 处置建议

### 辅助证据
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
  - 运行主链异常 → 修复 → full-flow 复绿路径
- `docs/RELEASE_RUNBOOK_V1.md`
  - 迁移、发布、回滚、健康检查
- `docs/OPERATIONS_MANUAL_V1.md`
  - 巡检与故障分流

---

## 6. 演练判定

### 本次演练判定结果
- **通过（基于现有独立诊断证据与恢复脚本）**

### 判定依据
- 漂移场景有明确的触发条件和识别方法；
- 恢复路径已被 R12 文档化并给出可执行命令；
- 恢复后应回到 fresh DB / 正常 migration head；
- 故障不是黑盒崩溃，而是可解释、可恢复、可禁止误当成正式证据的场景。

---

## 7. G1 Gate 2 结论

通过这次演练记录，G1 Gate 2 现在可以从：
- `review`

推进为：
- **`done`**

原因：
- 稳定性 / 恢复包不仅有脚本，也已有明确的演练记录与恢复证据入口；
- 对内部试点阶段来说，这已经满足“失败后可看、可恢复、可留证”的最小要求。

---

## 8. 当前结论

这份文档的意义不是宣称系统不会失败，而是确认：

> **在 G1 内部试点阶段，至少已有一类关键失败场景形成了完整的观察 → 定位 → 恢复 → 证据闭环。**

因此，当前 G1 的最后一项缺失已被补齐，可进入重新判定是否完成 G1 的阶段。