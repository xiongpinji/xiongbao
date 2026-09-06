type FileSystem = {
  readFileSync(path: string, encoding: "utf8"): string;
};

type NodeProcess = {
  cwd(): string;
  getBuiltinModule(name: "fs"): FileSystem;
};

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function readChatPageSource(): string {
  const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
  const process = runtime.process;
  assert(process, "ChatPage source contract requires the Node test runner");
  return process
    .getBuiltinModule("fs")
    .readFileSync(`${process.cwd()}/src/pages/ChatPage.tsx`, "utf8");
}

describe("ChatPage agent-mode request contract", () => {
  it("defaults to agent mode (tool_mode auto), pure chat is opt-out", () => {
    const source = readChatPageSource();

    assert(
      source.includes('useState<"auto" | "none">("auto")'),
      "ChatPage must default to toolMode auto (agent interaction, not chatbot)",
    );
  });

  it("threads the mode toggle into the SSE request", () => {
    const source = readChatPageSource();

    assert(
      source.includes(
        "tool_mode: toolMode })",
      ),
      "ChatPage SSE request must send the active tool_mode (auto by default)",
    );
  });

  it("threads the mode toggle into the direct fallback", () => {
    const source = readChatPageSource();

    assert(
      source.includes("runAgent({ goal: nextGoal, tool_mode: toolMode })"),
      "ChatPage direct fallback must send the active tool_mode",
    );
  });

  it("gates the no-tools hint to pure-chat mode only", () => {
    const source = readChatPageSource();

    assert(
      source.includes(
        'toolMode === "none" && hasExecutionIntent(nextGoal)',
      ),
      "noToolsHint must only appear in pure-chat mode; agent mode executes tools",
    );
  });

  it("renders a visible mode toggle with agent semantics", () => {
    const source = readChatPageSource();

    assert(
      source.includes('"智能体"') && source.includes('"纯对话"'),
      "ChatPage must expose an 智能体/纯对话 toggle",
    );
  });
});
