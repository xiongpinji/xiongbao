# Web/API P2-B 完整技能包证据

## 结论

- 审计日期：2026-08-07。
- 分支：`feature/webapi-release-hardening`。
- 审计范围：租户技能包持久记录、安全 ZIP/目录导入、完整正文运行时匹配、API/Web manifest 与 hash 回读、失败补偿清理。
- 排除范围：短剧、Tauri 桌面和技能脚本自动执行。
- 结论：P2-B 通过。技能包保留原始 `SKILL.md`、`references`、`scripts`、`assets`，脚本只存储不执行；下一阶段为 P2-C Session/Checkpoint/受控回滚。

## 持久化与安全门禁

| 验证 | 结果 |
|---|---|
| 数据库记录 | `skill_packages` 按 tenant/owner 保存 name/version、SHA-256、manifest、受控 root、完整 body、source、文件数、总大小和导入时间 |
| 原始包保留 | 受控目录完整写入 `SKILL.md`、references/scripts/assets；manifest 逐文件保存 path/size/SHA-256 |
| ZIP/目录上限 | 默认最多 100 文件、单文件 2 MiB、归档与解压总量 20 MiB；ZIP 成员按 64 KiB 流式计数，不信任中心目录声明大小 |
| 路径安全 | 拒绝绝对路径、盘符、反斜杠、`..`、ADS/冒号、Windows 设备名、尾随点空格、大小写或 Unicode 等价重复路径 |
| 链接安全 | ZIP 符号链接拒绝测试实际通过；目录符号链接也会拒绝，当前 Windows 因无创建符号链接权限仅跳过该测试用例 |
| 运行时正文 | 包导入技能按 tenant 隔离，匹配器和详情读取完整正文；列表仅返回 500 字符预览并标记截断，避免大正文拖慢 Web 列表 |
| 失败原子性 | 数据库 flush 失败或 commit 失败均删除运行时 JSON 技能与本次 `package_id` 受控目录；补偿测试已通过 |
| 脚本边界 | `scripts` 纳入 manifest 和存储，但导入路径不执行脚本 |

## API、Web 与真实浏览器

| 验证 | 结果 |
|---|---|
| 租户 API | package list/detail/import 和 skill list/detail 均按 Principal tenant 过滤；跨租户 package 返回 404，技能不可匹配 |
| API 脱敏 | 列表不返回完整 body/frontmatter，任何响应均不暴露服务器 `root_path`；详情保留完整 body 和 manifest |
| Web 页面 | 设置页支持 ZIP 上传，显示包名、版本、来源、完整 hash tooltip、文件数、总大小和可展开 manifest；明确脚本不自动执行 |
| `npm test` | 退出码 0；默认发现并执行 19/19，包含 hash 稳定预览和 manifest 路径完整性 |
| `npm run typecheck` | 退出码 0 |
| `npm run lint` | 退出码 0；0 error / 100 条存量 warning，未反弹 |
| `npm run build` | 退出码 0；2377 modules transformed，生产构建成功 |
| Playwright 真实链路 | 隔离 API + Vite 登录后进入 `/settings?section=skills`，上传本地 Playwright 技能 ZIP；页面从数据库 API 回读包名、版本、64 位 SHA-256、9 文件、23,256 bytes，并展开显示 `SKILL.md`、references、scripts 与 assets |

浏览器链路导入得到 SHA-256 `aa5e6b5b87195ce2ae412812938f09c85fc8b9528dee445bca5cb783cf5c59fb`；设置页控制台为 0 error、2 条既有 warning。验证产物已移至仓库外临时证据目录，工作树未残留测试包。

## 新鲜验证

| 验证 | 结果 |
|---|---|
| 后端关联回归 | `test_skill_packages.py`、`test_skill_packages_api.py`、`test_skill_import.py`、`test_skills_list_cache.py`、`test_skill_evolve_review.py`、`test_skill_evolve_auto.py` 共 45 项通过、1 项环境权限跳过 |
| 目标 Ruff | skill package domain/API/skills 及关联测试全部通过，0 项 |
| 目标 mypy | skill package domain/API 全部通过，0 项 |
| 全仓静态门禁 | Ruff `271 <= 286`；mypy `65 <= 74`，继续低于基线 |
| fresh migration | 空 SQLite 升级到 `20260807_skill_packages (head)`，`skill_packages` 表与 Alembic head 已回读 |
| Web 回归 | 19/19、typecheck、lint 0/100、build 全部通过 |
| 差异审计 | `git diff --check`、提交检查通过；实现提交后工作树无未提交实现文件 |

Windows 本机测试期间一度出现套接字缓冲区紧张，使提交失败补偿用例耗时约 106 秒；重跑关联套件最终全部通过，不属于产品断言或业务链失败。

## P2-B 实现提交

- `611bda5`：增加完整技能包安全导入、数据库模型和迁移。
- `c65c520`：接入租户技能包 API 与完整正文运行时匹配。
- `8efb736`：增加 Web ZIP 导入、manifest/hash 清单、列表正文限长与 commit 失败补偿。

## 已知剩余风险

- 运行时技能仍由既有 JSON SkillStore 提供，包元数据以数据库为事实源；服务重启可从 JSON 恢复，但 P2-C/R1 应增加数据库包与运行时索引一致性审计。
- 目录符号链接拒绝逻辑已实现，但当前 Windows 账户无法创建符号链接，只有 ZIP 符号链接拒绝获得本机实跑证据。
- Web 仍有 100 条存量 ESLint warning；P2 总收口必须归零或形成逐项 owner/理由/失效日期豁免。
- P2-C checkpoint、P2-D MCP 与 R1 发布门禁尚未完成，因此不能判定整个 Web/API 已达发布标准。
