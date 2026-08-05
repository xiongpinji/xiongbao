# R17 PR Evidence Matrix Source

> Date: 2026-07-06
> Owner: Codex
> Scope: source data for R5 PR review package, not the final PR body.
> Recovery refresh: 2026-07-07

## Purpose

R17 maps the current DONE / REVIEW evidence packages to `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` so R5 can assemble a reviewer-ready PR package without re-mining the entire coordination history.

The 2026-07-07 refresh keeps the source data aligned with the live task board after R8 and R15 were rechecked in the fixed recovery chain.

This is source data only:

- It does not mark the release as formally ready.
- It does not sign off checklist boxes.
- It does not replace R4 target-environment rehearsal.
- It does not convert REVIEW packages to DONE.

## Candidate And Gate Context

| Item | Current source | R5 handling |
|---|---|---|
| Remote CI | R1 records draft PR #6, commit `d59faa3`, run `28789809193`, all checks green | Treat as remote CI evidence for that candidate; re-check if PR candidate changes after R13-R17 docs/code changes |
| Current task board | `docs/coordination/TASK_BOARD.md` | Use as live status source; do not infer DONE from delivery evidence without scheduler review |
| Release truth source | `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` | Use for public/reviewer status wording |
| Release checklist | `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` | Use as checklist mapping target; boxes remain release-owner signoff items |
| Target environment | R4 BLOCKED, R16 REVIEW prep checklist | R5 must keep R4 as unresolved unless target rehearsal evidence appears |
| Codex follow-up candidates | R18/R19 are visible as READY in `TASK_BOARD.md` | Treat as follow-up work only; dependency labels reference R17/R16/U2 completion states that still need reviewer/scheduler confirmation before claim |

## Evidence Chain Closure Notes

- R8 messaging audit, R15 evidence sync, this R17 source file, and `TASK_BOARD.md` now consistently describe R17 as REVIEW, not a claimable task.
- R8 is reviewer-ready for its bounded purpose: external messaging / release-status wording consistency for PR review preparation.
- R15 is reviewer-ready for its bounded purpose: coordination state and evidence-link consistency.
- R17 is reviewer-ready for its bounded purpose: R5 source data and checklist evidence matrix.
- None of these packages converts R4, R5, R14, R15, R16, or R17 to DONE; that remains a scheduler/reviewer decision.
- 2026-07-07 refresh: R18/R19 are tracked as READY follow-up candidates, but R17 does not use their existence as release readiness evidence and does not clear their dependency-label drift.

## Checklist Evidence Matrix

| Checklist area | Relevant items | Evidence packages | Current state | R5 note |
|---|---|---|---|---|
| 1. Version and scope | version/tag, frozen scope, included/excluded capability, status docs | R1, R8, R15, SOT, ROADMAP, R18 candidate task | Partial | PR #6 / `d59faa3` is the only remote-CI candidate evidence; local worktree still contains later readiness changes and must not be silently treated as the same frozen release candidate; R18 is the follow-up audit candidate, not current proof |
| 2.1 Docs and messaging | README / ROADMAP consistency, owner-reviewed external wording | R8 REVIEW, R15 REVIEW, SOT | Review pending | Messaging is aligned for PR-prep wording, not formal GA; owner review still required before public use |
| 2.2 Frontend first release scope | page scope, assets under version control, screenshots | R2 DONE, R9 DONE, R14 REVIEW | Mostly covered locally | R9 is local dev evidence; target/staging screenshots remain tied to R4 or release-owner signoff |
| 2.3 Runtime failure closure | direct/stream/workflow failure visibility, blocked/failed UI, failure rehearsal | P0-A DONE, R3 DONE, R10 DONE, R13 DONE | Functional evidence covered locally | R10 originally found Chat SSE gap; R13 closes it locally with full-flow 9/9; target-environment failure rehearsal still not proven |
| 2.4 Security defaults | no `admin/admin` in prod, JWT secret, compose/Helm defaults, CORS, auth, Langfuse defaults | P0-D DONE, R7 DONE, R16 REVIEW | Baseline covered, target secrets pending | Full-mode account source, Langfuse secrets and secret manager injection still need R4/U2 execution |
| 2.5 Release and rollback | runbook, DB migration, rollback, staging rehearsal logs | R6 DONE, R12 DONE, R16 REVIEW, R4 BLOCKED | Runbook and prep covered; rehearsal blocked | R4 is the main release blocker; R16 is only a prerequisite checklist |
| 2.6 CI and quality gates | backend pytest/ruff, frontend lint/typecheck/build, Playwright, CI green | P0-E DONE, R1 DONE, R2 DONE, R3 DONE, R10 DONE, R13 DONE, R14 REVIEW, R11 DONE | Strong local/remote evidence, with caveats | R1 CI covers `d59faa3`; R14 clears chunk warning locally; R11 still has full `npm audit` dev/build-tool risk |
| 3. Function and UX acceptance | health/ready/login/workbench/run console/core flows/empty states | R3 DONE, R9 DONE, R13 DONE, R14 REVIEW | Local dev evidence | R4 or release owner must decide whether local UI/E2E is sufficient for PR review entry |
| 4. Environment and config baseline | dev/staging/prod config, secret source, external dependencies, LLM path, OIDC/OpenFGA/storage | R7 DONE, R16 REVIEW, P0-D DONE | Documented baseline, not environment-proven | R4 needs real or equivalent environment values, services and LLM path |
| 5. Security and compliance | license gate, security scan, tenant/auth/header/rate-limit, exposure, TLS | R1 DONE, P0-D DONE, P0-E DONE, security middleware tests in P0 evidence | Partial | Remote license-gate passed in R1; host security scan, TLS, direct exposure and full target auth scenarios remain checklist signoff items |
| 6. Observability and operations | metrics, Grafana, Langfuse trace, worker, logs | R6 DONE, R16 REVIEW | Partial | R16 lists prerequisites; actual metrics/traces/worker verification belongs to R4 or later ops package |
| 7. Data and recovery | target DB migration, backup, restore, RTO/RPO | R6 DONE, R12 DONE | Partial | Fresh SQLite migration is proven; target DB migration/backup/restore rehearsal is not |
| 8. Performance and capacity | load test, capacity, bottlenecks | R14 REVIEW, R11 DONE | Mostly open | Bundle warning cleared; no load/capacity evidence yet |
| 9. Delivery materials | admin/deploy/ops/upgrade/rollback/known issues/trial boundary/contact | README, R6 DONE, R7 DONE, R8 REVIEW, R15 REVIEW, this R17 source, R19 candidate task | Partial | R5 can reuse these as PR evidence links; R19 may add a secret handoff template later, but it is not current release evidence |
| 10. Final release decision | formal commercial / internal trial / no release | SOT, checklist, TASK_BOARD | Not formal GA | Current evidence supports PR review preparation only; final decision blocked by R4/R5 and reviewer signoff |

## Evidence Index For R5

| Package | Status now | Evidence entry |
|---|---|---|
| P0-A | DONE | `docs/coordination/reports/delivery-report.md#p0-a-orchestration-await-bug` |
| P0-B | DONE | `docs/coordination/reports/delivery-report.md#p0-b-前端-lint-阻断` |
| P0-C | DONE | `docs/coordination/reports/delivery-report.md#p0-c-previewdemo-污染清理` |
| P0-D | DONE | `docs/coordination/reports/delivery-report.md#p0-d-危险默认值清零` |
| P0-E | DONE | `docs/coordination/reports/delivery-report.md#p0-e-ci-最小门禁与真实状态文档对齐` |
| R1 | DONE | `docs/coordination/reports/delivery-report.md#r1-远端-ci-全绿收口与失败项清零` |
| R2 | DONE | `docs/coordination/reports/delivery-report.md#r2-frontend-build-可复现验证与构建门禁补齐` |
| R3 | DONE | `docs/coordination/reports/delivery-report.md#r3-关键-e2e-冒烟包补齐并跑通` |
| R4 | BLOCKED | `docs/coordination/reports/delivery-report.md#r4-目标环境演练与发布证据归档` |
| R6 | DONE | `docs/coordination/reports/delivery-report.md#r6-发布回滚-runbook-v1-补齐` |
| R7 | DONE | `docs/coordination/reports/delivery-report.md#r7-环境基线与-secret-注入说明补齐` |
| R8 | REVIEW | `docs/coordination/reports/delivery-report.md#r8-对外口径一致性终检包`; `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md` |
| R9 | DONE | `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md` |
| R10 | DONE | `docs/coordination/reports/R10_FULL_FLOW_E2E_TRIAGE.md` |
| R11 | DONE | `docs/coordination/reports/R11_NPM_AUDIT_FRONTEND_BUILD_RISK.md` |
| R12 | DONE | `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md` |
| R13 | DONE | `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md` |
| R14 | REVIEW | `docs/coordination/reports/R14_VITE_CHUNK_SPLIT.md` |
| R15 | REVIEW | `docs/coordination/reports/R15_EVIDENCE_SYNC.md` |
| R16 | REVIEW | `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md` |
| R17 | REVIEW | this file |
| R18 | READY | `docs/coordination/TASK_BOARD.md`; follow-up candidate only |
| R19 | READY | `docs/coordination/TASK_BOARD.md`; follow-up candidate only |

## Remaining Risks To Surface In R5

- R4 target-environment rehearsal is still BLOCKED; local lite/dev evidence is not enough for formal release.
- R8/R14/R15/R16/R17 are REVIEW, not DONE, until scheduler/reviewer accepts them.
- R1 remote CI evidence covers draft PR #6 / `d59faa3`; R5 must re-check remote CI if the PR candidate includes later local changes.
- R18/R19 are READY follow-up candidates, but their dependency labels still reference DONE states that are not all reflected by the live REVIEW board; the claimant or scheduler must resolve that before using them as gate evidence.
- R11 leaves full `npm audit` dev/build-tool risk unresolved unless release owner accepts it or opens an upgrade package.
- R12 proves fresh DB migration, not target-environment data migration, backup or restore.
- R17 is source data only and must not be pasted as final PR signoff without R5 owner review.

## 2026-07-07 Verification

- Structure scan command: `rg -n "Codex follow-up candidates|R18/R19 are visible as READY|R8/R14/R15/R16/R17 are REVIEW|R17 is source data only" docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- Board status scan command: `rg -n "R17.*状态: REVIEW|R18.*状态: READY|R19.*状态: READY|R4.*BLOCKED|R5.*PR 审查包" docs\coordination\TASK_BOARD.md`
- Result: source data now includes R18/R19 as follow-up candidates, keeps R17 in REVIEW, and preserves R4/R5 as unresolved gates.
