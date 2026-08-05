# G1-A4 试点交付材料包

> 适用阶段：G1 内部试点可稳定使用
>
> 用途：把当前 `xagent` 进入内部试点所需的管理员部署、运维值守、升级/回滚、已知问题、支持升级路径和阶段边界整理成一个最小可交付材料包，让试点负责人不需要开发者陪跑也能启动、值守并理解边界。

---

## 1. 目标

G1-A4 的目标是：

> **把当前已经存在的部署、运维、边界、升级与支持材料，整理成一套内部试点负责人可以直接拿来用的交付包。**

这不是正式商用 GA 的签发包，也不是企业级长期运营包；它只服务于内部试点与受控私有部署阶段。

---

## 2. 材料包组成

G1-A4 当前固定包含以下材料：

1. **管理员部署手册**
   - `docs/ADMIN_DEPLOYMENT_MANUAL_V1.md`
2. **运维手册**
   - `docs/OPERATIONS_MANUAL_V1.md`
3. **升级 / 回滚说明**
   - `docs/RELEASE_RUNBOOK_V1.md`
4. **已知问题 / 试点边界**
   - `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
5. **支持与故障升级路径**
   - `docs/SUPPORT_ESCALATION_PATH_V1.md`
6. **当前真实状态口径**
   - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
7. **Goal / 执行包入口**
   - `docs/coordination/reports/commercialization-goal-board.md`
8. **功能链路包**
   - `docs/coordination/reports/commercialization-g1-a1-functional-package.md`
9. **稳定性 / 恢复包**
   - `docs/coordination/reports/commercialization-g1-a2-stability-package.md`
10. **数据 / 权限 / 审计包**
    - `docs/coordination/reports/commercialization-g1-a3-data-governance-package.md`

---

## 3. 试点负责人如何使用

### 3.1 开始前先看

试点负责人建议按下面顺序阅读：

1. `COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
2. `KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
3. `commercialization-goal-board.md`
4. `commercialization-g1-a1-functional-package.md`
5. `commercialization-g1-a2-stability-package.md`
6. `commercialization-g1-a3-data-governance-package.md`
7. `ADMIN_DEPLOYMENT_MANUAL_V1.md`
8. `OPERATIONS_MANUAL_V1.md`
9. `RELEASE_RUNBOOK_V1.md`
10. `SUPPORT_ESCALATION_PATH_V1.md`

### 3.2 为什么按这个顺序

- 先看真实状态与试点边界，避免误以为当前就是正式 GA；
- 再看 Goal 板和 G1 的三个执行包，理解当前试点究竟冻结了哪些内容；
- 再看管理员、运维、回滚手册，进入实际部署和值守；
- 最后看升级路径，知道出问题该找谁、怎么升级。

---

## 4. 对试点负责人的最小承诺

当前材料包支持的最小承诺是：

- 可以按固定路径完成部署；
- 可以完成登录、工作台、Goal Board、run 主链的试点使用；
- 失败时可以按现有材料判断故障入口与恢复入口；
- 知道当前哪些能力已经 ready，哪些还不能按正式商用 GA 对外承诺。

当前材料包**不承诺**：

- 正式商用 GA 已完成；
- 多实例 HA 已完成；
- K8s / secretRef 平台化已完成；
- 全量 SLO / 容量 / 长期审计保留已冻结。

---

## 5. 最小交付检查

试点交付前，负责人至少检查：

### 5.1 版本与环境
- 当前候选 commit / branch 已记录；
- 环境基线和 secret 输入已确认；
- 不依赖默认管理员；
- 不依赖危险默认值。

### 5.2 主链可用性
- 登录路径可用；
- `/chat`、`/goal-board`、`/runs/:runId`、`/settings` 入口已知；
- 关键测试命令已知；
- 现有主链证据入口已知。

### 5.3 故障处置
- 试点负责人知道从哪里看 Goal Board / Run Console / 日志；
- 知道升级 / 回滚手册在哪里；
- 知道联系谁升级问题；
- 知道当前哪些问题仍属于已知边界。

---

## 6. 最小验证命令

### 6.1 前端验证

```bash
cd apps/web
npm test -- goalBoard.test.tsx
```

### 6.2 后端主链验证

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_spine_api.py tests/test_spine_session_resume.py tests/test_spine_release_flow.py -q
```

### 6.3 worker / service / 恢复验证

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_runtime_runs.py tests/test_spine_service.py -q
```

### 6.4 环境健康检查

```bash
curl -f http://localhost:8000/health
curl -f http://localhost:8000/ready
curl -f http://localhost:3000
```

---

## 7. 完成定义

G1-A4 只有在以下条件同时成立时，才算完成：

- 试点负责人可以按固定入口拿到整套材料；
- 试点负责人不需要开发者口头解释，就能知道应该先看什么；
- 已知问题、试点边界、支持升级路径都在同一交付包内；
- 当前 G1-A1 / G1-A2 / G1-A3 的成果都已被纳入材料索引；
- 材料包明确说明“当前是内部试点阶段，而不是正式商用 GA”。

---

## 8. 当前结论

G1-A4 的作用不是新增手册，而是：

> **把当前已经存在的部署、运维、恢复、边界与支持材料收成一套真正可交接的内部试点交付包。**

当 G1-A1、G1-A2、G1-A3、G1-A4 全部具备后，`G1 内部试点可稳定使用` 就具备进入阶段 Gate 评估的基础。