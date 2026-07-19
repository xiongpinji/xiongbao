# G3-C2 可观测 / 告警真实验证计划

> 适用阶段：G3 企业级长期运营
>
> 用途：把 G3-C2 从“观测与告警方向定义完成”推进到“已有可执行验证计划”，明确当前哪些观测入口已经真实存在、哪些信号可以被实际验证，以及哪些内容仍只是目标方向。

---

## 1. 目标

本计划的目标是：

> **为 `xagent` 的可观测 / 告警包提供第一份真实验证计划，使 G3-C2 不再只停留在定义层，而进入可验证状态。**

---

## 2. 验证范围

本次验证只覆盖以下内容：

1. `/health`、`/ready`、`/metrics` 等观测入口是否存在；
2. API / worker / web 日志入口是否清晰；
3. 当前已知关键日志信号是否可被明确点名；
4. Helm 模板中与 Prometheus scrape 相关入口是否已表达；
5. 当前哪些可观测能力已经真实存在，哪些仍只是长期目标。

本次验证**不**要求一次性完成：
- 完整 Grafana 看板落地；
- 完整 Alertmanager / PagerDuty / SLA 流程；
- 所有 SLO 数值已经生产级签字；
- 大规模历史指标存储体系建设。

---

## 3. 验证环境

当前优先采用：

- 仓库文档与 Helm 模板的等价验证环境；
- 用于确认观测入口、日志入口、Prometheus scrape 配置、当前信号与告警方向。

环境前提：
- 能读取 `deploy/helm/templates` 模板；
- 能读取 `OPERATIONS_MANUAL_V1.md`、`COMMERCIAL_RELEASE_CHECKLIST_V1.md` 等材料；
- 能确认 `/health`、`/ready`、`/metrics` 已被纳入文档与模板表达。

---

## 4. 验证项

### 4.1 健康与就绪入口验证

验证：
- `/health`
- `/ready`
- `/metrics`

期望：
- 当前材料中这些入口都被明确列出；
- `/metrics` 已进入长期运营阶段的必须关注项。

### 4.2 日志入口验证

验证：
- `docker compose logs --tail=200 api`
- `docker compose logs --tail=200 worker`
- `docker compose logs --tail=200 web`

期望：
- API / worker / web 的日志入口已被冻结为标准观察方式；
- 运维手册中明确哪些异常优先看日志。

### 4.3 关键日志信号验证

验证当前被明确列出的信号：
- `ollama_warmup_failed`
- provider 401 / 403 / timeout
- worker 长时间 pending
- readiness components 异常

期望：
- 这些信号不再只是隐含经验，而是已经成为可观测包的一部分。

### 4.4 Helm / Prometheus 表达验证

验证：
- `deploy/helm/templates/deployment.yaml` 中 Prometheus scrape annotations 是否存在。

期望：
- API Deployment 已具备 `/metrics` 的 scrape 表达；
- 说明长期运营阶段的可观测入口不是从零开始。

---

## 5. 通过标准

G3-C2 的真实验证通过，至少需要满足：

1. 健康、就绪、指标入口已真实存在；
2. API / worker / web 日志入口已清晰固定；
3. 一组关键日志信号已被正式列为长期运营关注点；
4. Prometheus scrape 入口已在模板层被验证存在；
5. 可以明确区分“当前已存在的观测能力”与“后续仍需平台化建设的能力”。

这意味着：
- G3-C2 的“通过”不是完整告警平台已经落地；
- 而是长期运营所需的观测面已经有真实可验证基础。

---

## 6. 证据要求

本计划要求输出的最小证据包括：

- 现有 `/health` / `/ready` / `/metrics` 入口说明
- 日志入口说明
- 关键日志信号清单
- Helm 模板中与 metrics/scrape 相关的渲染片段或确认结论
- 最终判定：
  - 通过 / 不通过
  - 哪些部分已验证
  - 哪些仍是后续目标

建议归档到：
- `docs/coordination/reports/commercialization-g3-c2-observability-verification.md`

---

## 7. 当前结论

当前 `G3-C2` 已完成方向定义；
这份计划的作用是让它进入下一状态：

> **可执行验证**

只有完成这一步，`G3-C2` 才能从“定义完成”走向“验证完成”。
