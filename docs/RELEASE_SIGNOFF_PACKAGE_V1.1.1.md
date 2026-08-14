# X-Agent v1.1.1 发布签字包（Release Sign-off Package）

> 用途：本文件是 v1.1.1 正式商用交付的**签发级证据汇总**。签字人只需核对本文件证据链，确认后在第 6 节签字即完成发布治理最后一环。
> 生成时间：2026-08-14 · 候选提交：`792751e`（master HEAD）

---

## 1. 发布对象

| 项 | 值 |
|---|---|
| 版本 | v1.1.1（patch：交付缺陷修复） |
| 前一版本 | v1.1.0（2026-08-14 首发，tag CI run 31776468207 全绿） |
| 发布范围 | Web/API 单实例私有部署（短剧链路、Tauri 桌面端不在范围） |
| 仓库 | https://github.com/xiongpinji/xiongbao |
| Release | https://github.com/xiongpinji/xiongbao/releases/tag/v1.1.1 |

## 2. v1.1.1 相对 v1.1.0 的变更（全部为演练实证的缺陷修复）

| # | 缺陷 | 影响 | 修复 | 回归测试 |
|---|---|---|---|---|
| 1 | `r2_preflight` whoami 按 UTF-8 解码 GBK 输出 | init-env 权限加固在中文 Windows 必失败（icacls 1332） | OEM 代码页解码 | `test_windows_acl_decodes_whoami_with_console_codepage` + 真机验证 |
| 2 | `ollama_warmup` 漏剥 `ollama_chat/` 前缀 | warmup 超时 → API 容器重启循环 | 双前缀剥离 | `test_raw_ollama_model_name_strips_litellm_route_prefixes` |
| 3 | 原生 qwen3:4b 思考模式吃光 512 max_tokens | 编排链路空响应（model_empty_response_after_retry） | `deploy/ollama/Modelfile.xagent-qwen3` 配方入仓 | 重建模型 + 编排条件实测非空 |
| 4 | hosted CI 负载门 P95<200 噪声抖动 | 同代码间歇红绿 | CI 门校准 P95<350/P99<800（生产冻结门槛仍由受控环境裁定） | `test_r3_load_contract.py` 5/5 |
| 5 | compose 合同测试依赖 compose 插件 | 无插件 Windows 上失败 | docker-compose 独立二进制自动回退 | 发布合同 93/93 |

配套：TS SDK 产品化（dist 构建 + 类型声明 + 5 项 node:test + npm pack 验证）；README/r2.env.example 默认模型修正。

## 3. CI 证据链（全部可点击复核）

| 环节 | Run ID | 结果 |
|---|---|---|
| 候选分支 CI（c2e496e→8022e3d） | 31771271879 | ✅ 8/8（backend/frontend/license-gate/config-governance/e2e-api/promptfoo-eval/load-test/release-version） |
| master CI（8022e3d） | 31771819353 | ✅ 10/10 含 docker-build |
| v1.1.0 tag CI + Release | 31776468207 | ✅ Release 已创建 |
| master CI（792751e，v1.1.1） | 31779565589 | ✅ |
| v1.1.1 tag CI + Release | 31780400062 | ✅ 10/10，Release 已创建（非草稿） |

## 4. 本地验证证据（2026-08-14 实跑）

- 后端 pytest 35 文件约 380 用例全过；发布合同测试 93/93；warmup 10/10
- 全新 SQLite Alembic 迁移至 head `20260809_checkpoint_scope_unique`
- API `/health`、`/ready` 200；登录签 JWT；无令牌/伪令牌一律 401
- 真实模型冒烟 `xagent smoke` 三链路全通
- 前端 lint 0 error / typecheck / build / 35 单测全过；`npm audit --omit=dev` = 0
- license 门禁通过；窄化 ruff 门禁通过

## 5. 目标环境等价演练证据（Docker Engine 29.5.3，隔离项目 xagentdrill）

- 6 核心服务全部 healthy：postgres / redis / qdrant / api / worker / web
- 容器内 `alembic current` = head
- full 模式默认 admin 登录 401（不 seed 默认管理员，fail-closed 符合安全基线）
- 注册 → 登录 → 真实模型代理运行 HTTP 200（最终答案正确返回）
- helm lint 通过；default/dev/staging/prod/enterprise 五套 values 渲染通过（prod 29 个 YAML 文档全部可解析）
- compose 配置经 docker-compose config 校验合法（13 服务，可选服务全部 profile 隔离）
- 演练完成后环境已拆除清理

## 6. 签字矩阵

| 角色 | 职责确认 | 签字 | 日期 |
|---|---|---|---|
| Owner（canqu） | 范围、变更清单与证据链确认 | ＿＿＿＿ | ＿＿＿＿ |
| 发布负责人 | CI/Release/演练证据复核 | ＿＿＿＿ | ＿＿＿＿ |
| QA | 测试与合同证据复核 | ＿＿＿＿ | ＿＿＿＿ |

> 单人交付模式下以上角色均由 owner 承担，签署即视为全部角色确认。

## 7. 签字后仍需的外部条件（不阻塞本版本发布，属规模化/客户化阶段）

- 客户现场验收（按交付环境执行 ADMIN_DEPLOYMENT_MANUAL_V1）
- 多机 HA 演练（脚本见 `scripts/ha_drill.py`，需第二台机器）
- E2B L2 沙箱实测（需 E2B API key）
- 付费 LLM provider 实测（需对应 key）
