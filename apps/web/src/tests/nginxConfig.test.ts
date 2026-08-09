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

function readNginxConfig(): string {
  const runtime = globalThis as typeof globalThis & { process?: NodeProcess };
  const process = runtime.process;
  assert(process, "nginx config contract requires the Node test runner");
  return process.getBuiltinModule("fs").readFileSync(`${process.cwd()}/nginx.conf`, "utf8");
}

describe("nginx API upstream contract", () => {
  it("dynamically re-resolves every API upstream through Docker DNS", () => {
    const config = readNginxConfig();

    assert(
      /\bresolver\s+127\.0\.0\.11\b[^;]*\bvalid=\d+s\b[^;]*;/.test(config),
      "nginx must use Docker DNS with a bounded refresh interval",
    );
    assert(
      /\bset\s+\$api_upstream\s+http:\/\/api:8000\s*;/.test(config),
      "nginx must keep the api service name in a runtime-resolved variable",
    );
    assert(
      (config.match(/\bproxy_pass\s+\$api_upstream\s*;/g) ?? []).length === 2,
      "both HTTP API and WebSocket proxy locations must use the dynamic upstream",
    );
    assert(
      !/\bproxy_pass\s+http:\/\/api:8000\s*;/.test(config),
      "nginx must not resolve the api service only once during startup",
    );
  });

  it("proxies the exact API WebSocket path without a trailing-slash redirect", () => {
    const config = readNginxConfig();

    assert(
      /\blocation\s*=\s*\/ws\s*\{[\s\S]*?\bproxy_pass\s+\$api_upstream\s*;[\s\S]*?\}/.test(config),
      "nginx must proxy the API's exact /ws route",
    );
    assert(
      !/\blocation\s+\/ws\/\s*\{/.test(config),
      "nginx must not redirect /ws to the unsupported /ws/ route",
    );
  });
});
