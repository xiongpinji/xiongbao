# R27 Decided Freeze Scope Memo

> 日期：2026-07-07
> Owner：Claude Code
> 决策来源：按 R26 默认建议固化
> 范围：将当前候选冻结前的范围拍板结果固定为一份“已决范围说明”。
> 边界：本文件记录已决范围，不等于已经完成 branch / commit / CI 级冻结。

---

## 1. 已决结论

当前按默认建议固化后的冻结范围决策如下：

| 决策项 | 结果 |
|---|---|
| `ci.yml` 是否随本轮候选一起冻结？ | **YES** |
| `deploy/helm/templates/deployment.yaml` 是否进入本轮候选？ | **NO** |
| `deploy/helm/values.yaml` 是否进入本轮候选？ | **NO** |
| `deploy/keycloak/xagent-realm.json` 是否进入本轮候选？ | **NO** |
| `R16_FULL_MODE_REHEARSAL_PREP.md` 是否作为扩展审查包附带？ | **NO** |
| `R17_PR_EVIDENCE_MATRIX_SOURCE.md` 是否作为扩展审查包附带？ | **NO** |
| `R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md` 是否作为扩展审查包附带？ | **NO** |
| `R9_KEY_PAGE_VISUAL_EVIDENCE.md` 与截图目录是否附带？ | **NO** |
| `tests/e2e/specs/r9-visual-evidence.spec.ts` 是否进入本轮候选？ | **NO** |
| 本轮是否采用“最小可送审候选”而不是“完整内部 dossier”？ | **YES** |

---

## 2. 这意味着什么

### 2.1 本轮候选将包含

- 真实产品代码
- 当前配套测试
- 必要静态资源
- 关键 CI 定义（`ci.yml`）
- compose 路径下的核心运行配置
- 最小 release/readiness 文档主干

### 2.2 本轮候选将不会包含

- Helm 主模板与 values
- Keycloak realm 配置
- 扩展证据型文档（R16 / R17 / R19）
- R9 视觉验收文档与截图目录
- `r9-visual-evidence.spec.ts`
- 所有已明确排除的日志、snapshot、一次性审计记录、过程性文档

### 2.3 本轮候选的定位

这次冻结目标不是“完整内部 dossier”，而是：

> **一个最小可送审候选**

它的作用是：
- 先形成可绑定 branch / commit / 远端 CI 的主干候选；
- 为后续 R4 / R5 提供稳定输入；
- 避免在真正冻结前把扩展证据与额外部署边界一并打包。

---

## 3. 由此导出的下一步动作

既然范围已经拍板，下一步就不再讨论“哪些该进候选”，而是进入实际冻结前执行：

1. 按 R25 的精确暂存清单形成 staged candidate
2. 确认 staged set 中没有排除项
3. 固定 branch
4. 形成唯一 commit
5. push 到远端
6. 绑定新的远端 CI

也就是说，接下来可以直接把以下文档视为执行链：

- `R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`
- `R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`
- **本文件 R27_DECIDED_FREEZE_SCOPE_MEMO.md**

---

## 4. 当前仍未变化的边界

即使范围已决，也仍然不能宣称：

- 候选已经冻结完成
- 当前已有新的远端 CI 绑定
- R4 已完成
- R5 已可签发
- 当前工作树已经等同于正式发布候选

因为这些都还需要真正执行：

> staged → branch → commit → push → CI → R4 → R5

---

## 5. 一句话结论

> 当前“该不该进候选”的边界已经按默认建议拍板完成；接下来不再需要继续讨论范围，而应直接进入真正冻结前的 staged candidate 执行步骤。
