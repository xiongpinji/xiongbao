# Web/API R3 `1.1.0` 远端发布前置审计

> 日期：2026-08-12
> 范围：远端候选分支创建、本地版本候选与发布流水线安全门；未建 PR、未合并、未打 tag、未发布或部署。

## 1. 冻结事实

- 本地准备基线：`43b395177a0a2cd4f682417a40e449638d7ec8b9`，`master` 相对 `origin/master` ahead 116。
- 首次候选提交 `1fb2098f0729909701f686b76ffe97c9b3409d13` 已创建远端分支，但因旧 workflow 的 branch allowlist 排除 `candidate/**`，GitHub API 精确返回该 SHA 的 workflow runs 为 0。该提交已被后续修正候选取代，不得进入 PR、master 或 tag。
- 修正候选提交：`773570e12aadc4095434e8cd0a0c41db02d74f54`。该提交加入 `candidate/**` push 触发合同，并保留候选分支不执行版本发布、镜像推送和 Release 的安全条件。
- 远端 `origin/master`：`fa8c923c21534c53782d832aa5727735f1aafabd`。
- `v1.0.0` 的 peeled commit 同为 `fa8c923c21534c53782d832aa5727735f1aafabd`；标签和历史 Release 不得移动或复用。
- 当前本地 116 个提交没有 Hosted CI 证据；远端最近一次 master CI 只覆盖 `fa8c923`。
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

首次远端动作的建议命令仅供审批后执行：

```powershell
git push origin 773570e12aadc4095434e8cd0a0c41db02d74f54:refs/heads/candidate/webapi-v1.1.0-20260812
```

首次已获批命令仅创建了无 CI 运行的 `1fb2098` 分支。修正候选为 `773570e12aadc4095434e8cd0a0c41db02d74f54`；在再次获得授权前，不得 fast-forward 远端分支。

## 6. 候选分支 CI 通过标准

- 远端 head SHA 与本地冻结 SHA 完全一致。
- backend、frontend、license-gate、config-governance、e2e-api、load-test、promptfoo-eval 全绿；release-version 因候选分支条件跳过。
- docker-build 和 release 因候选分支条件跳过；GHCR `latest`、`1.1.0` 和 GitHub Release 不发生变化。
- CI 日志没有 secret、JWT 或真实凭据泄漏。
- `origin/master` 与 `v1.0.0` 保持 `fa8c923`，直到后续 PR/merge 获得独立批准。

## 7. 当前结论

远端存在初始候选分支，但 `1fb2098` 没有任何 Hosted CI 运行，不能作为可合并候选。下一外部动作必须重新申请：只允许把修正候选 `773570e12aadc4095434e8cd0a0c41db02d74f54` fast-forward 到同名候选分支。不得把既有授权解释为替代 SHA push、master push、PR、tag、Release 或部署授权。
