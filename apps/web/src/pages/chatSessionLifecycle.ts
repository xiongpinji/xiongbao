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
