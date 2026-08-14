/**
 * P1 回归合同：模型选择器必须动态化（后端可用性判定），
 * 不可用模型禁用并给原因，切换失败不得静默。
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

describe("ChatPage dynamic model options contract (P1)", () => {
  it("dropdown renders backend-driven options with availability, not bare presets", () => {
    const source = readSource("src/pages/ChatPage.tsx");
    assert(source.includes("dropdownModels"), "dropdown must render dropdownModels");
    assert(
      !/modelOpen && \([\s\S]{0,300}MODEL_PRESETS\.map/.test(source),
      "dropdown must not map directly over hardcoded MODEL_PRESETS",
    );
    assert(
      source.includes('disabled={!m.available}'),
      "unavailable models must be disabled",
    );
    assert(
      source.includes("未配置"),
      "unavailable models must carry a visible reason marker",
    );
  });

  it("model switch failure rolls back and surfaces the backend reason", () => {
    const source = readSource("src/pages/ChatPage.tsx");
    assert(source.includes("setModel(prev)"), "switch failure must roll back selection");
    assert(
      source.includes("response?.data?.detail"),
      "switch failure must surface backend 422 detail",
    );
    assert(
      !/catch \{\s*\/\* silent \*\/\s*\}/.test(source),
      "silent catch on model switch is forbidden",
    );
  });

  it("settings page warns when disk override is active", () => {
    const source = readSource("src/components/settings/ModelSettings.tsx");
    assert(
      source.includes("override_active"),
      "ModelSettings must surface override_active",
    );
    assert(
      source.includes("运行时覆盖生效中"),
      "override warning banner must be rendered",
    );
  });

  it("LLMConfig type carries override visibility and model options", () => {
    const source = readSource("src/api/index.ts");
    assert(source.includes("override_active"), "LLMConfig must expose override_active");
    assert(source.includes("models?:"), "LLMConfig must expose models options");
  });
});
