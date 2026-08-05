import { build } from "esbuild";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const { argv, execPath, exit } = process;
const rawArg = argv[2] ?? "goalBoard.test.tsx";
const normalizedArg = rawArg.replace(/^--\s*/, "").trim() || "goalBoard.test.tsx";
const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const sourceEntry = normalizedArg.includes(path.sep) || normalizedArg.includes("/")
  ? path.resolve(projectRoot, normalizedArg)
  : path.resolve(projectRoot, "src/tests", normalizedArg);
const tmpRoot = path.resolve(projectRoot, ".tmp-tests");
const outDir = path.resolve(tmpRoot, path.basename(normalizedArg, path.extname(normalizedArg)));
const runnerSource = path.resolve(outDir, "runner-entry.mjs");
const runnerOutput = path.resolve(outDir, "runner.mjs");
const relativeTestEnv = path.relative(outDir, path.resolve(projectRoot, "src/tests/test-env.ts")).split(path.sep).join("/");
const relativeTestFile = path.relative(outDir, sourceEntry).split(path.sep).join("/");

rmSync(outDir, { force: true, recursive: true });
mkdirSync(outDir, { recursive: true });
writeFileSync(
  runnerSource,
  `import { waitForTests } from "./${relativeTestEnv}";\nimport "./${relativeTestFile}";\nawait waitForTests();\n`,
  "utf8",
);

try {
  await build({
    absWorkingDir: projectRoot,
    bundle: true,
    entryPoints: [runnerSource],
    outfile: runnerOutput,
    format: "esm",
    // CJS 依赖（如 axios→form-data）在 ESM bundle 中需要 require 垫片
    banner: {
      js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);",
    },
    jsx: "automatic",
    loader: {
      ".ts": "ts",
      ".tsx": "tsx",
    },
    platform: "node",
    target: "node18",
  });

  const result = spawnSync(execPath, [runnerOutput], {
    cwd: projectRoot,
    stdio: "inherit",
  });

  if (result.status !== 0) {
    exit(result.status ?? 1);
  }
} finally {
  rmSync(outDir, { force: true, recursive: true });
  try {
    rmSync(tmpRoot, { force: true, recursive: false });
  } catch {
    // Ignore non-empty directory cleanup on parallel or failed runs.
  }
}
