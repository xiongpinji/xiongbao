"""Optional orchestration adapters must report honest terminal outcomes."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

from xagent.enterprise.auth.principal import Principal


def _principal() -> Principal:
    return Principal(
        user_id="u",
        tenant_id="t",
        roles=frozenset({"member"}),
    )


def _install_deerflow_client(monkeypatch, client) -> None:
    package = ModuleType("deerflow")
    package.__path__ = []
    client_module = ModuleType("deerflow.client")
    client_module.DeerFlowClient = lambda: client
    monkeypatch.setitem(sys.modules, "deerflow", package)
    monkeypatch.setitem(sys.modules, "deerflow.client", client_module)


async def test_deerflow_requires_a_final_event_for_success(monkeypatch) -> None:
    from xagent.core.orchestration.deerflow_loop import run_agent_deerflow

    client = SimpleNamespace(
        stream=lambda *args, **kwargs: iter(()),
        chat=lambda *args, **kwargs: {"content": "unused"},
    )
    _install_deerflow_client(monkeypatch, client)

    run = await run_agent_deerflow("silent", principal=_principal())

    assert run.status == "failed"
    assert run.error == "incomplete_run"


async def test_deerflow_double_failure_reports_error_status(monkeypatch) -> None:
    from xagent.core.orchestration.deerflow_loop import run_agent_deerflow

    def _stream_failure(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("stream down")

    def _chat_failure(*args, **kwargs):  # noqa: ARG001
        raise ValueError("chat down")

    client = SimpleNamespace(stream=_stream_failure, chat=_chat_failure)
    _install_deerflow_client(monkeypatch, client)

    run = await run_agent_deerflow("failure", principal=_principal())

    assert run.status == "failed"
    assert "chat down" in run.error
    assert run.events[-1].kind.value == "error"


async def test_deerflow_final_event_is_succeeded(monkeypatch) -> None:
    from xagent.core.orchestration.deerflow_loop import run_agent_deerflow

    events = [
        SimpleNamespace(
            type="messages-tuple",
            data={"type": "ai", "content": "done"},
        ),
        SimpleNamespace(type="end", data={}),
    ]
    client = SimpleNamespace(
        stream=lambda *args, **kwargs: iter(events),
        chat=lambda *args, **kwargs: {"content": "unused"},
    )
    _install_deerflow_client(monkeypatch, client)

    run = await run_agent_deerflow("success", principal=_principal())

    assert run.status == "succeeded"
    assert run.error == ""


async def test_deerflow_error_after_final_takes_precedence(monkeypatch) -> None:
    from xagent.core.orchestration.deerflow_loop import run_agent_deerflow

    def _stream_then_fail(*args, **kwargs):  # noqa: ARG001
        yield SimpleNamespace(
            type="messages-tuple",
            data={"type": "ai", "content": "premature"},
        )
        yield SimpleNamespace(type="end", data={})
        raise RuntimeError("stream failed after final")

    def _chat_failure(*args, **kwargs):  # noqa: ARG001
        raise ValueError("fallback failed")

    client = SimpleNamespace(stream=_stream_then_fail, chat=_chat_failure)
    _install_deerflow_client(monkeypatch, client)

    run = await run_agent_deerflow("late failure", principal=_principal())

    assert run.status == "failed"
    assert run.error == "fallback failed"
    assert run.events[-1].kind.value == "error"


def _load_langgraph_loop(monkeypatch):
    package = ModuleType("langgraph")
    package.__path__ = []
    graph_module = ModuleType("langgraph.graph")
    graph_module.END = object()
    graph_module.StateGraph = object
    monkeypatch.setitem(sys.modules, "langgraph", package)
    monkeypatch.setitem(sys.modules, "langgraph.graph", graph_module)
    monkeypatch.delitem(
        sys.modules, "xagent.core.orchestration.langgraph_loop", raising=False
    )
    return importlib.import_module("xagent.core.orchestration.langgraph_loop")


class _Trace:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):  # noqa: ARG002
        return None

    def set_input(self, value):  # noqa: ARG002
        return None

    def set_output(self, value):  # noqa: ARG002
        return None


class _Tracer:
    def trace(self, *args, **kwargs):  # noqa: ARG002
        return _Trace()


async def _run_langgraph_state(monkeypatch, final_state: dict):
    module = _load_langgraph_loop(monkeypatch)
    role = SimpleNamespace(
        name="tester",
        system_prompt="test",
        preferred_model=None,
        can_use=lambda name: False,
    )
    role_registry = SimpleNamespace(
        get=lambda name: role,
        match=lambda capabilities: role,
    )
    tool_registry = SimpleNamespace(specs=lambda: [])

    class _App:
        async def ainvoke(self, initial_state):  # noqa: ARG002
            return final_state

    graph = SimpleNamespace(compile=lambda: _App())
    monkeypatch.setattr(module, "get_role_registry", lambda: role_registry)
    monkeypatch.setattr(module, "get_tool_registry", lambda: tool_registry)
    monkeypatch.setattr(module, "get_llm_client", lambda: object())
    monkeypatch.setattr(module, "get_tracer", lambda: _Tracer())
    monkeypatch.setattr(module, "_build_graph", lambda *args, **kwargs: graph)
    return await module.run_agent_langgraph("goal", principal=_principal())


async def test_langgraph_unfinished_max_steps_is_failed(monkeypatch) -> None:
    run = await _run_langgraph_state(
        monkeypatch,
        {
            "messages": [{"role": "assistant", "content": "fallback"}],
            "events": [],
            "step": 6,
            "finished": False,
            "final_answer": "",
        },
    )

    assert run.final_answer == "fallback"
    assert run.status == "failed"
    assert run.error == "max_steps_exceeded"


async def test_langgraph_finished_state_is_succeeded(monkeypatch) -> None:
    run = await _run_langgraph_state(
        monkeypatch,
        {
            "messages": [{"role": "assistant", "content": "done"}],
            "events": [
                {"kind": "final", "content": "done", "step": 1}
            ],
            "step": 1,
            "finished": True,
            "final_answer": "done",
        },
    )

    assert run.status == "succeeded"
    assert run.error == ""
