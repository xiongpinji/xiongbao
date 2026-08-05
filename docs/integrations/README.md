# GitHub 集成：X-Agent Code Review

对标 OpenAI Codex 的 Code Review：PR 自动评审 + 仓库自定义规则。

## 快速接入

1. 把 [`github-code-review.yml`](./github-code-review.yml) 复制到被审仓库的
   `.github/workflows/code-review.yml`。
2. 在仓库 Secrets 配置 LLM key（如 `XAGENT_LLM__OPENAI_API_KEY`）。
3. 打开 PR 即自动评审并把结构化结论（findings 表格 + verdict）评论到 PR。

## 与 Codex 对齐的自定义规则（AGENTS.md）

评审服务复用 `core/instructions.get_layered_instructions` 的分层加载：

- **用户级** `~/.xagent/AGENTS.md` < **仓库根** `AGENTS.md` < **子目录级**（按 diff
  涉及文件就近选择，越深优先级越高），冲突时高优先级覆盖低优先级。
- 规则注入到 standards 维度（风格与项目规范符合度）的评审 prompt；
  该维度的每条 finding 带 `rule_ref` 字段，引用被违反的规则原文。

## 输出契约

- **findings**：`file / line / severity（critical|high|medium|low|info）/ issue /
  suggestion / dimension / rule_ref`
- **verdict**：任一 critical/high → `request_changes`；仅有中低危 → `comment`；
  无发现 → `approve`
- **summary**：LLM 综合摘要（失败时降级为确定性统计摘要）

## 本地 / API 用法

```bash
# CLI（本地直调，无需起 API 服务）
xagent review --repo . --base main --head HEAD --output review.md
xagent review --repo . --diff-file pr.diff        # repo 非 git 或不可访问时

# API
POST /api/v1/code-review        {"diff": "..."} 或 {"repo": ".", "base": "main"}
GET  /api/v1/code-review/{id}   查询评审结果（RBAC: code_review:read）
```
