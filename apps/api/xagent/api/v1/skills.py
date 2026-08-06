"""Skill 自进化管理接口。

提供技能的 CRUD、演化、淘汰、统计等管理能力。
Agent 在任务执行中会自动提炼技能，此接口用于人工查看/干预。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from xagent.core.skills import SkillStore, get_skill_store
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/skills", tags=["skills"])


# ─── 查询 ───

# list 响应缓存：key=(store.version, include_retired, tenant_id)。
# 压测诊断（2026-08-03）：每请求 90 技能双重序列化（dataclasses.asdict 深拷贝 +
# FastAPI jsonable_encoder 逐字段遍历）消耗 ~20ms CPU 阻塞事件循环，是 skills
# 端点 ~48 RPS 硬顶的根源（并非此前猜测的目录扫描——SkillStore 本身全内存）。
# 预编码为 JSON bytes 并以 Response 直接返回，可跳过 jsonable_encoder；
# 库任何写操作（_persist/delete）递增 version 使缓存整体失效。
_list_cache: dict[tuple[int, bool, str], bytes] = {}


def _visible_pending(store: SkillStore, tenant_id: str) -> list[dict]:
    return [
        item
        for item in store.list_pending_evolutions()
        if store.get_for_tenant(str(item.get("skill_id", "")), tenant_id)
        is not None
    ]


def _list_view(skill) -> dict:
    value = skill.to_dict()
    hint = str(value.get("system_prompt_hint", ""))
    value["system_prompt_truncated"] = len(hint) > 500
    value["system_prompt_hint"] = hint[:500]
    return value


@router.get("", summary="列出所有技能")
async def list_skills(
    include_retired: bool = False,
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    key = (store.version, include_retired, principal.tenant_id)
    body = _list_cache.get(key)
    if body is None:
        skills = store.list_all(
            include_retired=include_retired, tenant_id=principal.tenant_id
        )
        # separators 与 starlette JSONResponse 一致（紧凑），保持响应字节级口径
        body = json.dumps(
            {"skills": [_list_view(skill) for skill in skills], "total": len(skills)},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        _list_cache.clear()
        _list_cache[key] = body
    return Response(content=body, media_type="application/json")


@router.get("/stats", summary="技能库统计")
async def skill_stats(
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    return store.stats(tenant_id=principal.tenant_id)


@router.get("/{skill_id}", summary="获取技能详情")
async def get_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    skill = store.get_for_tenant(skill_id, principal.tenant_id)
    if not skill:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    return skill.to_dict()


# ─── 创建 ───


class SkillCreateIn(BaseModel):
    name: str = Field(..., min_length=1, description="技能名称")
    description: str = Field(default="", description="技能描述")
    trigger_pattern: str = Field(..., min_length=1, description="触发关键词(|分隔)")
    system_prompt_hint: str = Field(default="", description="注入提示")
    steps: list[dict] = Field(default_factory=list, description="工具调用序列")
    tags: list[str] = Field(default_factory=list, description="标签")


@router.post("", summary="手动创建技能")
async def create_skill(
    body: SkillCreateIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    skill = store.create_skill(
        name=body.name,
        description=body.description,
        trigger_pattern=body.trigger_pattern,
        system_prompt_hint=body.system_prompt_hint,
        steps=body.steps,
        tags=body.tags,
        source="manual",
        tenant_id=principal.tenant_id,
    )
    return {"created": True, "skill": skill.to_dict()}


# ─── 演化/更新 ───


class SkillEvolveIn(BaseModel):
    description: str | None = None
    system_prompt_hint: str | None = None
    trigger_pattern: str | None = None
    steps: list[dict] | None = None
    change_reason: str = Field(default="", description="变更原因")


@router.put("/{skill_id}/evolve", summary="迭代升级技能")
async def evolve_skill(
    skill_id: str,
    body: SkillEvolveIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    if store.get_for_tenant(skill_id, principal.tenant_id) is None:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    skill = store.evolve_skill(
        skill_id=skill_id,
        description=body.description,
        system_prompt_hint=body.system_prompt_hint,
        trigger_pattern=body.trigger_pattern,
        steps=body.steps,
        change_reason=body.change_reason,
    )
    if not skill:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    return {"evolved": True, "skill": skill.to_dict()}


class EvolveAutoIn(BaseModel):
    n_variants: int = Field(default=2, ge=1, le=5, description="生成变体数")
    threshold: float = Field(
        default=0.1, ge=0.0, le=1.0, description="采纳阈值（变体须领先父代的分差）"
    )
    require_review: bool = Field(
        default=False,
        description="人工审核模式：评测通过后挂起待审，须 approve 才入库（对标 GEPA 人工 PR）",
    )


@router.post("/{skill_id}/evolve-auto", summary="自动进化闭环（变体生成→评测→优胜入库）")
async def evolve_auto(
    skill_id: str,
    body: EvolveAutoIn | None = None,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    if store.get_for_tenant(skill_id, principal.tenant_id) is None:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    body = body or EvolveAutoIn()
    result = await store.evolve_auto(
        skill_id, n_variants=body.n_variants, threshold=body.threshold,
        require_review=body.require_review,
    )
    if result is None:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    # 变体评测留证（V3-2a）：全量结果落 evidence_records，可回溯每次进化判定
    try:
        from xagent.infra.db import get_sessionmaker
        from xagent.infra.repos.evidence import persist_evidence_bundle

        async with get_sessionmaker()() as session:
            await persist_evidence_bundle(
                session,
                tenant_id=principal.tenant_id,
                run_id="",
                task_id=skill_id,
                records=[{"kind": "skill.evolve_auto", "payload": result}],
            )
            await session.commit()
    except Exception:  # noqa: S110  证据写入失败不影响进化主流程
        pass
    return result


# ─── 进化人工审核队列（V3-2b） ───


@router.get("/evolutions/pending", summary="列出待人工审核的进化条目")
async def list_pending_evolutions(
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    items = _visible_pending(store, principal.tenant_id)
    return {"pending": items, "total": len(items)}


@router.post("/evolutions/{pending_id}/approve", summary="批准进化（优胜变体入库）")
async def approve_evolution(
    pending_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    pending = next(
        (
            item
            for item in _visible_pending(store, principal.tenant_id)
            if item.get("pending_id") == pending_id
        ),
        None,
    )
    if pending is None:
        raise HTTPException(404, f"pending evolution '{pending_id}' not found")
    result = store.approve_evolution(pending_id)
    if result is None:
        raise HTTPException(404, f"pending evolution '{pending_id}' not found")
    return result


@router.post("/evolutions/{pending_id}/reject", summary="拒绝进化（丢弃变体）")
async def reject_evolution(
    pending_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    pending = next(
        (
            item
            for item in _visible_pending(store, principal.tenant_id)
            if item.get("pending_id") == pending_id
        ),
        None,
    )
    if pending is None:
        raise HTTPException(404, f"pending evolution '{pending_id}' not found")
    if not store.reject_evolution(pending_id):
        raise HTTPException(404, f"pending evolution '{pending_id}' not found")
    return {"rejected": True, "pending_id": pending_id}


# ─── 淘汰/恢复 ───


@router.post("/{skill_id}/retire", summary="手动淘汰技能")
async def retire_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    skill = store.get_for_tenant(skill_id, principal.tenant_id)
    if not skill:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    skill.retired = True
    store._persist(skill)
    return {"retired": True, "skill_id": skill_id}


@router.post("/{skill_id}/restore", summary="恢复已淘汰技能")
async def restore_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    if not store.get_for_tenant(skill_id, principal.tenant_id):
        raise HTTPException(404, f"skill '{skill_id}' not found")
    ok = store.restore_skill(skill_id)
    return {"restored": ok, "skill_id": skill_id}


@router.post("/retire-low-performers", summary="批量淘汰低效技能")
async def retire_low_performers(
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    retired = store.retire_low_performers(tenant_id=principal.tenant_id)
    return {"retired_count": len(retired), "retired_ids": retired}


# ─── 删除 ───


@router.delete("/{skill_id}", summary="删除技能")
async def delete_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    if store.get_for_tenant(skill_id, principal.tenant_id) is None:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    deleted = store.delete(skill_id)
    if not deleted:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    return {"deleted": True, "skill_id": skill_id}


# ─── SKILL.md 导入（agentskills.io 生态兼容）───


class SkillMdImportIn(BaseModel):
    content: str = Field(..., min_length=1, description="SKILL.md 全文（含 frontmatter）")
    origin: str = Field(default="", description="来源标识（如 repo 路径/tap 名）")


class SkillMdBatchImportIn(BaseModel):
    items: list[SkillMdImportIn] = Field(..., min_length=1, description="批量导入项")


@router.post("/import/skillmd", summary="导入单个 SKILL.md（过质量门禁）")
async def import_skillmd_endpoint(
    body: SkillMdImportIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    from xagent.core.skills.importer import import_skillmd

    store = get_skill_store()
    skill, reason = import_skillmd(
        store, body.content, body.origin, tenant_id=principal.tenant_id
    )
    if skill is None:
        return {"imported": False, "reason": reason}
    return {"imported": True, "skill": skill.to_dict()}


@router.post("/import/skillmd/batch", summary="批量导入 SKILL.md（逐条过门禁）")
async def import_skillmd_batch_endpoint(
    body: SkillMdBatchImportIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    from xagent.core.skills.importer import import_skillmd_batch

    store = get_skill_store()
    return import_skillmd_batch(
        store,
        [item.model_dump() for item in body.items],
        tenant_id=principal.tenant_id,
    )


# ─── 匹配测试 ───


class SkillMatchIn(BaseModel):
    goal: str = Field(..., min_length=1, description="测试目标文本")


@router.post("/match", summary="测试技能匹配")
async def match_skills(
    body: SkillMatchIn,
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    matched = store.match(body.goal, tenant_id=principal.tenant_id)
    return {
        "goal": body.goal,
        "matched": [s.to_dict() for s in matched],
        "prompt_injection": store.build_prompt_injection(
            body.goal, tenant_id=principal.tenant_id
        ),
    }
