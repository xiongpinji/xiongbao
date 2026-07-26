# G1-A1 功能链路包

> 适用阶段：G1 内部试点可稳定使用
>
> 用途：冻结一条内部试点阶段的标准日常使用路径，让试点负责人、运维、接手者可以按同一条主链完成登录、进入工作台、查看 Goal Board、提交任务/工作流、查看运行结果与回放。

---

## 1. 目标

G1-A1 的目标是：

> **把当前 `xagent` 的内部试点高频主链冻结成一条可重复、可交接、可验证的功能路径。**

这条功能链路不追求覆盖所有能力，而是确保：

- 关键入口明确；
- 关键路径一致；
- 结果查看和回放可用；
- 现有证据与最小验证命令可直接复用。

---

## 2. 标准日常使用路径

### 2.1 登录

用户首先进入登录页，并使用当前试点环境允许的有效凭据完成登录。

目标：
- 成功获得可访问工作台的会话状态；
- 失败时可以明确区分“账号/凭据错误”和“环境未就绪”。

### 2.2 进入工作台入口

登录后，标准工作台入口按以下顺序理解：

1. `/chat`
2. `/goal-board`
3. `/runs/:runId`
4. `/settings`

含义：
- `/chat`：统一任务输入与主对话入口；
- `/goal-board`：当前交付目标、执行包和发布/恢复状态入口；
- `/runs/:runId`：运行详情、结果查看与回放入口；
- `/settings`：配置、索引、技能与环境说明入口。

### 2.3 Goal Board / task / workflow 入口

内部试点中的标准任务推进路径应按以下顺序理解：

1. 在 `/chat` 或工作流入口发起任务；
2. 在 `/goal-board` 观察当前目标、执行包和发布/恢复状态；
3. 通过 run id 进入 `/runs/:runId` 查看运行详情；
4. 必要时再回到 `/settings` 或材料包查看环境 / 边界 / 支持信息。

### 2.4 结果查看 / 回放

结果查看与回放的最小入口是：

- `/runs/:runId`

试点负责人应能在这个入口完成：
- 查看运行最终状态；
- 查看主要输出；
- 查看失败信息（若存在）；
- 回查运行关联上下文。

---

## 3. 固定入口路径

当前冻结的功能链路入口如下：

- `/chat`
- `/goal-board`
- `/runs/:runId`
- `/settings`

补充说明：
- 这些入口是 G1-A1 固定主链，不要求覆盖所有历史遗留页面；
- 任何不在上述链路中的页面，不视为当前内部试点主链的必验入口。

---

## 4. 现有证据入口

当前可直接复用的主链证据包括：

- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`
  - 关键页面视觉证据入口
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
  - Chat / SSE / full-flow 主链证据
- `docs/coordination/reports/auto-delivery-phase1-report.md`
  - Phase 1 验收报告模板入口

这些证据的作用是：
- 支持内部试点负责人快速判断主链是否存在明显退化；
- 为后续 G1-A2 稳定性 / 恢复包提供基础输入；
- 作为“当前主链曾被验证”的最小引用入口。

---

## 5. 最小验证命令

当前冻结的最小验证命令如下：

### 前端主链

```bash
cd apps/web
npm test -- goalBoard.test.tsx
```

预期：
- Goal Board 渲染通过；
- Release / Recovery 侧栏逻辑通过；
- 非 release `next_action` 不误显示到 release pane。

### 后端 Spine / 运行主链

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_spine_api.py tests/test_spine_session_resume.py tests/test_spine_release_flow.py -q
```

预期：
- Goal Board API、session 决策、release flow 相关测试通过。

### 运行时 / worker 主链

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_runtime_runs.py tests/test_spine_service.py -q
```

预期：
- worker、runtime、spine service 主链测试通过。

---

## 6. 完成定义

G1-A1 只有在以下条件同时成立时，才算完成：

- 登录、工作台入口、Goal Board、Run 详情入口的路径定义明确；
- 试点负责人可以按固定路径理解日常使用流程；
- Goal Board / run 主链的关键自动化验证可直接复用；
- 关键视觉/交互/运行证据有明确入口；
- 不需要开发者口头解释，接手者也能理解“内部试点的标准日常路径”。

---

## 7. 当前结论

G1-A1 不是新增产品能力，而是：

> **把已经存在的关键工作台、Goal Board、Run 详情与主链验证入口冻结成一条标准内部试点功能路径。**

后续若要继续推进 Phase 1，应在此基础上进入：
- `G1-A2 稳定性 / 恢复包`
- `G1-A3 数据 / 权限 / 审计包`
- `G1-A4 试点交付材料包`
