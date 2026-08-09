import {
  resolveInitialConversationId,
  shouldLoadConversationHistory,
  shouldResetChatSession,
} from "../pages/chatSessionLifecycle";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

describe("chat session lifecycle", () => {
  it("preserves a selected conversation on first mount", () => {
    assert(
      !shouldResetChatSession(null, "session-a"),
      "Initial ChatPage mount must not clear the conversation selected in the sidebar",
    );
  });

  it("resets only when the new-chat session key actually changes", () => {
    assert(
      !shouldResetChatSession("session-a", "session-a"),
      "Unchanged session key must preserve the current conversation",
    );
    assert(
      shouldResetChatSession("session-a", "session-b"),
      "A new-chat action must reset the current conversation",
    );
  });

  it("restores the persisted conversation after a full page reload", () => {
    assert(
      resolveInitialConversationId(null, "persisted-conversation") ===
        "persisted-conversation",
      "Reloaded ChatPage must restore its persisted conversation",
    );
    assert(
      resolveInitialConversationId("selected-conversation", "persisted-conversation") ===
        "selected-conversation",
      "An explicit sidebar selection must take precedence over persisted state",
    );
  });

  it("does not load history for a conversation announced by the active stream", () => {
    assert(
      !shouldLoadConversationHistory("new-conversation", "new-conversation"),
      "The conversation announced by the active stream must keep its in-memory messages",
    );
    assert(
      shouldLoadConversationHistory("persisted-conversation", null),
      "A reloaded persisted conversation must load history",
    );
    assert(
      shouldLoadConversationHistory("selected-conversation", "other-conversation"),
      "A non-streaming sidebar selection must load history",
    );
  });
});
