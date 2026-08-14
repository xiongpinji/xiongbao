import assert from "node:assert/strict";
import { test } from "node:test";
import { XAgentClient } from "../dist/index.js";

test("constructor applies baseUrl and bearer token", () => {
  const client = new XAgentClient({ baseUrl: "http://example.test:9000", token: "tk-1" });
  const http = client.http; // runtime access for contract verification
  assert.equal(http.defaults.baseURL, "http://example.test:9000/api/v1");
  assert.equal(http.defaults.headers.common.Authorization, "Bearer tk-1");
});

test("constructor defaults to localhost:8000 without token", () => {
  const client = new XAgentClient();
  const http = client.http;
  assert.equal(http.defaults.baseURL, "http://localhost:8000/api/v1");
  assert.equal(http.defaults.headers.common.Authorization, undefined);
});

test("setToken updates the authorization header", () => {
  const client = new XAgentClient();
  client.setToken("tk-2");
  assert.equal(client.http.defaults.headers.common.Authorization, "Bearer tk-2");
});

test("streamRun parses SSE data lines and skips malformed payloads", async () => {
  const sse = [
    'data: {"event":"step","data":{"step":1}}',
    "",
    "data: {not-json}",
    'data: {"event":"done","data":{"answer":"ok"}}',
    "",
  ].join("\n");

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "http://localhost:8000/api/v1/stream/agents/run");
    assert.equal(init.method, "POST");
    const body = JSON.parse(init.body);
    assert.equal(body.goal, "hello");
    return new Response(sse, { status: 200 });
  };

  try {
    const client = new XAgentClient();
    const events = [];
    for await (const evt of client.streamRun({ goal: "hello" })) {
      events.push(evt);
    }
    assert.equal(events.length, 2);
    assert.deepEqual(events[0], { event: "step", data: { step: 1 } });
    assert.deepEqual(events[1], { event: "done", data: { answer: "ok" } });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamRun throws on non-OK response", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("boom", { status: 500 });
  try {
    const client = new XAgentClient();
    await assert.rejects(async () => {
      for await (const _ of client.streamRun({ goal: "x" })) { /* drain */ }
    }, /Stream failed: 500/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
