type FileSystem = {
  readFileSync(path: string, encoding: "utf8"): string;
};

type NodeProcess = {
  cwd(): string;
  getBuiltinModule(name: "fs"): FileSystem;
};

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

describe("general settings security", () => {
  it("does not render the persisted bearer token into the input", () => {
    const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
    const process = runtime.process;
    assert(process, "source contract requires the Node test runner");
    const source = process
      .getBuiltinModule("fs")
      .readFileSync(`${process.cwd()}/src/components/settings/GeneralSettings.tsx`, "utf8");

    assert(source.includes('type="password"'), "Bearer token input must be masked");
    assert(
      !source.includes("useState(getToken()"),
      "The persisted bearer token must not be used as the input's initial value",
    );
    assert(
      source.includes('setTok("");') && source.includes("setToken(token.trim());"),
      "The input must be cleared immediately after a bearer token is saved",
    );
  });
});
