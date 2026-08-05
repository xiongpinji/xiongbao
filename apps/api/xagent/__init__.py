"""X-Agent — 面向企业的自主智能体框架（开源重构版）。

包结构：
    infra/       横切基础设施（settings/db/cache/logging/health）
    adapters/    开源底座适配层（llm/memory/observability/...）
    core/        编排内核（orchestration/agents/workflow）
    domains/     独有业务（creative_studio/open_source_discovery/billing）
    enterprise/  RBAC/SSO/审计/多租户
    api/         FastAPI 路由（薄）
"""

__version__ = "1.0.0"
