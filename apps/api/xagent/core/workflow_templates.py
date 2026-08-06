"""工作流模板持久化存储（文件级 JSON）。"""

from __future__ import annotations

import json
import time
import uuid
from builtins import list as list_type
from dataclasses import asdict, dataclass, field
from pathlib import Path

from xagent.infra.logging import get_logger

logger = get_logger("xagent.workflow_templates")

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "workflow_templates"


@dataclass
class WorkflowTemplate:
    template_id: str
    name: str
    tenant_id: str
    version: int = 1
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_view(self) -> dict:
        return asdict(self)


class WorkflowTemplateStore:
    """文件级工作流模板存储，按 tenant 隔离。"""

    def __init__(self, data_dir: Path | None = None):
        self._dir = data_dir or _DATA_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, WorkflowTemplate] = {}
        self._load_all()

    def _load_all(self) -> None:
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tpl = WorkflowTemplate(**data)
                self._cache[tpl.template_id] = tpl
            except Exception:  # noqa: S112
                continue

    def _persist(self, tpl: WorkflowTemplate) -> None:
        path = self._dir / f"{tpl.template_id}.json"
        path.write_text(json.dumps(asdict(tpl), ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self, tenant_id: str) -> list[WorkflowTemplate]:
        return [t for t in self._cache.values() if t.tenant_id == tenant_id]

    def get(self, template_id: str, tenant_id: str) -> WorkflowTemplate | None:
        tpl = self._cache.get(template_id)
        if tpl and tpl.tenant_id == tenant_id:
            return tpl
        return None

    def save(
        self, tenant_id: str, name: str, nodes: list_type[dict], edges: list_type[dict],
        template_id: str | None = None,
    ) -> WorkflowTemplate:
        """保存或更新模板。若 template_id 存在则版本+1。"""
        if template_id and template_id in self._cache:
            existing = self._cache[template_id]
            if existing.tenant_id != tenant_id:
                raise ValueError("无权修改此模板")
            existing.name = name
            existing.nodes = nodes
            existing.edges = edges
            existing.version += 1
            existing.updated_at = time.time()
            self._persist(existing)
            logger.info(
                "workflow_template_updated", template_id=template_id, version=existing.version,
            )
            return existing

        tpl = WorkflowTemplate(
            template_id=template_id or uuid.uuid4().hex[:12],
            name=name,
            tenant_id=tenant_id,
            nodes=nodes,
            edges=edges,
        )
        self._cache[tpl.template_id] = tpl
        self._persist(tpl)
        logger.info("workflow_template_created", template_id=tpl.template_id)
        return tpl

    def delete(self, template_id: str, tenant_id: str) -> bool:
        tpl = self._cache.get(template_id)
        if not tpl or tpl.tenant_id != tenant_id:
            return False
        del self._cache[template_id]
        path = self._dir / f"{template_id}.json"
        path.unlink(missing_ok=True)
        return True


_store: WorkflowTemplateStore | None = None


def get_template_store() -> WorkflowTemplateStore:
    global _store
    if _store is None:
        _store = WorkflowTemplateStore()
    return _store
