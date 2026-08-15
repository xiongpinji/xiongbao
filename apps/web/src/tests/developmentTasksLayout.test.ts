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

function readDevelopmentTasksPageSource(): string {
  const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
  const process = runtime.process;
  assert(process, "DevelopmentTasksPage source contract requires the Node test runner");
  return process
    .getBuiltinModule("fs")
    .readFileSync(`${process.cwd()}/src/pages/DevelopmentTasksPage.tsx`, "utf8");
}

describe("DevelopmentTasksPage narrow detail layout", () => {
  it("keeps metadata cards readable beside the context panel", () => {
    const source = readDevelopmentTasksPageSource();

    assert(
      source.includes('className="grid grid-cols-2 gap-3 text-xs"'),
      "development task metadata must use two readable columns",
    );
    assert(
      !source.includes("xl:grid-cols-4"),
      "viewport breakpoints must not force four columns inside the narrow detail pane",
    );
  });

  it("offers the reviewed patch as an explicit download", () => {
    const source = readDevelopmentTasksPageSource();

    assert(source.includes("下载 Patch"), "reviewed patches need a download action");
    assert(source.includes("new Blob"), "patch download must contain the actual patch bytes");
    assert(source.includes(".patch`"), "patch download must use an openable patch filename");
  });
});
