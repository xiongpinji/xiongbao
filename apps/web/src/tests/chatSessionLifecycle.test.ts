import {
  resolveInitialConversationId,
  shouldLoadConversationHistory,
  shouldResetChatSession,
  withStreamingConversationHistoryGuard,
} from "../pages/chatSessionLifecycle";

type StreamingConversationSetter = (
  update: string | null | ((current: string | null) => string | null),
) => void;

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

  it("suppresses history while the announced conversation is streaming", async () => {
    const state = createStreamingConversationState();
    let historyGets = 0;

    await withStreamingConversationHistoryGuard(state.set, async (onStarted) => {
      onStarted("new-conversation");
      if (shouldLoadConversationHistory("new-conversation", state.current())) {
        historyGets += 1;
      }
    });

    assert(historyGets === 0, "A newly announced conversation must not request missing history");
  });

  it("releases the streaming guard after done, error, cancellation, and throw", async () => {
    const terminalCases: Array<{
      name: string;
      rejects: boolean;
      run: (onStarted: (id: string) => void) => void | Promise<void>;
    }> = [
      {
        name: "done",
        rejects: false,
        run: async (onStarted) => { onStarted("done"); },
      },
      {
        name: "error",
        rejects: true,
        run: async (onStarted) => {
          onStarted("error");
          throw new Error("stream error");
        },
      },
      {
        name: "cancel",
        rejects: true,
        run: async (onStarted) => {
          onStarted("cancel");
          throw new DOMException("cancelled", "AbortError");
        },
      },
      {
        name: "throw",
        rejects: true,
        run: (onStarted) => {
          onStarted("throw");
          throw new Error("synchronous throw");
        },
      },
    ];

    for (const terminalCase of terminalCases) {
      const state = createStreamingConversationState();
      let rejected = false;
      try {
        await withStreamingConversationHistoryGuard(state.set, terminalCase.run);
      } catch {
        rejected = true;
      }
      assert(rejected === terminalCase.rejects, `${terminalCase.name} result must propagate`);
      assert(state.current() === null, `${terminalCase.name} must release the streaming guard`);
    }
  });

  it("does not let an older stream clear a newer stream guard", async () => {
    const state = createStreamingConversationState();

    await withStreamingConversationHistoryGuard(state.set, async (onStarted) => {
      onStarted("old-conversation");
      state.set("new-conversation");
    });

    assert(
      state.current() === "new-conversation",
      "An older stream terminal event must preserve the newer stream guard",
    );
  });

});

function createStreamingConversationState() {
  let value: string | null = null;
  const set: StreamingConversationSetter = (update) => {
    value = typeof update === "function" ? update(value) : update;
  };
  return { current: () => value, set };
}
