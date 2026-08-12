# Web/API R3 `1.1.0` 远端发布前置审计

> 日期：2026-08-12
> 范围：只读远端核验、本地版本候选与发布流水线安全门；未 push、未建 PR、未合并、未打 tag、未发布或部署。

## 1. 冻结事实

- 本地准备基线：`43b395177a0a2cd4f682417a40e449638d7ec8b9`，`master` 相对 `origin/master` ahead 116。
- 冻结的 `1.1.0` 候选提交：`1fb2098f0729909701f686b76ffe97c9b3409d13`。该提交包含版本事实源、Release Notes、CI 门禁和回归合同；本交接报告提交位于其后，不属于首次候选分支 push 的对象。
- 远端 `origin/master`：`fa8c923c21534c53782d832aa5727735f1aafabd`。
- `v1.0.0` 的 peeled commit 同为 `fa8c923c21534c53782d832aa5727735f1aafabd`；标签和历史 Release 不得移动或复用。
- 当前本地 116 个提交没有 Hosted CI 证据；远端最近一次 master CI 只覆盖 `fa8c923`。
- API、Web、README 和 Web lockfile 已统一准备为 `1.1.0`；标签一致性仍由 `scripts/verify_release_versions.py` 强制。

## 2. 版本判断

在准备基线 `43b3951` 上，`v1.0.0..43b3951` 共 116 个提交，其中 `feat` 27、`fix` 47、`docs` 31、`test` 6、`ci` 3、`chore` 1、`refactor` 1；breaking 标记为 0。候选包装提交不改变这一功能变更分类。

结论：按 SemVer 选择 `1.1.0`。功能增长要求 MINOR，不应只升 PATCH；没有破坏性变更证据，不升 MAJOR。

## 3. 首轮审计发现并关闭的流水线风险

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
git push origin 1fb2098f0729909701f686b76ffe97c9b3409d13:refs/heads/candidate/webapi-v1.1.0-20260812
```

本报告生成阶段没有执行该命令。

## 6. 候选分支 CI 通过标准

- 远端 head SHA 与本地冻结 SHA 完全一致。
- backend、frontend、license-gate、config-governance、e2e-api、load-test、promptfoo-eval 全绿；release-version 因候选分支条件跳过。
- docker-build 和 release 因候选分支条件跳过；GHCR `latest`、`1.1.0` 和 GitHub Release 不发生变化。
- CI 日志没有 secret、JWT 或真实凭据泄漏。
- `origin/master` 与 `v1.0.0` 保持 `fa8c923`，直到后续 PR/merge 获得独立批准。

## 7. 当前结论

本地 `1.1.0` 候选包可以进入“候选分支 push”审批门，但尚未形成远端候选、Hosted CI 或正式发布证据。当前唯一允许申请的外部动作是第 5 节第 1 步；不得把“继续”解释为 master push、tag、Release 或部署授权。
