import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const testsDir = path.join(projectRoot, "src", "tests");
const runner = path.join(projectRoot, "scripts", "run-tests.mjs");
const testFiles = readdirSync(testsDir)
  .filter((name) => /\.test\.tsx?$/.test(name))
  .sort();

if (testFiles.length === 0) {
  process.stderr.write("No Web unit test files found\n");
  process.exit(1);
}

for (const testFile of testFiles) {
  const result = spawnSync(process.execPath, [runner, testFile], {
    cwd: projectRoot,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
