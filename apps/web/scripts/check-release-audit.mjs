import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("..", import.meta.url));
const expiry = "2026-09-30";
const allowedPackages = new Set(["react-router", "react-router-dom"]);
const allowedAdvisory = "https://github.com/advisories/GHSA-qwww-vcr4-c8h2";

function fail(message) {
  process.stderr.write(`Web release audit failed: ${message}\n`);
  process.exit(1);
}

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(target);
    return /\.(ts|tsx|js|jsx)$/.test(entry.name) ? [target] : [];
  });
}

const npmExecPath = process.env.npm_execpath;
const command = npmExecPath ? process.execPath : process.platform === "win32" ? "npm.cmd" : "npm";
const args = npmExecPath
  ? [npmExecPath, "audit", "--omit=dev", "--json"]
  : ["audit", "--omit=dev", "--json"];
const audit = spawnSync(command, args, { cwd: root, encoding: "utf8" });
if (!audit.stdout.trim()) fail(`npm audit produced no JSON (${audit.stderr.trim()})`);

let report;
try {
  report = JSON.parse(audit.stdout);
} catch (error) {
  fail(`npm audit JSON is invalid: ${error}`);
}

const vulnerabilities = report.vulnerabilities ?? {};
const names = Object.keys(vulnerabilities);
if (names.length === 0) {
  process.stdout.write("Web production dependency audit passed with zero vulnerabilities.\n");
  process.exit(0);
}
if (new Date().toISOString().slice(0, 10) > expiry) {
  fail(`the React Router RSC exception expired on ${expiry}`);
}
if (names.some((name) => !allowedPackages.has(name))) {
  fail(`unexpected vulnerable production package(s): ${names.join(", ")}`);
}

const advisoryUrls = new Set();
for (const detail of Object.values(vulnerabilities)) {
  for (const via of detail.via ?? []) {
    if (typeof via === "object" && via.url) advisoryUrls.add(via.url);
  }
}
if (advisoryUrls.size !== 1 || !advisoryUrls.has(allowedAdvisory)) {
  fail(`unexpected advisory set: ${[...advisoryUrls].join(", ")}`);
}

const forbiddenRouterSurface = /(?:react-router(?:-dom)?\/(?:server|rsc)|createStaticRouter|StaticRouterProvider|RSCHydratedRouter|RSCStaticRouter)/;
const reachable = sourceFiles(path.join(root, "src")).filter((file) =>
  forbiddenRouterSurface.test(readFileSync(file, "utf8")),
);
if (reachable.length > 0) {
  fail(`RSC/SSR router surface became reachable: ${reachable.map((file) => path.relative(root, file)).join(", ")}`);
}

const dockerfile = readFileSync(path.join(root, "Dockerfile"), "utf8");
const activeDockerfile = dockerfile
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter((line) => line && !line.startsWith("#"))
  .join("\n");
if (!/^FROM nginx:/m.test(activeDockerfile) || !/^COPY dist /m.test(activeDockerfile)) {
  fail("production Web image is no longer a static Nginx dist image");
}
if (/^FROM node|npm (?:ci|install)/m.test(activeDockerfile)) {
  fail("production Web image unexpectedly contains a Node/npm runtime stage");
}

const packageJson = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8"));
if (packageJson.dependencies?.["react-router-dom"] !== "^7.18.2") {
  fail("React Router version changed without re-auditing the exception");
}

const counts = report.metadata?.vulnerabilities ?? {};
process.stdout.write(
  `Web production dependency audit accepted one unreachable RSC advisory ` +
  `(owner=web-platform, expiry=${expiry}, high=${counts.high ?? 0}); ` +
  `the deployed image contains static dist only.\n`,
);
