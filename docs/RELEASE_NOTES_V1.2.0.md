# X-Agent v1.2.0 发布说明

> 发布日期：2026-09-05 · 上一版本：v1.1.3（2026-08-14）
> 本版主题：**全量商用交付候选门禁合并 + 交付缺口修复 + 上下文压缩（竞品差距 V3-5）**

---

## 一、商用交付门禁全量合入（PR #22，67 提交）

v1.1.3 之后在 `codex/commercial-delivery-20260815` 分支积累三周的商用交付加固工作，
经本地全量门禁复验（后端/前端/根级合同测试全绿）与远端 CI 验证后合入 master：

- **发布脊柱**：`core/spine/release.py` + release-version / load-test / promptfoo-eval /
  supply-chain / config-governance / 商用内核合同等 CI 门禁
- **目标环境发布门禁**：候选 SHA 证据绑定、拒绝伪通过证据、托管负载门
- **版本对齐修复**：runtime `__version__`、Helm Chart、桌面端版本与发布 tag 全链一致
  （v1.1.x 存在的 runtime 版本停在 1.0.0 的缺陷就此闭环），`verify_release_versions.py`
  覆盖 pyproject / web / `__init__.py` / Helm / README 五处断言
- **安全**：安全扫描器增强（tests/security/scan.py）、LLM override 明文密钥剥离迁移
  （scripts/migrate_llm_overrides.py）、请求日志合同
- **桌面端**：Windows 桌面质量与安装包（MSI/NSIS）CI 产线，版本对齐主版本
- **性能**：ASGI 中间件替代请求上下文中间件、去除重复同步访问日志

## 二、交付缺口修复（2026-09-05 审计 F-3/F-4）

- **LLM override 一键清除**：`DELETE /api/v1/system/llm-config/override`（运行中即时恢复
  env 控制）+ `xagent config clear-override`（服务不可用时运维本地清除，默认 `.bak` 备份）
  ——解决"设置页覆盖优先级高于 env/.env、改环境变量不生效"的排障困境
- **环境一键重建**：`scripts/bootstrap_dev_env.py`（uv 重建 venv + node_modules，
  `--check` 诊断模式）——解决接手/运维复现环境丢失问题
- 修复 master 分支保护与 CI job 名不匹配导致的合并阻塞（ruleset + branch protection
  的 required checks 更新为实际 job 名）

## 三、上下文压缩 V3-5（对标 Codex compaction）

- 多轮历史按 **token 预算**管理：默认 24000 tokens（`XAGENT_LLM__CONTEXT_BUDGET_TOKENS`
  可配，0 关闭）；超预算时旧消息摘要折叠（优先 LLM 摘要，失败降级启发式），
  近期 8 条原样保留
- 编排循环由"盲截 8 轮"（旧上下文静默丢失）改为"30 轮窗口 + 预算压缩"
- 零新依赖（CJK/ASCII 启发式 token 估算）

## 四、竞品路线更新（ROADMAP_V3）

- V3-5 上下文压缩 ✅（本版）
- V3-6 Telegram 消息渠道网关 ⏳（v1.2.x 目标，对标 Hermes 渠道接入）
- V3-7 内网技能目录 ⏳（v1.3 目标，对标 Hermes Skills Hub）

## 五、升级与兼容

- 数据库迁移无新增（head 仍为 `20260809_checkpoint_scope_unique`）
- 配置新增可选项 `XAGENT_LLM__CONTEXT_BUDGET_TOKENS`（默认 24000，行为向后兼容）
- API 新增端点：`DELETE /api/v1/system/llm-config/override`（需 `system:manage` 权限）
- CLI 新增子命令：`xagent config clear-override`
- 全部既有测试兼容通过（后端全量 + 前端 51 项 + 根级发布/安全合同）

## 六、已知边界（不变）

多机 HA、E2B L2 云沙箱、付费 provider、客户现场签字、桌面安装包代码签名
（desktop_signing: not_completed）仍为独立外部条件，不在本版结论内。
