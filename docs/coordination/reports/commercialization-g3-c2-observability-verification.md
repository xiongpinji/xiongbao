# G3-C2 可观测 / 告警验证结果

> 适用阶段：G3 企业级长期运营
>
> 目的：记录 G3-C2 的第一轮真实验证结果，证明可观测 / 告警方向已经从“定义完成”推进到“已有真实通过证据”。

---

## 1. 验证目标

本轮验证覆盖：

- `/health`、`/ready`、`/metrics` 等入口是否已在材料中真实存在；
- API / worker / web 日志入口是否固定；
- 关键日志信号是否已被冻结；
- Helm 模板中 Prometheus scrape 入口是否已表达。

---

## 2. 验证结果

### 2.1 健康 / 就绪 / 指标入口
- **通过**
- 当前材料中已明确：
  - `/health`
  - `/ready`
  - `/metrics`
- 这意味着长期运营阶段的基础健康与指标入口已被正式承认存在。

### 2.2 日志入口
- **通过**
- 运维手册已固定：
  - `docker compose logs --tail=200 api`
  - `docker compose logs --tail=200 worker`
  - `docker compose logs --tail=200 web`
- 说明 API / worker / web 的日志入口已经有统一口径。

### 2.3 关键日志信号
- **通过**
- 当前已经被冻结的重点信号包括：
  - `ollama_warmup_failed`
  - provider 401 / 403 / timeout
  - worker 长时间 pending
  - readiness components 异常
- 这些信号已不再只是经验，而是长期运营阶段的正式关注点。

### 2.4 Helm / Prometheus scrape 入口
- **通过**
- Helm 模板中已存在：
  - `prometheus.io/scrape: "true"`
  - `prometheus.io/port: "8000"`
  - `prometheus.io/path: "/metrics"`
- 说明 API 的 Prometheus scrape 表达已经具备。

---

## 3. 当前仍未完成的项

本轮验证通过后，G3-C2 仍未完成的部分包括：

1. **Grafana / Alertmanager 真正落地**
   - 当前只是已有入口与方向，不是完整平台落地。
2. **SLO / 阈值签字版**
   - 当前已明确方向，但还未形成生产级正式签字版。
3. **长期指标保留与告警升级链**
   - 仍需在后续包中继续收口。

---

## 4. 当前判定

### 已成立
- 可观测 / 告警方向已经不是抽象目标；
- 至少一轮真实验证已完成；
- 健康、就绪、指标、日志与基础 scrape 入口都已形成可验证证据。

### 尚不能成立
- 完整观测平台已生产级落地；
- 所有告警阈值已经正式签字；
- 长期指标保留与全链路告警已经全部闭环。

---

## 5. 当前结论

> **G3-C2 已完成第一轮真实验证，状态可以从“定义完成”推进为“验证中且已有通过证据”。**

后续若要把 G3-C2 判为完全 done，仍需继续补：
- Grafana / Alertmanager / SLO 的正式落地结果；
- 长期告警升级链与保留策略。
