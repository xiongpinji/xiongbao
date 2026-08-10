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

function readShellContextPanelSource(): string {
  const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
  const process = runtime.process;
  assert(process, "ShellContextPanel source contract requires the Node test runner");
  return process
    .getBuiltinModule("fs")
    .readFileSync(`${process.cwd()}/src/components/layout/ShellContextPanel.tsx`, "utf8");
}

describe("ShellContextPanel preview contract", () => {
  it("starts without loading a dead local preview URL", () => {
    const source = readShellContextPanelSource();

    assert(
      !source.includes("localhost:5175"),
      "the preview panel must not auto-load a development-only localhost URL",
    );
    assert(
      source.includes('const [url, setUrl] = useState("")'),
      "the preview URL must start empty",
    );
    assert(
      source.includes('const [inputUrl, setInputUrl] = useState("")'),
      "the preview input must start empty",
    );
    assert(
      source.includes("输入 URL 以预览页面"),
      "the empty preview must explain how to start a preview",
    );
  });
});
