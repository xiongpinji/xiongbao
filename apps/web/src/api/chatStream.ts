export interface AgentRunStreamHandlers {
  onFinalAnswer?: (answer: string) => void;
  onError?: (error: string) => void;
  onDone?: (runId: string) => void;
}

interface SseEvent {
  eventName: string;
  data: Record<string, unknown>;
}

function parseSseEvent(block: string): SseEvent | null {
  const lines = block.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event:"));
  const dataLines = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim());
  if (!dataLines.length) return null;

  const data = JSON.parse(dataLines.join("\n"));
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    return null;
  }

  return {
    eventName: eventLine?.slice(6).trim() ?? "message",
    data: data as Record<string, unknown>,
  };
}

function applySseEvent(
  event: SseEvent,
  handlers: AgentRunStreamHandlers,
): string | null {
  const finalAnswer = event.data.final_answer;
  if (typeof finalAnswer === "string") {
    handlers.onFinalAnswer?.(finalAnswer);
  }

  const error = event.data.error;
  if (typeof error === "string") {
    handlers.onError?.(error);
  }

  const runId = event.data.run_id;
  if (event.eventName === "done" && typeof runId === "string" && runId) {
    handlers.onDone?.(runId);
    return runId;
  }

  return null;
}

export async function readAgentRunStream(
  resp: Response,
  handlers: AgentRunStreamHandlers = {},
): Promise<string> {
  if (!resp.ok || !resp.body) throw new Error(`SSE ${resp.status}`);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const eventBlock of events) {
      const event = parseSseEvent(eventBlock);
      if (!event) continue;

      const runId = applySseEvent(event, handlers);
      if (runId) return runId;
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    const event = parseSseEvent(buffer);
    if (event) {
      const runId = applySseEvent(event, handlers);
      if (runId) return runId;
    }
  }

  throw new Error("SSE stream ended before done event");
}
