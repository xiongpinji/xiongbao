export interface StepInfo {
  kind: string;
  step: number;
  tool?: string | null;
  content?: unknown;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
}

export interface AgentRunStreamHandlers {
  onFinalAnswer?: (answer: string) => void;
  onError?: (error: string) => void;
  onDone?: (runId: string, usage?: TokenUsage) => void;
  onStep?: (step: StepInfo) => void;
  onStarted?: (conversationId: string) => void;
  onToken?: (token: string) => void;
  onProgress?: (percent: number, step: number, maxSteps: number) => void;
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

  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    // 畸形 JSON（服务端截断/编码错误）——跳过该事件，不崩流
    return null;
  }
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
  // started 事件：返回 conversation_id
  if (event.eventName === "started") {
    const convId = event.data.conversation_id as string | undefined;
    if (convId) handlers.onStarted?.(convId);
  }

  // 后端 final 事件格式: {kind: "final", content: "...", step: N}
  const finalAnswer = event.data.final_answer ?? (
    event.data.kind === "final" ? event.data.content : undefined
  );
  if (typeof finalAnswer === "string") {
    handlers.onFinalAnswer?.(finalAnswer);
  }

  // 实时步骤事件（tool_call / tool_result / reason）
  const kind = event.data.kind as string | undefined;
  if (kind && ["tool_call", "tool_result", "reason"].includes(kind)) {
    handlers.onStep?.({
      kind,
      step: (event.data.step as number) ?? 0,
      tool: (event.data.tool as string) ?? null,
      content: event.data.content,
    });
  }

  // 流式 token 事件
  if (kind === "token" && typeof event.data.content === "string") {
    handlers.onToken?.(event.data.content);
  }

  // 执行进度事件
  if (kind === "progress" && event.data.content) {
    const p = event.data.content as Record<string, number>;
    handlers.onProgress?.(p.percent ?? 0, p.step ?? 0, p.max_steps ?? 0);
  }

  const error = event.data.error;
  if (typeof error === "string") {
    handlers.onError?.(error);
  }

  const runId = event.data.run_id;
  if (event.eventName === "done" && typeof runId === "string" && runId) {
    const usage: TokenUsage | undefined =
      typeof event.data.prompt_tokens === "number"
        ? {
            promptTokens: event.data.prompt_tokens as number,
            completionTokens: (event.data.completion_tokens as number) ?? 0,
          }
        : undefined;
    handlers.onDone?.(runId, usage);
    return runId;
  }

  return null;
}

/** 流空闲超时（ms）：超过此时间未收到任何数据则判定连接已死 */
const STREAM_IDLE_TIMEOUT = 120_000;

export async function readAgentRunStream(
  resp: Response,
  handlers: AgentRunStreamHandlers = {},
): Promise<string> {
  if (!resp.ok || !resp.body) {
    const errText = resp.ok ? "" : await resp.text().catch(() => "");
    throw new Error(`SSE ${resp.status}${errText ? `: ${errText.slice(0, 200)}` : ""}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let gotDone = false;
  let runId = "";

  /** 带超时的 read：服务器静默挂起时不会永远等待 */
  function readWithTimeout(): Promise<ReadableStreamReadResult<Uint8Array>> {
    return Promise.race([
      reader.read(),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("STREAM_IDLE_TIMEOUT")), STREAM_IDLE_TIMEOUT),
      ),
    ]);
  }

  try {
    while (true) {
      const { done, value } = await readWithTimeout();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const eventBlock of events) {
        const event = parseSseEvent(eventBlock);
        if (!event) continue;

        const rid = applySseEvent(event, handlers);
        if (rid) {
          gotDone = true;
          runId = rid;
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.message === "STREAM_IDLE_TIMEOUT") {
      handlers.onError?.("服务器响应超时，连接可能已中断");
      reader.cancel().catch(() => {});
      return runId || "timeout";
    }
    throw err;
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    const event = parseSseEvent(buffer);
    if (event) {
      const rid = applySseEvent(event, handlers);
      if (rid) {
        gotDone = true;
        runId = rid;
      }
    }
  }

  // 容错：流正常结束但未收到 done 事件（网络中断/服务器重启）
  if (!gotDone) {
    handlers.onError?.("连接已中断，请重试");
    return runId || "interrupted";
  }

  return runId;
}
