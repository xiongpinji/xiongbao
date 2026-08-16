import { createHash, randomBytes } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type APIRequestContext } from "@playwright/test";
import AdmZip from "adm-zip";

const API_BASE = process.env.E2E_API_URL ?? "http://127.0.0.1:18000";
const evidenceDir = process.env.E2E_EVIDENCE_DIR
  ? resolve(process.env.E2E_EVIDENCE_DIR)
  : "";

test("短剧本地产出可重开并下载校验包", async ({ request }) => {
  test.setTimeout(180_000);
  if (!evidenceDir) {
    throw new Error("E2E_EVIDENCE_DIR is required");
  }
  await mkdir(evidenceDir, { recursive: true });
  const nonce = `${Date.now()}-${randomBytes(4).toString("hex")}`;
  const token = await register(
    request,
    `short-drama-${nonce}`,
    `Short-${randomBytes(24).toString("base64url")}!`,
    `short-drama-tenant-${nonce}`,
  );
  const headers = { Authorization: `Bearer ${token}` };

  const produced = await request.post(`${API_BASE}/api/v1/creative-studio/produce`, {
    headers,
    data: { brief: "本地离线交付验收", with_video: false },
    timeout: 180_000,
  });
  expect(produced.status()).toBe(200);
  const doc = await produced.json();
  expect(doc.status).toBe("produced");
  expect(doc.timeline.id).toBe(doc.timeline_id);
  expect(doc.timeline.clips.length).toBeGreaterThan(0);

  const reopened = await request.get(
    `${API_BASE}/api/v1/creative-studio/productions/${doc.storyboard_id}`,
    { headers },
  );
  expect(reopened.status()).toBe(200);
  expect((await reopened.json()).timeline).toEqual(doc.timeline);

  const bundle = await request.get(
    `${API_BASE}/api/v1/creative-studio/productions/${doc.storyboard_id}/bundle`,
    { headers },
  );
  expect(bundle.status()).toBe(200);
  expect(bundle.headers()["content-type"]).toContain("application/zip");
  const bytes = await bundle.body();
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  await writeFile(resolve(evidenceDir, "short-drama.zip"), bytes);
  await writeFile(
    resolve(evidenceDir, "short-drama.zip.sha256"),
    `${createHash("sha256").update(bytes).digest("hex")}  short-drama.zip\n`,
  );

  const archive = new AdmZip(bytes);
  const entries = new Map(
    archive.getEntries().map((entry) => [entry.entryName, entry.getData()]),
  );
  expect([...entries.keys()].every((name) => !name.startsWith("/") && !name.includes(".."))).toBeTruthy();
  for (const required of ["manifest.json", "production.json", "timeline.json"]) {
    expect(entries.has(required)).toBeTruthy();
  }
  const manifest = JSON.parse(entries.get("manifest.json")!.toString("utf8"));
  expect(manifest.production_status).toBe("produced");
  expect(manifest.provider_classification).toBe("fixture_local");
  expect(manifest.external_provider_acceptance).toBe("not_authorized");
  for (const file of manifest.files) {
    const payload = entries.get(file.path);
    expect(payload, `missing ZIP member ${file.path}`).toBeTruthy();
    expect(payload!.length).toBe(file.size_bytes);
    expect(createHash("sha256").update(payload!).digest("hex")).toBe(file.sha256);
  }
  expect(JSON.parse(entries.get("production.json")!.toString("utf8")).timeline).toEqual(doc.timeline);
  expect(JSON.parse(entries.get("timeline.json")!.toString("utf8"))).toEqual(doc.timeline);
  await writeFile(
    resolve(evidenceDir, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
  );
});

async function register(
  request: APIRequestContext,
  username: string,
  password: string,
  tenantId: string,
): Promise<string> {
  const response = await request.post(`${API_BASE}/api/v1/auth/register`, {
    data: { username, password, tenant_id: tenantId },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.tenant_id).toBe(tenantId);
  return body.access_token;
}
