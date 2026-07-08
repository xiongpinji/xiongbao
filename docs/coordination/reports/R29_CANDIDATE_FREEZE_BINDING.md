# R29 Candidate Freeze Binding

> 日期：2026-07-07  
> Owner：Claude Code  
> 范围：记录最小可送审候选的 branch / commit / 远端 CI 绑定事实。  
> 边界：本文件记录候选冻结与 CI 触发事实；不等于 R4 已完成，也不等于 R5 已可签发。

---

## 1. 结论

当前最小可送审候选已完成以下动作：

- 已创建候选分支：`candidate/min-send-review-20260707-claude`
- 已生成候选提交：`1c29e5316a43f403e462cdaacf5c271f2553f23b`
- 已推送到远端：`origin/candidate/min-send-review-20260707-claude`
- 已触发新的 GitHub Actions `CI` workflow：run `28838799599`
- 当前 CI 状态：`completed / success`

当前尚未完成：

- PR 尚未创建
- R4 目标环境 / full-mode 演练仍未完成
- R5 审查包仍不可签发

---

## 2. 候选绑定事实

| 项目 | 值 |
|---|---|
| Candidate branch | `candidate/min-send-review-20260707-claude` |
| Candidate commit | `1c29e5316a43f403e462cdaacf5c271f2553f23b` |
| Upstream | `origin/candidate/min-send-review-20260707-claude` |
| CI workflow | `CI` |
| CI run id | `28838799599` |
| CI run URL | `https://github.com/xiongpinji/xiongbao/actions/runs/28838799599` |
| CI status at capture time | `completed / success` |
| PR status | no PR found for branch |

---

## 3. 执行证据

### 3.1 分支与提交

已执行：

```powershell
git -C "xagent" switch -c "candidate/min-send-review-20260707-claude"
git -C "xagent" commit -m "chore(readiness): freeze minimal send-review candidate"
git -C "xagent" rev-parse HEAD
```

结果：

- 新分支创建成功
- 候选提交生成成功
- `HEAD = 1c29e5316a43f403e462cdaacf5c271f2553f23b`

### 3.2 推送

已执行：

```powershell
git -C "xagent" push -u origin "candidate/min-send-review-20260707-claude"
```

结果：

- 新远端分支创建成功
- upstream 已绑定成功
- GitHub 返回 PR 创建入口：
  - `https://github.com/xiongpinji/xiongbao/pull/new/candidate/min-send-review-20260707-claude`

### 3.3 PR 状态

已执行：

```powershell
gh pr view "candidate/min-send-review-20260707-claude" --json number,url,state,isDraft,headRefName,headRefOid,baseRefName,statusCheckRollup
```

结果：

- `no pull requests found for branch "candidate/min-send-review-20260707-claude"`

结论：

> 当前候选分支已存在，但 PR 尚未创建。

### 3.4 CI 触发与状态

已执行：

```bash
gh workflow run CI -R xiongpinji/xiongbao --ref candidate/min-send-review-20260707-claude
gh run list -R xiongpinji/xiongbao --branch candidate/min-send-review-20260707-claude --limit 5 --json databaseId,workflowName,status,conclusion,headBranch,headSha,url,createdAt
gh run view 28838799599 -R xiongpinji/xiongbao --json status,conclusion,url,headBranch,headSha
```

结果：

- 成功触发 `CI`
- 运行号：`28838799599`
- 当前状态：`completed / success`
- head branch：`candidate/min-send-review-20260707-claude`
- head sha：`1c29e5316a43f403e462cdaacf5c271f2553f23b`
- run URL：`https://github.com/xiongpinji/xiongbao/actions/runs/28838799599`

---

## 4. 仍留在工作树中的未纳入项

当前候选 commit 之外，工作树仍保留未纳入内容，包括：

### 已修改但未纳入
- `deploy/helm/templates/deployment.yaml`
- `deploy/helm/values.yaml`
- `deploy/keycloak/xagent-realm.json`

### 未跟踪且未纳入
- 各类 `apps/api/*.log`
- 各类 `apps/web/*.log`
- `apps/api/r3-canvas-snapshot.json`
- `apps/web/08_diff_fix/...`
- `docs/FRONTEND_*`
- `docs/coordination/README.md`
- `docs/coordination/EXECUTION_LIVE_OUTPUT_PROTOCOL.md`
- `docs/coordination/TASK_PACKAGE_PROTOCOL.md`
- `docs/coordination/reports/R9 / R10 / R11 / R12 / R13 / R14 / R15 / R16 / R17 / R19 ...`
- `docs/superpowers/plans/*`
- `tests/e2e/specs/r9-visual-evidence.spec.ts`

结论：

> 当前候选是**按最小可送审候选范围冻结**的，并未把这些默认 NO / Exclude 项一并打包。

---

## 5. 下一步

当前最自然的后续动作是：

1. 记录并固化 CI 成功结论
2. 如需 code review / PR 流程，创建该候选分支的 PR
3. 继续 R4 目标环境 / full-mode 演练
4. 待 R4 与关键 REVIEW 项闭环后，再组装 R5

---

## 6. 一句话结论

> 最小可送审候选已成功冻结为分支 `candidate/min-send-review-20260707-claude` 和提交 `1c29e5316a43f403e462cdaacf5c271f2553f23b`，并已获得对应远端 CI `success`；PR 尚未创建，R4 / R5 仍未闭环。
