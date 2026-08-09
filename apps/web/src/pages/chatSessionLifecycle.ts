export function resolveInitialConversationId(
  activeConversationId: string | null,
  persistedConversationId: string | null,
): string | null {
  return activeConversationId ?? (persistedConversationId?.trim() || null);
}

export function shouldResetChatSession(
  previousSessionKey: string | null,
  currentSessionKey: string,
): boolean {
  return previousSessionKey !== null && previousSessionKey !== currentSessionKey;
}

export function shouldLoadConversationHistory(
  conversationId: string | null,
  streamingConversationId: string | null,
): boolean {
  return conversationId !== null && conversationId !== streamingConversationId;
}

type StreamingConversationSetter = (
  update: string | null | ((current: string | null) => string | null),
) => void;

export async function withStreamingConversationHistoryGuard<T>(
  setStreamingConversationId: StreamingConversationSetter,
  run: (onStarted: (conversationId: string) => void) => T | Promise<T>,
): Promise<T> {
  let startedConversationId: string | null = null;
  try {
    return await run((conversationId) => {
      startedConversationId = conversationId;
      setStreamingConversationId(conversationId);
    });
  } finally {
    if (startedConversationId !== null) {
      const completedConversationId = startedConversationId;
      setStreamingConversationId((current) =>
        current === completedConversationId ? null : current,
      );
    }
  }
}
