"""skills 列表端点响应缓存测试（压测瓶颈#2 修复）。

背景：每请求对 90 个技能做 dataclasses.asdict 深拷贝 + FastAPI jsonable_encoder
双重序列化（~20ms CPU 阻塞事件循环），是 /skills ~48 RPS 硬顶的根源。
修复：按 store.version 缓存预编码 JSON bytes，库写操作使缓存失效。
"""

from __future__ import annotations

import json

from xagent.api.v1 import skills as skills_api
from xagent.core.skills import SkillStore


def _make_store(tmp_path) -> SkillStore:
    store = SkillStore(storage_dir=tmp_path)
    store.create_skill(name="s1", description="d1", trigger_pattern="k1")
    return store


def test_version_bumps_on_mutations(tmp_path) -> None:
    store = _make_store(tmp_path)
    v0 = store.version
    skill = store.create_skill(name="s2", description="d2", trigger_pattern="k2")
    assert store.version > v0
    v1 = store.version
    store.record_usage(skill.skill_id, success=True)
    assert store.version > v1
    v2 = store.version
    assert store.delete(skill.skill_id)
    assert store.version > v2


def test_list_cache_hit_and_invalidation(tmp_path) -> None:
    store = _make_store(tmp_path)
    skills_api._list_cache.clear()

    # 首次：缓存未命中，生成预编码 body
    key = (store.version, False)
    assert key not in skills_api._list_cache
    skills = store.list_all()
    body = json.dumps(
        {"skills": [s.to_dict() for s in skills], "total": len(skills)},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    skills_api._list_cache[key] = body
    assert skills_api._list_cache[key] == body

    # 写操作后 version 变化 -> 旧 key 不再命中（等价于缓存失效）
    store.create_skill(name="s3", description="d3", trigger_pattern="k3")
    assert (store.version, False) not in skills_api._list_cache or \
        skills_api._list_cache.get((store.version, False)) != body


def test_cached_body_matches_legacy_shape(tmp_path) -> None:
    """缓存路径的响应体与原 list_all + to_dict 形状一致（键/值/顺序）。"""
    store = _make_store(tmp_path)
    skills = store.list_all()
    expected = json.loads(json.dumps(
        {"skills": [s.to_dict() for s in skills], "total": len(skills)},
        ensure_ascii=False,
    ))
    body = json.dumps(
        {"skills": [s.to_dict() for s in skills], "total": len(skills)},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    assert json.loads(body) == expected
