# Web/API R3 `1.1.0` 远端发布前置审计

> 日期：2026-08-12
> 范围：远端候选分支创建、本地版本候选与发布流水线安全门；未建 PR、未合并、未打 tag、未发布或部署。

## 1. 冻结事实

- 本地准备基线：`43b395177a0a2cd4f682417a40e449638d7ec8b9`，`master` 相对 `origin/master` ahead 116。
- 首次候选提交 `1fb2098f0729909701f686b76ffe97c9b3409d13` 已创建远端分支，但因旧 workflow 的 branch allowlist 排除 `candidate/**`，GitHub API 精确返回该 SHA 的 workflow runs 为 0。该提交已被后续修正候选取代，不得进入 PR、master 或 tag。
- 第二候选提交 `773570e12aadc4095434e8cd0a0c41db02d74f54` 加入 `candidate/**` push 触发合同，并保留候选分支不执行版本发布、镜像推送和 Release 的安全条件。获批快进后已触发 Hosted CI run `31574864402`，但未全绿，不可合并。
- 首个可执行候选 `1b2acdb905478ad025c7019ea1bd5dcc137990ac` 已快进至远端候选分支，并触发 Hosted CI run `31580023074`。该运行仅 load-test 失败，其余可执行候选门全部通过。
- 当前本地负载门禁修正候选：`5fbf3fdae95a4261444357dbf13593155baa30e1`。该提交仅修正 CI 负载模型、场景阈值与对应合同；未修改 API 产品路由、恢复 `/metrics` 缓存、放宽业务 API 延迟门槛或扩大发布范围。
- 远端 `origin/master`：`fa8c923c21534c53782d832aa5727735f1aafabd`。
- `v1.0.0` 的 peeled commit 同为 `fa8c923c21534c53782d832aa5727735f1aafabd`；标签和历史 Release 不得移动或复用。
- Hosted CI 已覆盖到 `1b2acdb`，结论为 failure，且唯一失败为 load-test；后继修正 `5fbf3fd` 仍只有本地验证，尚无 Hosted CI 证据。远端 master 仍停留在 `fa8c923`。
- API、Web、README 和 Web lockfile 已统一准备为 `1.1.0`；标签一致性仍由 `scripts/verify_release_versions.py` 强制。

## 2. 版本判断

在准备基线 `43b3951` 上，`v1.0.0..43b3951` 共 116 个提交，其中 `feat` 27、`fix` 47、`docs` 31、`test` 6、`ci` 3、`chore` 1、`refactor` 1；breaking 标记为 0。候选包装提交不改变这一功能变更分类。

结论：按 SemVer 选择 `1.1.0`。功能增长要求 MINOR，不应只升 PATCH；没有破坏性变更证据，不升 MAJOR。

## 3. 审计发现并关闭的流水线风险

旧 `docker-build` 只依赖 backend/frontend。由于 master push 会生成并推送 `latest`、sha 和 semver metadata，这可能在 license、config、API E2E、load 和 promptfoo 尚未通过时提前覆盖镜像。

本地候选已将 `docker-build.needs` 收紧为八个门：

1. backend
2. frontend
3. license-gate
4. config-governance
5. e2e-api
6. load-test
7. promptfoo-eval
8. release-version

其中 `release-version` 在 master 校验 API/Web/README 一致，在 tag 上额外校验 tag；错误 tag 无法先行推送镜像。合同测试先在旧配置稳定失败，再以最小 YAML 修改转绿。候选分支 push 因 workflow 条件不会执行 docker-build；只有 master 或 `v*` tag push 才会构建并推送镜像。

首次远端创建还暴露第二个真实缺口：`on.push.branches` 原先只包含 `main/master/develop`，所以合法的候选分支不会触发任何 CI。修复合同先证明 `candidate/**` 缺失，再将该模式加入 push allowlist。修正后候选分支会执行 backend、frontend、license、config、API E2E、load 和 promptfoo，而 version、docker-build、release 仍按条件跳过。

第二次 Hosted CI 暴露了负载合同与实时指标语义的偏差：`cbb7de3` 正确让 `/metrics` 绕过 60 秒响应缓存后，旧 k6 脚本仍在每个业务迭代中同步请求 `/metrics`，候选运行等价于约每秒 74.8 次 Prometheus 抓取，而生产配置周期为 15 秒。旧脚本还将无效登录 429 排除在自定义错误率之外，却没有 checks 阈值，导致摘要无法反映真实合同。本地修正保持 `/metrics` 实时语义，将其按 15 秒周期的独立 scenario 验证；业务 API 仍使用原 P95 < 200 ms / P99 < 500 ms 门槛，并为两个 scenario 分别设置延迟、checks 和 errors 阈值。

## 4. 远端治理边界

- 仓库是私有仓库，默认分支为 `master`。
- GitHub GraphQL 返回 branch protection rules 为空；REST protection/rulesets 因当前私有仓库套餐返回 403。不能依赖平台强制保护，必须采用人工分步授权。
- 任意 `v*` tag 都会触发版本一致性门、GHCR 镜像推送，并在全部 release needs 通过后自动创建非草稿 GitHub Release。
- 因此不得使用 `v1.1.0-rc.*` 做远端试跑；当前工作流会把它当正式 Release 处理。

## 5. 推荐的不可逆操作顺序

每一步都需要独立结果和下一步授权，不得合并成一次命令：

1. **候选分支 push**：只推送本地交接报告记录的显式候选 SHA 到 `candidate/webapi-v1.1.0-20260812`；不得使用漂移的 `HEAD`，不得更新远端 master，不得创建 tag。
2. **候选 CI**：等待该 SHA 的 backend、frontend、license、config、API E2E、load、promptfoo 全部完成；确认 docker-build/release 按条件跳过。
3. **PR/merge 授权**：候选 CI 全绿后，建立 PR 并复核 diff、版本、release notes、风险和回滚；Owner 单独批准后才合并 master。
4. **master CI**：确认合并 SHA 的全部门禁通过，GHCR `latest`/sha 已由受控 docker-build 生成，并记录不可变 digest。
5. **tag/Release 授权**：再次核对版本事实源均为 `1.1.0`，Owner 单独批准后才创建 `v1.1.0`；等待 tag workflow 自动创建 Release。
6. **部署授权**：目标环境、secret、备份、变更窗口、回滚负责人和签字齐备后，才按 Runbook 部署。tag/Release 不是部署授权。

下一次远端动作的建议命令仅供重新审批后执行：

```powershell
git push origin 5fbf3fdae95a4261444357dbf13593155baa30e1:refs/heads/candidate/webapi-v1.1.0-20260812
```

`1b2acdb` 的快进已单独获批并执行，但 CI run `31580023074` 仅 load-test 失败。在再次获得对精确 SHA `5fbf3fdae95a4261444357dbf13593155baa30e1` 的授权前，不得再次 fast-forward 远端分支。

## 6. 候选分支 CI 通过标准

- 远端 head SHA 与本地冻结 SHA 完全一致。
- backend、frontend、license-gate、config-governance、e2e-api、load-test、promptfoo-eval 全绿；release-version 因候选分支条件跳过。
- docker-build 和 release 因候选分支条件跳过；GHCR `latest`、`1.1.0` 和 GitHub Release 不发生变化。
- CI 日志没有 secret、JWT 或真实凭据泄漏。
- `origin/master` 与 `v1.0.0` 保持 `fa8c923`，直到后续 PR/merge 获得独立批准。

### 6.1 首次真实 Hosted CI 结果

- Run：`31574864402`，候选 SHA：`773570e12aadc4095434e8cd0a0c41db02d74f54`，结论：`failure`。
- 通过：frontend、license-gate、e2e-api。
- 失败：backend 的静态质量基线；config-governance 的 R2 contract。
- 依赖跳过：load-test、promptfoo-eval。安全条件跳过：release-version、docker-build、release。
- 完整 4112 行 CI 日志中 Bearer、JWT、private key 和 GitHub token 模式命中均为 0。
- Backend 根因：R3 收口提交将明确排除的 `creative_studio` 4 项 mypy 精确基线误写为 0；CI 实测仍为 4 项，指纹 `4be9c4ff75c9cb73f9c6987dfb2f7fa2f401200efba8c866087ac767a11aa95d`。
- Config 根因：Linux 测试在 mock `os.name="nt"` 后才构造 `Path("C:/Windows/System32")`，导致 `WindowsPath` 在非 Windows 平台抛 `NotImplementedError`。
- 复审追加根因：静态门的 `-S` 子进程会在部分虚拟环境重新解析错误的 `site-packages`，可产生假 0。修复后子进程使用父解释器解析的 `purelib`，依赖漂移会 fail-closed。
- 本地绿灯：R2 release contracts 43/43；后端发布范围 744 passed / 8 skipped；静态门 4 项短剧排除精确匹配；Linux Python 3.11 跨平台定向测试通过；独立复审 PASS，0 问题。

### 6.2 `1b2acdb` Hosted CI 与负载门修正

- Run：`31580023074`，候选 SHA：`1b2acdb905478ad025c7019ea1bd5dcc137990ac`，结论：`failure`。
- 通过：backend、frontend、license-gate、config-governance、e2e-api、promptfoo-eval。唯一失败：load-test。安全条件跳过：release-version、docker-build、release。
- Hosted k6 摘要：373.8 RPS、全局 P95 236.9 ms、自定义 errors 0.31%，仅 `http_req_duration` P95 < 200 ms 阈值失败。该 errors 口径不包含登录 429，不能作为标准 HTTP 错误率。
- 同一旧脚本的本地 CI 形状基线复现为 exit 99、416.3 RPS、P95 233.5 ms；分端点数据中 `/metrics` P95 290.87 ms，并且登录产生 12,475 次 429。
- 修正候选 `5fbf3fdae95a4261444357dbf13593155baa30e1` 在不恢复 metrics 缓存、不改 API 产品逻辑、不放宽业务 API 门槛的前提下，将 metrics 调整为独立 15 秒抓取 scenario，禁用可信负载 job 的全局 IP 限流，并保留登录防爆破 429 为预期拒绝结果。
- 最终同曲线本地运行 exit 0：536.3 RPS，业务 API P95 167.2 ms、P99 292.7 ms，errors 0.00%；metrics 和 API 两个 scenario 门均通过。
- TDD 先证明旧实现缺少独立 scenario、checks 阈值、P99 摘要来源和 CI 发现入口，再逐项转绿。最终 R2 合同 43/43、R3 负载合同 5/5、完整 Web/API 发布范围 exit 0（10 项既有环境跳过）、Python 3.11 精确 Ruff/mypy 指纹通过；规格和质量独立复审均 PASS，Critical/Important/Minor 均为 0。
- 剩余风险：Hosted runner 的 k6 与 Python 依赖仍未全量锁定；本地同曲线证据不能替代新 SHA 的 Hosted CI。

## 7. 当前结论

远端候选已在 `1b2acdb` 触发真实 Hosted CI，但 run `31580023074` 仅 load-test 失败，仍不能作为可合并候选。下一外部动作必须重新申请：只允许把本地修正候选 `5fbf3fdae95a4261444357dbf13593155baa30e1` fast-forward 到同名候选分支，然后只监控该 SHA 的 CI。不得把既有授权解释为替代 SHA push、master push、PR、tag、Release 或部署授权。
