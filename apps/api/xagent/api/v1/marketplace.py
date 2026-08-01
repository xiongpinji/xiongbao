"""插件/技能市场接口。

提供技能的发布、发现、安装、版本管理能力。
构建于 Skill Store 之上，增加市场化元数据（作者、评分、下载量、版本）。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


# ─── 数据模型 ───


@dataclass
class MarketEntry:
    """市场条目。"""

    entry_id: str
    name: str
    description: str
    author: str
    tenant_id: str
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0
    skill_id: str = ""  # 关联的 skill store ID
    published_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "published"  # published | draft | revoked

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "tags": self.tags,
            "downloads": self.downloads,
            "rating": round(self.rating, 2),
            "rating_count": self.rating_count,
            "skill_id": self.skill_id,
            "published_at": self.published_at,
            "status": self.status,
        }


# ─── 内存存储（生产替换为 DB） ───

_market: dict[str, MarketEntry] = {}


def _seed_market() -> None:
    """初始化示例条目。"""
    if _market:
        return
    samples = [
        ("代码审查助手", "自动审查 PR 代码质量", ["code", "review"]),
        ("数据可视化", "从 CSV 生成图表", ["data", "chart"]),
        ("API 文档生成", "从 OpenAPI 生成 Markdown 文档", ["api", "docs"]),
        ("翻译专家", "多语言互译，保留格式", ["i18n", "translate"]),
        ("测试用例生成", "根据函数签名生成 pytest 用例", ["test", "pytest"]),
    ]
    for name, desc, tags in samples:
        eid = uuid.uuid4().hex[:10]
        _market[eid] = MarketEntry(
            entry_id=eid,
            name=name,
            description=desc,
            author="X-Agent Official",
            tenant_id="default",
            tags=tags,
            downloads=100 + hash(name) % 500,
            rating=4.0 + (hash(name) % 10) / 10,
            rating_count=10 + hash(name) % 50,
        )


_seed_market()


# ─── 查询 ───


@router.get("", summary="浏览市场")
async def browse_market(
    q: str = "",
    tag: str = "",
    sort: str = "downloads",
    limit: int = 20,
    principal: Principal = Depends(require_permission("system", "read")),
):
    """搜索/浏览市场条目。支持关键词、标签过滤、排序。"""
    entries = [e for e in _market.values() if e.status == "published"]
    if q:
        q_lower = q.lower()
        entries = [e for e in entries if q_lower in e.name.lower() or q_lower in e.description.lower()]
    if tag:
        entries = [e for e in entries if tag in e.tags]
    # 排序
    if sort == "rating":
        entries.sort(key=lambda e: e.rating, reverse=True)
    elif sort == "newest":
        entries.sort(key=lambda e: e.published_at, reverse=True)
    else:
        entries.sort(key=lambda e: e.downloads, reverse=True)
    return {"entries": [e.to_dict() for e in entries[:limit]], "total": len(entries)}


@router.get("/{entry_id}", summary="条目详情")
async def get_entry(
    entry_id: str,
    principal: Principal = Depends(require_permission("system", "read")),
):
    entry = _market.get(entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    return entry.to_dict()


# ─── 发布 ───


class PublishIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list)
    version: str = Field(default="1.0.0")
    skill_id: str = Field(default="", description="关联已有 skill ID")


@router.post("/publish", summary="发布到市场")
async def publish_entry(
    body: PublishIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    eid = uuid.uuid4().hex[:10]
    entry = MarketEntry(
        entry_id=eid,
        name=body.name,
        description=body.description,
        author=principal.user_id,
        tenant_id=principal.tenant_id,
        version=body.version,
        tags=body.tags,
        skill_id=body.skill_id,
    )
    _market[eid] = entry
    return {"published": True, "entry": entry.to_dict()}


# ─── 安装 ───


@router.post("/{entry_id}/install", summary="安装插件")
async def install_entry(
    entry_id: str,
    principal: Principal = Depends(require_permission("system", "read")),
):
    entry = _market.get(entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    entry.downloads += 1
    return {
        "installed": True,
        "entry_id": entry_id,
        "name": entry.name,
        "version": entry.version,
        "message": f"已安装 {entry.name} v{entry.version} 到租户 {principal.tenant_id}",
    }


# ─── 评分 ───


class RateIn(BaseModel):
    score: float = Field(..., ge=1.0, le=5.0)


@router.post("/{entry_id}/rate", summary="评分")
async def rate_entry(
    entry_id: str,
    body: RateIn,
    principal: Principal = Depends(require_permission("system", "read")),
):
    entry = _market.get(entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    # 加权平均
    total = entry.rating * entry.rating_count + body.score
    entry.rating_count += 1
    entry.rating = total / entry.rating_count
    return {"rated": True, "new_rating": round(entry.rating, 2)}


# ─── 版本更新 ───


class VersionUpdateIn(BaseModel):
    version: str = Field(..., min_length=1)
    description: str = Field(default="")


@router.put("/{entry_id}/version", summary="发布新版本")
async def update_version(
    entry_id: str,
    body: VersionUpdateIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    entry = _market.get(entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    entry.version = body.version
    entry.updated_at = time.time()
    if body.description:
        entry.description = body.description
    return {"updated": True, "entry": entry.to_dict()}


# ─── 下架 ───


@router.post("/{entry_id}/revoke", summary="下架条目")
async def revoke_entry(
    entry_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    entry = _market.get(entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    entry.status = "revoked"
    return {"revoked": True, "entry_id": entry_id}
