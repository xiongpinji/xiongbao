# R26 YES-NO Decision Sheet For Candidate Freeze

> 日期：2026-07-07
> Owner：Claude Code
> 范围：把最小候选冻结前仍未决的范围问题压缩成一份可直接拍板的 YES / NO 清单。
> 边界：本文件只收敛决策问题，不执行冻结动作本身。

---

## 1. 使用方式

这份清单的目的不是再做分析，而是让负责人快速拍板。

建议用法：

- 对每一项只给出 **YES / NO**
- 默认建议已经给出；若不同意，再显式改成相反结论
- 所有项拍板后，就可以把 R25 的“精确暂存清单”变成真正冻结动作输入

---

## 2. YES / NO 拍板清单

| # | 决策项 | 默认建议 | YES 的含义 | NO 的含义 |
|---|---|---|---|---|
| 1 | `ci.yml` 是否随本轮候选一起冻结？ | **YES** | 本轮候选的远端 CI 定义与候选代码保持一致 | 沿用旧 CI 定义，不把本地 CI 改动算进候选 |
| 2 | `deploy/helm/templates/deployment.yaml` 是否进入本轮候选？ | **NO** | 本轮候选扩大到 Helm 主部署模板 | Helm 主模板暂不进入本轮候选 |
| 3 | `deploy/helm/values.yaml` 是否进入本轮候选？ | **NO** | 本轮候选对 Helm values 负责 | Helm values 暂不进入本轮候选 |
| 4 | `deploy/keycloak/xagent-realm.json` 是否进入本轮候选？ | **NO** | 本轮候选把 Keycloak realm 配置一并冻结 | Keycloak realm 暂不进入本轮候选 |
| 5 | `R16_FULL_MODE_REHEARSAL_PREP.md` 是否作为扩展审查包附带？ | **NO** | reviewer 可直接看到 R4 前置清单 | 仅在需要时引用，不进入最小送审包 |
| 6 | `R17_PR_EVIDENCE_MATRIX_SOURCE.md` 是否作为扩展审查包附带？ | **NO** | reviewer 可直接看到 R5 源数据矩阵 | 保留为内部 source-data，不进最小送审包 |
| 7 | `R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md` 是否作为扩展审查包附带？ | **NO** | reviewer 可直接看到无密 handoff 模板 | 保留为 R4 输入，不进最小送审包 |
| 8 | `R9_KEY_PAGE_VISUAL_EVIDENCE.md` 与 `evidence/r9-key-pages/*` 是否附带？ | **NO** | 本轮候选自带页面截图证据 | 视觉证据作为独立附件或按需引用 |
| 9 | `tests/e2e/specs/r9-visual-evidence.spec.ts` 是否进入本轮候选？ | **NO** | 视觉证据型 E2E 一并进入候选 | 仅保留 `creative-smoke` 与 `full-flow` 作为最小 E2E 集 |
| 10 | 本轮是否采用“最小可送审候选”而不是“完整内部 dossier”？ | **YES** | 优先冻结最小主干，后续再附加扩展证据 | 一次性把扩展证据包一并打进候选 |

---

## 3. 默认拍板后的结果

如果完全按默认建议拍板，那么本轮将得到：

### 3.1 进入候选
- R25 A 组全部
- R25 B 组全部
- `.github/workflows/ci.yml`

### 3.2 不进入候选
- Helm 主模板与 values
- Keycloak realm
- R16 / R17 / R19
- R9 视觉证据与截图目录
- `r9-visual-evidence.spec.ts`
- 所有已明确排除项（日志 / snapshot / 一次性审计 / 过程性文档）

### 3.3 结果解释

这意味着本轮冻结目标将是：

> **一个最小可送审候选**

它具备：
- 真实产品代码
- 测试
- 必要资源
- 最小运行/发布配置
- 最小 release/readiness 文档主干

但不自带：
- 扩展视觉证据
- R4 前置细节模板
- R5 source-data 深层矩阵
- Helm / Keycloak 扩展部署边界

---

## 4. 如果你想改默认建议，最常见的情况

### 只改一项：把视觉证据带上
若你希望 reviewer 一次看全页面证据，可改：
- 第 8 项：YES

### 想把 R4 / R5 审查输入一并带上
可改：
- 第 5 项：YES
- 第 6 项：YES
- 第 7 项：YES

### 想把部署边界扩大到 Helm / Keycloak
可改：
- 第 2 项：YES
- 第 3 项：YES
- 第 4 项：YES

但一旦改成 YES，候选边界会明显变宽，后续 reviewer 和发布负责人就会自然要求对这些部分一起承担审查责任。

---

## 5. 推荐结论

如果你的目标是：

> **尽快形成一个干净、可审、可继续推进 R4 / R5 的候选**

那么推荐直接采用默认建议：

- `ci.yml`：YES
- Helm：NO
- Keycloak：NO
- R16 / R17 / R19：NO
- R9 视觉证据：NO
- `r9-visual-evidence.spec.ts`：NO
- 候选模式：YES（采用最小可送审候选）

---

## 6. 一句话结论

> R26 的作用，就是把“候选范围还差哪些决定”压缩成 10 个 YES / NO；一旦拍板完成，就可以按 R25 直接进入真正冻结动作。
