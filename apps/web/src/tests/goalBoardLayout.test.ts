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

describe("goal board layout", () => {
  it("keeps task columns readable inside the three-pane workspace", () => {
    const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
    const process = runtime.process;
    assert(process, "source contract requires the Node test runner");
    const source = process
      .getBuiltinModule("fs")
      .readFileSync(`${process.cwd()}/src/components/spine/GoalBoard.tsx`, "utf8");

    assert(
      source.includes("repeat(auto-fit,minmax(240px,1fr))"),
      "Task columns must respond to their container and keep a readable minimum width",
    );
    assert(
      !source.includes("xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)]"),
      "Release content must not squeeze task columns beside the context panel",
    );
  });
});
