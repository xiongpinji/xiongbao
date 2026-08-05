"""litellm_client._serialize_messages 双向配对修复测试。

覆盖：
- 合法 tool 序列原样透传（不插占位）；
- assistant tool_calls 缺配对 tool 消息（run 中途 Cancel 后 checkpoint 恢复）
  → 合成占位 tool 消息，保证发给 LLM 的序列合法；
- 孤儿 tool 消息 → 合成 assistant（既有行为保持）。
"""

from __future__ import annotations

from xagent.adapters.llm.base import Message
from xagent.adapters.llm.litellm_client import LiteLLMClient

_serialize = LiteLLMClient._serialize_messages


def _tc(call_id: str, name: str = "shell_exec") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


def _assert_sequence_legal(payload: list[dict]) -> None:
    """OpenAI 兼容接口要求：assistant 的每个 tool_call 都有配对 tool 消息，
    且每个 tool 消息都能回溯到某个 assistant 的 tool_call。"""
    known_calls: set[str] = set()
    answered: set[str] = set()
    for m in payload:
        if m["role"] == "assistant":
            for tc in m.get("tool_calls") or []:
                known_calls.add(tc["id"])
        elif m["role"] == "tool":
            assert m["tool_call_id"] in known_calls, f"孤儿 tool 消息: {m}"
            answered.add(m["tool_call_id"])
    assert known_calls == answered, f"未配对的 tool_calls: {known_calls - answered}"


def test_wellformed_tool_sequence_unchanged() -> None:
    msgs = [
        Message(role="user", content="查一下"),
        Message(role="assistant", content="", tool_calls=[_tc("c1")]),
        Message(role="tool", content="ok", tool_call_id="c1", name="shell_exec"),
        Message(role="assistant", content="结果是这样"),
    ]
    payload = _serialize(msgs)
    assert [m["role"] for m in payload] == ["user", "assistant", "tool", "assistant"]
    assert payload[2]["content"] == "ok"
    _assert_sequence_legal(payload)


def test_missing_tool_message_synthesizes_placeholder() -> None:
    """assistant 发了两个 tool_calls，只有一个 tool 结果（另一个被 Cancel）。"""
    msgs = [
        Message(role="user", content="并行做两件事"),
        Message(role="assistant", content="", tool_calls=[_tc("c1"), _tc("c2")]),
        Message(role="tool", content="第一件事完成", tool_call_id="c1"),
        Message(role="user", content="继续"),
    ]
    payload = _serialize(msgs)
    roles = [m["role"] for m in payload]
    assert roles == ["user", "assistant", "tool", "tool", "user"]
    placeholder = payload[3]
    assert placeholder["tool_call_id"] == "c2"
    assert "中断" in placeholder["content"]
    _assert_sequence_legal(payload)


def test_cancel_recovery_history_ends_with_unanswered_tool_calls() -> None:
    """run 取消后 checkpoint 恢复：历史以带 tool_calls 的 assistant 结尾。"""
    msgs = [
        Message(role="user", content="跑个任务"),
        Message(role="assistant", content="", tool_calls=[_tc("c9")]),
    ]
    payload = _serialize(msgs)
    assert [m["role"] for m in payload] == ["user", "assistant", "tool"]
    assert payload[-1]["tool_call_id"] == "c9"
    assert "无实际返回" in payload[-1]["content"]
    _assert_sequence_legal(payload)


def test_multiple_assistants_each_flushed_before_next() -> None:
    """连续两个 assistant 都有 tool_calls，第一个的全部缺结果。"""
    msgs = [
        Message(role="assistant", content="", tool_calls=[_tc("a1")]),
        Message(role="assistant", content="", tool_calls=[_tc("b1")]),
        Message(role="tool", content="done", tool_call_id="b1"),
    ]
    payload = _serialize(msgs)
    assert [m["role"] for m in payload] == ["assistant", "tool", "assistant", "tool"]
    assert payload[1]["tool_call_id"] == "a1"
    assert payload[3]["tool_call_id"] == "b1"
    assert payload[3]["content"] == "done"
    _assert_sequence_legal(payload)


def test_orphan_tool_message_still_synthesizes_assistant() -> None:
    """既有行为：孤儿 tool 消息前自动插入合成 assistant。"""
    msgs = [
        Message(role="user", content="hi"),
        Message(role="tool", content="遗留结果", tool_call_id="orphan1", name="file_read"),
    ]
    payload = _serialize(msgs)
    assert [m["role"] for m in payload] == ["user", "assistant", "tool"]
    synth = payload[1]
    assert synth["tool_calls"][0]["id"] == "orphan1"
    assert synth["tool_calls"][0]["function"]["name"] == "file_read"
    assert payload[2]["content"] == "遗留结果"
    _assert_sequence_legal(payload)


def test_plain_messages_untouched() -> None:
    msgs = [
        Message(role="system", content="你是助手"),
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！"),
    ]
    payload = _serialize(msgs)
    assert payload == [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
    ]
