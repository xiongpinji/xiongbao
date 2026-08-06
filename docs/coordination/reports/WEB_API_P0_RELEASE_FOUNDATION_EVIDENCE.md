# Web/API P0 发布基础证据

## 结论

- 审计日期：2026-08-07。
- 分支：`feature/webapi-release-hardening`。
- 审计范围：P0-A 至 P0-E，仅 Web/API；短剧和 Tauri 桌面端排除。
- 结论：P0 发布可信基础通过，可以进入 P1 开发任务闭环；这不代表 Codex/Hermes 对标总目标已完成，也不授权创建或移动发布标签。

## 后端与静态质量

| 验证 | 结果 |
|---|---|
| `pytest test_orchestration.py test_static_quality_gate.py test_verify_release_versions.py -q` | 退出码 0，13/13 通过；1 条第三方弃用 warning |
| 关键 Ruff `F821,F822,F823,B023` | 退出码 0，0 项 |
| `python scripts/check_static_quality.py` | 退出码 0；Ruff `279 <= 286`，mypy `73 <= 74` |
| `python scripts/verify_release_versions.py --tag v1.0.0` | 退出码 0；API/Web/README/标签文本版本一致 |

P0-A 的流式双工具测试曾先稳定失败于两个 `_tool_success` `UnboundLocalError`；修复后返回真实 `a`、`b`，并验证最终统计为 2 次调用、成功率 100%。

## Web

| 验证 | 结果 |
|---|---|
| `npm test` | 退出码 0；自动发现 2 个测试文件，共 11/11 通过 |
| ESLint JSON 统计 | 退出码 0；0 error / 100 warnings，未超过基线 |
| `npm run typecheck` | 退出码 0 |
| `npm run build` | 退出码 0；2372 modules transformed |
| 排除模块产物检查 | `dist/assets` 无 `CreativeStudioPage` 或 `EditorPage` chunk；存在诚实的 `ExcludedModulePage` chunk |

## 仓库与发布链

| 验证 | 结果 |
|---|---|
| `git diff --check HEAD~4..HEAD` | 退出码 0 |
| `git status --short` | 空，审计前工作树干净 |
| CI Ruff/mypy `|| true` 搜索 | 无命中 |
| workflow YAML 与 Release needs 检查 | 解析通过；Release 依赖 backend、frontend、license、config、image、E2E、load、eval、version 共 9 个 gate |

P0 实现提交：

- `b82d829`：修复流式并发工具结果统计。
- `01251c0`：阻断关键静态错误并固定存量基线。
- `df3bbf5`：收紧 Web/API 发布入口与默认测试范围。
- `a937983`：统一版本事实源并门禁 Release。

## 已知剩余风险

- Ruff 279 项、mypy 73 项和 Web 100 条 warning 是受门禁约束的存量，不是零债务；后续不得反弹。
- `npm ci` 仍报告 6 个开发依赖漏洞（3 moderate / 3 high）；禁止用 `--force` 无差别升级，需独立依赖审计包。
- 本地只验证了 workflow 结构；远端 GitHub Actions 尚未由本分支 push/tag 触发。
- 现有 `v1.0.0` 标签指向历史提交，不得移动或复用；实际新发布必须选择新版本并重新通过版本门禁。
- 短剧源码和桌面源码仍保留供未来接入，但不属于当前发布证据。
- P1 的 Codex 开发任务闭环与 P2 的 Hermes 持久调度、技能、会话恢复、MCP 差距仍待实现。
