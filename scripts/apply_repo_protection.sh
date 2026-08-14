#!/usr/bin/env bash
# X-Agent 仓库服务端保护一键配置（需 GitHub Pro/Team 或仓库转为 public 后执行）。
#
# 免费版私有仓库不支持服务端分支/tag 保护（2026-08-14 实测 API 返回
# "Upgrade to GitHub Pro or make this repository public"）。升级后运行：
#
#   GITHUB_TOKEN=<有 repo 权限的 token> bash scripts/apply_repo_protection.sh
#
# 当前免费层的等效兜底已由 CI 标签哨兵提供：
#   .github/workflows/ci.yml -> release-version -> "Release tag immutability sentinel"
set -euo pipefail

REPO="xiongpinji/xiongbao"
API="https://api.github.com"
AUTH="Authorization: Bearer ${GITHUB_TOKEN:?请先 export GITHUB_TOKEN}"

echo "== 1/3 master 分支保护（禁强推/禁删除/线性历史/CI 全绿才可合并）=="
curl -sf -X PUT -H "$AUTH" -H "Accept: application/vnd.github+json" \
  "$API/repos/$REPO/branches/master/protection" -d '{
    "required_status_checks": {"strict": true, "contexts": [
      "backend","frontend","license-gate","config-governance",
      "e2e-api","load-test","promptfoo-eval","release-version"]},
    "enforce_admins": true,
    "required_pull_request_reviews": null,
    "restrictions": null,
    "allow_force_pushes": false,
    "allow_deletions": false,
    "required_linear_history": true
  }' > /dev/null && echo "master protection: OK"

echo "== 2/3 v* 标签保护（禁止删除/重打发布标签）=="
curl -sf -X POST -H "$AUTH" "$API/repos/$REPO/tags/protection" \
  -d '{"pattern":"v*"}' > /dev/null && echo "tag protection: OK"

echo "== 3/3 ruleset 兜底（分支规则集，双保险）=="
curl -sf -X POST -H "$AUTH" "$API/repos/$REPO/rulesets" -d '{
    "name": "master-release-discipline",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/heads/master"], "exclude": []}},
    "rules": [
      {"type": "deletion"},
      {"type": "non_fast_forward"},
      {"type": "required_status_checks", "parameters": {
        "required_status_checks": [
          {"context": "backend"}, {"context": "frontend"},
          {"context": "license-gate"}, {"context": "e2e-api"}],
        "strict_required_status_checks_policy": true}}
    ]
  }' > /dev/null && echo "ruleset: OK"

echo ""
echo "全部保护规则已生效。建议再到仓库 Settings 页面肉眼复核一次。"
