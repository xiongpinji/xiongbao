# R18 Candidate Freshness Audit

> Date: 2026-07-07
> Owner: Codex
> Scope: compare current local workspace with draft PR #6 / commit `d59faa3`; decide whether R5 can reuse that remote CI evidence.

## Conclusion

Draft PR #6 is still valid remote CI evidence for its own head commit, `d59faa3d66fa6848920fec8995e8d9f50ed68437`. It is not current-workspace evidence.

The active local workspace is not the PR #6 candidate:

- Current `HEAD`: `a98cea09506243ca2b585029c2c5b677f172845c`
- Current branch state: `master...origin/master [ahead 1, behind 2]`
- PR #6 head: `worktree-r1-remote-ci` at `d59faa3d66fa6848920fec8995e8d9f50ed68437`
- Merge base between local `HEAD` and PR #6 head: `da811423be37c870ca904487cd96c53ce64366cd`
- Working tree: 54 tracked modified files and 53 untracked files

R5 must not claim that PR #6 CI covers the current local readiness evidence chain. If R5 includes current local worktree changes, the release owner needs a new frozen candidate branch and a new remote CI run.

## Evidence

| Check | Result |
|---|---|
| `gh pr view 6` | PR #6 is `OPEN`, `isDraft=true`, `mergeStateStatus=CLEAN`, `headRefName=worktree-r1-remote-ci`, `headRefOid=d59faa3d66fa6848920fec8995e8d9f50ed68437` |
| PR #6 CI checks | `backend`, `frontend`, `license-gate`, and `promptfoo-eval` are all `SUCCESS` on run `28789809193` |
| `git rev-parse HEAD` | `a98cea09506243ca2b585029c2c5b677f172845c` |
| `git status --short --branch` | `## master...origin/master [ahead 1, behind 2]` plus tracked and untracked workspace changes |
| `git log --oneline --left-right --cherry-pick d59faa3...HEAD` | PR side has `d59faa3`, `0df469b`, `feff648`; local side has `a98cea0` |
| `git diff --name-only d59faa3..HEAD` | 18 tracked path differences between PR #6 candidate and local `HEAD` |
| `git diff --name-only` | 54 tracked modified files in the current working tree |
| `git ls-files --others --exclude-standard` | 53 untracked files in the current working tree |

## Difference Classification

| Area | Current local tracked changes | Current local untracked files | R5 impact |
|---|---:|---:|---|
| `.github` | 1 | 0 | CI definition changed locally; PR #6 CI result cannot validate the changed workflow definition. |
| `apps/api` | 14 | 5 | Backend code/tests/log artifacts differ from PR #6; any included runtime changes require fresh backend CI. |
| `apps/web` | 26 | 15 | Frontend app/tests/assets differ from PR #6; any included UI/build/E2E changes require fresh frontend CI. |
| `deploy` | 6 | 0 | Compose/Helm/Keycloak config changed locally; target environment and release rehearsal evidence cannot be inferred from PR #6. |
| `docs` | 3 | 27 | Coordination/release evidence docs are largely untracked relative to local `HEAD`; R5 can cite them only after a new candidate includes them. |
| `README` | 1 | 0 | Public status wording differs locally; PR #6 does not cover this wording. |
| `tests/e2e` | 2 | 1 | E2E specs differ locally; PR #6 cannot prove these exact specs. |

## Gate Decision For R5

- Safe to cite: PR #6 / run `28789809193` as remote CI evidence for commit `d59faa3d66fa6848920fec8995e8d9f50ed68437` only.
- Not safe to cite: PR #6 as proof for the current local workspace, R8/R15/R17 refreshed evidence, R18 itself, R19, or any uncommitted/untracked change.
- Required before PR review package can treat the current workspace as candidate evidence: freeze the intended files into a candidate branch, push it, and obtain a fresh remote CI run that covers that branch.

## Remaining Risk

- R18 was claimable in `TASK_BOARD.md`, but its original dependency label said `R17(DONE)` while the live board still has `R17(REVIEW)`. R18 records that drift and does not change R17 to DONE.
- The current workspace contains runtime, frontend, deploy, E2E, and docs changes from multiple prior packages. R18 does not decide which of those should enter the next candidate; it only states that PR #6 does not cover them.
