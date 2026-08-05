# R21 Candidate Freeze + R4/R5 Closure Checklist

> 日期：2026-07-07
> Owner：Claude Code
> 范围：把“候选冻结 + R4 演练 + R5 审查包”收敛为一份可直接执行的闭环清单，不替代实际演练与 reviewer 验收。

---

## 1. 目的

当前仓库已经完成本地质量基线验证：

- 前端 `lint/typecheck/build` 通过
- 后端 `ruff/pytest` 通过
- Python 许可证门禁通过

但正式进入可送审 / 可发布候选前，仍存在三道未闭环的门：

1. **候选未冻结**
2. **R4 目标环境 / full-mode 演练未完成**
3. **R5 PR 审查包无法签发**

R21 的目标是把这三道门拆成：

- 当前事实
- 前置依赖
- 执行动作
- 验收产物
- 未完成时不得越界宣称的边界

---

## 2. 当前事实快照

### 2.1 候选状态

当前本地工作树：

- `HEAD`: `a98cea09506243ca2b585029c2c5b677f172845c`
- 分支状态：`master...origin/master [ahead 1, behind 2]`
- 本地存在大量 tracked / untracked 改动

结论：

> **当前本地工作树不是已冻结候选。**

PR #6 / `d59faa3` 的远端 CI 仍有效，但**只对该候选有效**，不能覆盖当前本地工作树。

来源：

- `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
- `docs/coordination/TASK_BOARD.md`

### 2.2 R4 状态

当前 R4 仍 BLOCKED，原因已明确：

- 缺 `LANGFUSE_NEXTAUTH_SECRET`
- 缺 `LANGFUSE_SALT`
- 缺 `LANGFUSE_INIT_USER_PASSWORD`
- 缺 full-mode 显式账号
- compose 依赖端口未监听
- 尚未绑定一条 full-mode LLM 路径

结论：

> **当前只有 lite/dev 级证明，不能等同于 full-mode / staging 演练完成。**

来源：

- `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
- `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- `docs/coordination/TASK_BOARD.md`

### 2.3 R5 状态

R5 当前 BLOCKED，依赖：

- `R4` 完成至少一次目标环境或 staging 等价演练并归档
- `R8` 对外口径终检通过验收
- 候选与远端 CI 的对应关系清晰

结论：

> **现在可以准备 R5 的输入源数据，但不能把 R5 当作已可签发的 reviewer 包。**

来源：

- `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- `docs/coordination/TASK_BOARD.md`

---

## 3. 闭环总览

| 阶段 | 当前状态 | 阻塞点 | 解除条件 | 输出物 |
|---|---|---|---|---|
| 候选冻结 | 未完成 | 当前工作树未冻结；PR #6 CI 不覆盖当前 HEAD | 固定 branch/commit/范围并取得对应远端 CI | frozen candidate record |
| R4 演练 | BLOCKED | secret、账号、端口、依赖、LLM 路径未补齐 | full-mode / staging 等价环境实际拉起并归档证据 | rehearsal evidence bundle |
| R5 审查包 | BLOCKED | 缺 R4 证据、R8 reviewer 结论、候选绑定 | 完成候选冻结 + R4 + 关键 REVIEW 验收 | reviewer-ready PR package |

---

## 4. 第一门：候选冻结清单

### 4.1 必须先确认的事

- 本次交付到底包含哪些 tracked 改动？
- 哪些 untracked 文件属于交付内容，哪些只是日志 / 临时产物？
- 本次交付是否要把 `docs/coordination/`、frontend 变更、deploy 变更、E2E 变更一起纳入？

### 4.2 执行动作

1. 选定候选范围
   - 明确“纳入交付”的目录/文件清单
   - 明确“不纳入交付”的日志、快照、临时产物

2. 固定候选
   - 创建或选择唯一候选分支
   - 固定唯一候选 commit
   - 记录候选 branch / commit / 负责人 / 时间戳

3. 绑定远端 CI
   - push 候选分支
   - 获取新的远端 CI run
   - 确认 backend / frontend / license-gate / 其他所需门禁覆盖该候选

### 4.3 验收产物

至少要有：

- 候选 branch 名
- 候选 commit sha
- 远端 CI run URL / run id
- 当前候选包含范围说明
- “哪些本地改动未进入候选”的说明

### 4.4 未完成前禁止宣称

在候选冻结完成前，不得宣称：

- 当前工作树就是最终发布候选
- 当前远端 CI 已覆盖本地全部收尾内容
- R5 已具备正式 reviewer 输入

---

## 5. 第二门：R4 演练闭环清单

### 5.1 前置输入

R4 恢复执行前，至少补齐：

- `XAGENT_SECURITY__JWT_SECRET`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_SALT`
- `LANGFUSE_INIT_USER_PASSWORD`
- full-mode 显式账号来源
- 至少一条 LLM 路径（Ollama / LiteLLM / provider）
- compose 依赖端口与服务准备状态

### 5.2 执行动作

按 R16/R19/U2 组合路径执行：

1. 生成 `.env.rehearsal`
2. `docker compose --env-file .env.rehearsal config --quiet`
3. 对当前候选重新生成 `apps/web/dist`
4. 拉起依赖服务
5. 拉起 `api/worker/web`
6. 记录启动日志
7. 跑 `/health`、`/ready`、web root smoke
8. 用 full-mode 显式账号跑 `creative-smoke`
9. 如需更强证据，再跑 `full-flow`

### 5.3 必要归档证据

- compose config 输出
- compose ps 输出
- api / worker / web 日志
- `/health` 与 `/ready` 输出
- full-mode 登录证据
- Playwright 结果
- 若有 DB 迁移：Alembic 输出与备份路径

### 5.4 R4 完成定义

满足以下条件才能说 R4 完成：

- 目标环境或 staging 等价环境**实际启动成功**
- full-mode 显式账号登录成功
- 至少一组关键 smoke/E2E 成功
- 证据已归档且可被 reviewer 找到

### 5.5 未完成前禁止宣称

- 已完成 full-mode 演练
- 已完成 staging 等价验收
- 本地 lite/dev 页面证据可直接替代 R4

---

## 6. 第三门：R5 审查包闭环清单

### 6.1 R5 的最小输入

R5 应至少包含：

- 候选 branch / commit / 远端 CI 对应关系
- 风险摘要
- 本地验证矩阵
- R4 演练证据入口
- R8 / R14 / R15 / R16 / R17 / R18 / R19 等相关证据入口
- reviewer 关注点
- 明确剩余风险与不在本次发布范围的事项

### 6.2 需要先确认的 REVIEW gate

R5 组装前，至少要检查这些状态：

- R8：对外口径一致性终检
- R14：Vite chunk 拆包证据
- R15：证据一致性同步
- R16：full-mode 演练前置清单
- R17：PR 证据矩阵源数据
- R18：候选新鲜度审计
- R19：无密交接模板

注意：

> 这些包即便已有证据，只要仍是 REVIEW，就不能自动等价为 DONE。

### 6.3 R5 完成定义

只有在以下条件满足时，R5 才能从 BLOCKED 转为可签发：

- 已冻结真正候选
- 该候选已有对应远端 CI 绿证据
- R4 已完成至少一次目标环境 / staging 等价演练并归档
- R8 与关键 REVIEW 包已由 reviewer / 总调度确认
- PR 审查包正文、验证矩阵、风险摘要、证据链接齐全

### 6.4 未完成前禁止宣称

- R5 已可直接送审
- PR 包已具备正式发布签字条件
- 所有 readiness gate 都已关闭

---

## 7. 建议执行顺序

### 路径 A：最稳妥
1. 冻结候选
2. 推送并取得新远端 CI
3. 补齐 R4 secret / 账号 / LLM / 依赖
4. 完成 R4 演练并归档
5. 验收关键 REVIEW 包
6. 组装 R5

### 路径 B：并行准备
可并行进行：

- 候选范围梳理
- `.env.rehearsal` 输入收集
- R5 结构框架预写
- REVIEW 包预验收清单整理

但真正签发顺序不能跳过：

> 候选冻结 → R4 实跑 → R5 签发

---

## 8. 当前最小行动建议

如果现在继续推进，我建议按这个最小行动集执行：

1. **先冻结候选范围**
   - 否则所有后续证据都无法稳定绑定到同一版本。

2. **让环境/发布负责人填写 R19 并提供 R4 输入**
   - 这是恢复 R4 的最短路径。

3. **基于冻结候选重跑远端 CI**
   - 否则无法给 R5 建立可信 CI 对应关系。

4. **完成 R4 演练后再组装 R5**
   - 这样 PR 审查包才不会天然带着“关键证据缺失”的硬伤。

---

## 9. 一句话总结

> 当前本地质量基线已经通过，但离“可送审 / 可发布候选”仍差三步：**冻结候选、完成 R4、签发 R5**；R21 的作用就是把这三步从口径收敛成可执行清单。
