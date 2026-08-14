/**
 * P1/P2 回归合同：工作流画布异步执行 + 纯对话执行意图提示。
 */

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

function readSource(rel: string): string {
  const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
  const process = runtime.process;
  assert(process, "source contract requires the Node test runner");
  return process
    .getBuiltinModule("fs")
    .readFileSync(`${process.cwd()}/${rel}`, "utf8");
}

describe("P1 workflow canvas async execution contract", () => {
  it("canvas execute submits with run_async and navigates immediately", () => {
    const source = readSource("src/pages/WorkflowsPage.tsx");
    assert(
      source.includes('runWorkflow({ name, steps, run_async: true })'),
      "canvas run must submit with run_async: true",
    );
    assert(
      source.indexOf("run_async: true") < source.indexOf('navigate(`/runs/'),
      "must navigate to run detail right after async submit",
    );
  });

  it("runWorkflow API surface exposes run_async", () => {
    const source = readSource("src/api/index.ts");
    assert(source.includes("run_async?: boolean"), "runWorkflow must accept run_async");
  });
});

describe("P2 no-tools execution intent hint contract", () => {
  it("ChatPage detects execution intent and marks noToolsHint", () => {
    const source = readSource("src/pages/ChatPage.tsx");
    assert(source.includes("EXECUTION_INTENT_RE"), "intent regex must exist");
    assert(source.includes("hasExecutionIntent(nextGoal)"), "intent must be evaluated per goal");
    assert(source.includes("noToolsHint"), "messages must carry noToolsHint flag");
  });

  it("hint banner warns that no tool actually ran", () => {
    const source = readSource("src/pages/ChatPage.tsx");
    assert(
      source.includes("未调用任何工具"),
      "hint must explicitly state no tools were called",
    );
    assert(
      source.includes("msg.noToolsHint"),
      "hint banner must render from the message flag",
    );
  });
});
