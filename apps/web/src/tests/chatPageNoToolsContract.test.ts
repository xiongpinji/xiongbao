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

describe("ChatPage no-tools request contract", () => {
  it("uses tool_mode none for the SSE request", () => {
    const source = readChatPageSource();

    assert(
      source.includes(
        'JSON.stringify({ goal: nextGoal, conversation_id: conversationId || undefined, tool_mode: "none" })',
      ),
      "ChatPage SSE request must explicitly send tool_mode none",
    );
  });

  it("uses tool_mode none for the direct fallback", () => {
    const source = readChatPageSource();

    assert(
      source.includes('runAgent({ goal: nextGoal, tool_mode: "none" })'),
      "ChatPage direct fallback must explicitly send tool_mode none",
    );
  });
});
