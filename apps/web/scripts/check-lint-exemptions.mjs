import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const baselinePath = path.join(projectRoot, ".eslint-release-exemptions.json");
const groupRules = {
  react_compiler_migration: new Set([
    "react-hooks/immutability",
    "react-hooks/purity",
    "react-hooks/refs",
    "react-hooks/set-state-in-effect",
  ]),
  react_effect_dependencies: new Set(["react-hooks/exhaustive-deps"]),
};

export function digest(findings) {
  const stable = [...findings].sort((left, right) =>
    JSON.stringify(left).localeCompare(JSON.stringify(right)),
  );
  return createHash("sha256").update(JSON.stringify(stable)).digest("hex");
}

export function groupWarnings(results) {
  const groups = Object.fromEntries(Object.keys(groupRules).map((name) => [name, []]));
  for (const result of results) {
    const relativePath = path.relative(projectRoot, result.filePath).replaceAll("\\", "/");
    for (const message of result.messages) {
      if (message.severity === 2) {
        throw new Error(
          `ESLint error is never exempted: ${relativePath}:${message.line} ${message.ruleId}`,
        );
      }
      if (message.severity !== 1) continue;
      const group = Object.entries(groupRules).find(([, rules]) => rules.has(message.ruleId))?.[0];
      if (!group) {
        throw new Error(
          `Unclassified ESLint warning: ${relativePath}:${message.line} ${message.ruleId}`,
        );
      }
      groups[group].push({
        path: relativePath,
        rule: message.ruleId,
        line: message.line,
        column: message.column,
      });
    }
  }
  return groups;
}

function validate(current, baseline) {
  const errors = [];
  const required = ["count", "sha256", "owner", "reason", "expires_on", "scope"].sort();
  if (JSON.stringify(Object.keys(current).sort()) !== JSON.stringify(Object.keys(baseline).sort())) {
    return ["ESLint exemption groups differ from current scan groups"];
  }
  const today = new Date().toISOString().slice(0, 10);
  for (const [name, actual] of Object.entries(current)) {
    const expected = baseline[name];
    if (
      !expected ||
      JSON.stringify(Object.keys(expected).sort()) !== JSON.stringify(required)
    ) {
      errors.push(`${name}: incomplete exemption metadata`);
      continue;
    }
    if (today > expected.expires_on) errors.push(`${name}: expired on ${expected.expires_on}`);
    for (const field of ["owner", "reason", "scope"]) {
      if (typeof expected[field] !== "string" || !expected[field].trim()) {
        errors.push(`${name}: ${field} must not be empty`);
      }
    }
    if (actual.count !== expected.count || actual.sha256 !== expected.sha256) {
      errors.push(
        `${name}: fingerprint mismatch, current ${actual.count} / ${actual.sha256}`,
      );
    }
  }
  return errors;
}

async function main() {
  const baseline = JSON.parse(await readFile(baselinePath, "utf8"));
  const eslint = new ESLint({ cwd: projectRoot });
  const groups = groupWarnings(await eslint.lintFiles(["."]));
  const current = Object.fromEntries(
    Object.entries(groups).map(([name, findings]) => [
      name,
      { count: findings.length, sha256: digest(findings) },
    ]),
  );
  const errors = validate(current, baseline);
  for (const [name, actual] of Object.entries(current)) {
    const metadata = baseline[name] ?? {};
    process.stdout.write(
      `${name}: ${actual.count} findings, sha256=${actual.sha256}, ` +
        `owner=${metadata.owner}, expires_on=${metadata.expires_on}\n`,
    );
  }
  if (errors.length) throw new Error(errors.join("\n"));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`Release lint exemption gate failed: ${error.message}\n`);
    process.exitCode = 1;
  });
}
