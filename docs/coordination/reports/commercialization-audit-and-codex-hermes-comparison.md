# X-Agent 商用审计与 Codex / Hermes Agent 对比报告

- 日期：2026-07-20
- 目标：在“商用完整交付”推进完成后，对 `xagent` 做一轮最深度的交付审计，并结合对 Codex / Hermes Agent 的公开资料研究，给出结构化对比与最终口径建议。

---

## 一、执行摘要

### 最终结论
当前 `xagent` 可以成立的最稳妥结论是：

> **`xagent` 已具备当前机器、单机 Docker Compose `full` 模式、受控私有部署边界下的受控商用交付能力。**

但如果将其直接表述为：

> **更广义、可复制、可企业扩展、可长期运营 fully closed 的正式商用已闭环**

则风险偏高。

### 为什么
原因不在于项目“没有交付能力”，相反，项目已经形成：
- 商用交付材料包；
- Goal / Taskboard / Run / Release / Recover 主链；
- 发布 / 回滚 / 演练 / 签字包；
- 企业级长期运营的治理骨架与首轮验证材料。

真正的问题在于：
1. 仓库中仍存在**口径冲突**；
2. CI / 测试 / 证据对“更广义企业商用闭环”的证明仍不足；
3. 一些关键长期运营能力目前更像**首轮验证**，而不是完成级实证。

---

## 二、对 `xagent` 的最深度审计结论

### 2.1 已成立的能力

#### A. 最小受控交付包已成立
当前仓库已经具备：
- 管理员部署手册
- 运维手册
- 发布 / 回滚 runbook
- 环境基线
- 已知问题 / 试点边界
- 联系人与故障升级路径
- Goal Board 与阶段执行包

这说明 `xagent` 已经不再是“有功能但不能交付”的状态，而是已经具备了一套可交接的交付骨架。

#### B. 基础质量门禁与关键主链验证已成立
当前仓库已经有：
- backend `ruff` / `pytest`
- frontend `lint` / `typecheck` / `build`
- `promptfoo-eval`
- 关键 E2E / 视觉证据

这证明核心主链和基础门禁不是空话。

#### C. 危险默认值治理已成立
- JWT / CORS / 默认管理员路径已经有 fail-fast / 边界说明
- `lite` 与 `full` 的职责差异已经明确

这说明项目已经意识到“本地开发模式”和“交付模式”的安全差别。

---

### 2.2 高风险点

#### A. 官方口径冲突
仓库中仍然存在两类叙事：
- “已达到商用交付标准”
- “仍是准商用 / 仍需继续收口”

这会直接削弱结论可信度。

#### B. CI 证明范围仍偏窄
当前 `.github/workflows/ci.yml` 实际主要覆盖：
- backend `ruff`
- backend `pytest`
- frontend `lint` / `typecheck` / `build`
- `license-gate`
- `promptfoo-eval`

但它没有覆盖：
- desktop build/tests
- Helm / K8s 部署验证
- 真正的 Playwright 发布级 gate
- security scan
- load test

因此，“正式商用 fully closed”的证明范围仍然偏窄。

#### C. 测试仍明显偏 lite-mode / local-memory
`apps/api/tests/conftest.py` 会强制：
- `XAGENT_MODE=lite`
- 清空 `XAGENT_*`
- 使用进程内状态

这意味着大量自动化验证证明的是：
- lite / local / in-memory 行为
而不是：
- full-mode / Redis / Postgres / Qdrant / Keycloak / customer-env 行为

#### D. Full-mode / 目标环境证据仍偏局部
最强证据仍然偏向：
- current-machine
- single-node
- Compose `full`
- 单人交付模式

这比纯本地开发强很多，但仍不能自然外推成：
- 广义企业扩展交付
- 多环境可复制
- 多角色值守体系已完成

#### E. 长期运营实证不足
虽然 G3 的四个方向都已建立治理骨架并做了首轮验证，但从“长期真实运营 fully closed”的角度看，仍不足以无保留宣称：
- 多实例一致性已实证
- secretRef / external secret manager 已落地
- SLO / RTO / RPO 已正式签字
- 容量与性能结论已形成正式企业级基线

---

### 2.3 审计后的总判断

#### 可以成立的结论
- `xagent` 已具备受控私有部署边界下的商用交付能力；
- 关键交付材料、主链、发布回滚、阶段 Goal 结构已建立；
- 适合内部试点、受控交付和当前边界下的正式交付使用。

#### 不建议直接使用的结论
- “已具备完全广义的企业商用闭环”
- “已完成可复制企业扩展能力”
- “长期运营能力已经实证闭环”

---

## 三、Codex 画像（基于公开资料）

### 3.1 核心特征
Codex 更像：
- **开发代理产品族**
- 本地 CLI / IDE + 云端隔离任务
- PR / review / code task 是第一类对象

### 3.2 强项
- GitHub / PR 导向强
- 本地与云端双执行平面明确
- 审批、sandbox、permission profile 产品化程度高
- thread/turn runtime 已有较清晰的宿主控制协议

### 3.3 边界
- release orchestration 不像 PR 能力那么原生
- 长期运行 / durability / cron / background control 的公开细节不如 Hermes 厚
- 更偏“开发执行器”，而不是通用运营代理平台

---

## 四、Hermes Agent 画像（基于公开资料）

### 4.1 核心特征
Hermes 更像：
- **长期运行的通用自主代理平台**
- session / background / cron / checkpoint / rollback / messaging / control plane 是核心
- 多执行后端 abstraction 明确（local / docker / ssh / daytona / serverless 等）

### 4.2 强项
- durability 文档成熟度很高
- background / cron / notification / resume / redelivery 明确
- checkpoint / rollback 是正式产品能力
- 治理与安全（approvals / deny / env filtering / gateway safety）公开度高

### 4.3 边界
- PR / GitHub 虽然很强，但更多靠可编排能力而不是默认产品叙事
- 体系广而深，学习成本和运维复杂度高

---

## 五、`xagent` vs Codex vs Hermes 对比

## 5.1 产品定位
- **Codex**：开发执行器 / PR-first / cloud task coding agent
- **Hermes**：长期运行通用代理平台
- **xagent**：面向交付闭环的产品化代理系统

## 5.2 执行平面
- **Codex**：本地 + 云端双执行平面
- **Hermes**：多后端执行平面 abstraction
- **xagent**：当前主力仍偏单机 / Compose，平台化方向已建立但产品化程度不足

## 5.3 任务系统
- **Codex**：thread / turn + goal-oriented delegated tasks
- **Hermes**：session + background + cron + steer / interrupt + rollback
- **xagent**：Goal / Taskboard / Run / Release 主链已建立，但长期异步/多控制面 runtime 还不如 Hermes 成熟

## 5.4 交付系统能力
- **Codex**：PR 是强一等对象
- **Hermes**：PR / release 更多靠工作流编排能力实现
- **xagent**：交付主链意识很强，Goal → Release → Recover 更像交付系统，但 GitHub/PR 原生产品化不如 Codex

## 5.5 durability / 长期运行
- **Codex**：有 persisted thread / cloud background work 信号，但公开细节不厚
- **Hermes**：durability / replay / cron / remote control 非常成熟
- **xagent**：长期运营治理包已建立，但 runtime 层的真正 durability / scheduling 仍未产品化到 Hermes 水平

## 5.6 治理与安全
- **Codex**：approval + sandbox + permission profile
- **Hermes**：approval + file/env/container/session/gateway 多层治理
- **xagent**：当前更多依赖材料、边界文档和阶段 gate，运行时治理产品感仍偏弱

---

## 六、对 `xagent` 的最公允定位

当前最适合的正式表述应是：

> **`xagent` 已具备当前机器、单机 Docker Compose `full` 模式、受控私有部署边界下的商用交付能力；并已建立完整的 Goal 驱动交付体系与后续长期运营增强路线。**

### 为什么这样最稳妥
- 既承认已经做成的交付闭环；
- 又不把局部证据外推为过宽结论；
- 保留后续平台化、长期运行、复制交付增强空间；
- 避免与仓库中仍存在的保守材料形成更大冲突。

---

## 七、建议动作

### 7.1 如果要继续把“商用 fully closed”做实
建议优先补：
1. 统一唯一事实源与所有官方口径
2. 把 Playwright / security scan / load test / Helm 验证进入正式 CI / gate
3. 为 G3 的四个方向补第二轮更强实证（而不仅是首轮）
4. 将长期运行 runtime（background / scheduling / durability）向 Hermes 风格推进
5. 将 PR / GitHub / cloud execution 产品化体验向 Codex 靠拢

### 7.2 如果要对外表述
推荐说：
- “当前已具备受控商用交付能力”
- “后续工作属于平台化、规模化与长期运营增强，不影响当前交付成立”

不推荐说：
- “已经完成所有层面的企业级商用闭环”
- “已经具备完全可复制的长期企业扩展能力”

---

## 八、最终结论

> **`xagent` 的优势在于它已经把“交付闭环”本身产品化了；但和 Codex / Hermes 相比，它当前最需要继续增强的，不是再补功能，而是让 PR-first 体验、更强执行平面、长期运行 runtime、治理与长期实证更厚、更一致。**

在当前阶段，最稳妥的判断是：

- **受控商用交付能力：已成立**
- **更广义、可复制、企业扩展级的 fully closed 商用闭环：仍应保守表述**
