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

describe("goal board empty state", () => {
  it("does not request a hard-coded goal when none was selected", () => {
    const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
    const process = runtime.process;
    assert(process, "source contract requires the Node test runner");
    const source = process
      .getBuiltinModule("fs")
      .readFileSync(`${process.cwd()}/src/pages/GoalBoardPage.tsx`, "utf8");

    assert(!source.includes("DEFAULT_GOAL_ID"), "The page must not assume a seeded goal exists");
    assert(
      source.includes("enabled: goalId.length > 0"),
      "The board query must stay disabled until a goal is selected",
    );
    assert(source.includes("尚未选择 Goal"), "The page must render an actionable empty state");
  });
});
