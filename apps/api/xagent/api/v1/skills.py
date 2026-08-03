"""Skill 自进化管理接口。

提供技能的 CRUD、演化、淘汰、统计等管理能力。
Agent 在任务执行中会自动提炼技能，此接口用于人工查看/干预。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from xagent.core.skills import get_skill_store
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/skills", tags=["skills"])


# ─── 查询 ───

# list 响应缓存：key=(store.version, include_retired)。
# 压测诊断（2026-08-03）：每请求 90 技能双重序列化（dataclasses.asdict 深拷贝 +
# FastAPI jsonable_encoder 逐字段遍历）消耗 ~20ms CPU 阻塞事件循环，是 skills
# 端点 ~48 RPS 硬顶的根源（并非此前猜测的目录扫描——SkillStore 本身全内存）。
# 预编码为 JSON bytes 并以 Response 直接返回，可跳过 jsonable_encoder；
# 库任何写操作（_persist/delete）递增 version 使缓存整体失效。
_list_cache: dict[tuple[int, bool], bytes] = {}


@router.get("", summary="列出所有技能")
async def list_skills(
    include_retired: bool = False,
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    key = (store.version, include_retired)
    body = _list_cache.get(key)
    if body is None:
        skills = store.list_all(include_retired=include_retired)
        # separators 与 starlette JSONResponse 一致（紧凑），保持响应字节级口径
        body = json.dumps(
            {"skills": [s.to_dict() for s in skills], "total": len(skills)},
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
    return store.stats()


@router.get("/{skill_id}", summary="获取技能详情")
async def get_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    skill = store.get(skill_id)
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


@router.post("/{skill_id}/evolve-auto", summary="自动进化闭环（变体生成→评测→优胜入库）")
async def evolve_auto(
    skill_id: str,
    body: EvolveAutoIn | None = None,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    body = body or EvolveAutoIn()
    result = await store.evolve_auto(
        skill_id, n_variants=body.n_variants, threshold=body.threshold,
    )
    if result is None:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    return result


# ─── 淘汰/恢复 ───


@router.post("/{skill_id}/retire", summary="手动淘汰技能")
async def retire_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    skill = store.get(skill_id)
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
    if not store.get(skill_id):
        raise HTTPException(404, f"skill '{skill_id}' not found")
    ok = store.restore_skill(skill_id)
    return {"restored": ok, "skill_id": skill_id}


@router.post("/retire-low-performers", summary="批量淘汰低效技能")
async def retire_low_performers(
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    retired = store.retire_low_performers()
    return {"retired_count": len(retired), "retired_ids": retired}


# ─── 删除 ───


@router.delete("/{skill_id}", summary="删除技能")
async def delete_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    store = get_skill_store()
    deleted = store.delete(skill_id)
    if not deleted:
        raise HTTPException(404, f"skill '{skill_id}' not found")
    return {"deleted": True, "skill_id": skill_id}


# ─── 匹配测试 ───


class SkillMatchIn(BaseModel):
    goal: str = Field(..., min_length=1, description="测试目标文本")


@router.post("/match", summary="测试技能匹配")
async def match_skills(
    body: SkillMatchIn,
    principal: Principal = Depends(require_permission("system", "read")),
):
    store = get_skill_store()
    matched = store.match(body.goal)
    return {
        "goal": body.goal,
        "matched": [s.to_dict() for s in matched],
        "prompt_injection": store.build_prompt_injection(body.goal),
    }
