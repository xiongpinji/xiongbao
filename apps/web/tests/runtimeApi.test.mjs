import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { URL } from "node:url";
import { api } from "../src/api/client.ts";
import {
  getRunDetail,
  normalizeRunDetail,
  normalizeRunTimeline,
} from "../src/api/runtime.ts";

test("normalizeRunDetail merges workflow timeline, task timeline, and task events", () => {
  const detail = normalizeRunDetail({
    run_id: "run-1",
    tenant_id: "tenant-1",
    task: {
      task_id: "task-1",
      run_id: "run-1",
      kind: "creative.produce",
      status: "succeeded",
      result: {
        timeline: [
          { ts: "2026-06-30T10:01:00Z", step_id: "task", kind: "task-fallback", detail: "from-result" },
          { step_id: "task-no-ts", kind: "result-without-ts", detail: "stable-tail" },
        ],
      },
      events: [
        { ts: "2026-06-30T10:02:00Z", step_id: "event", kind: "agent.event", content: { ok: true } },
      ],
    },
    workflow: {
      run_id: "run-1",
      spec_name: "creative-flow",
      tenant_id: "tenant-1",
      status: "completed",
      steps: [{ id: "plan", name: "Plan", status: "succeeded" }],
      timeline: [{ ts: "2026-06-30T10:00:00Z", step_id: "plan", kind: "started", detail: { role: "planner" } }],
    },
    evidence: undefined,
    artifacts: undefined,
    validation: undefined,
    delivery: { status: "ready", summary: "完成交付" },
    related_tasks: undefined,
  });

  assert.equal(detail.run_id, "run-1");
  assert.deepEqual(detail.timeline, [
    {
      ts: "2026-06-30T10:00:00Z",
      step_id: "plan",
      kind: "started",
      detail: { role: "planner" },
      source: "workflow",
    },
    {
      ts: "2026-06-30T10:01:00Z",
      step_id: "task",
      kind: "task-fallback",
      detail: "from-result",
      source: "task",
    },
    {
      ts: "2026-06-30T10:02:00Z",
      step_id: "event",
      kind: "agent.event",
      detail: { ok: true },
      source: "task",
    },
    {
      ts: "",
      step_id: "task-no-ts",
      kind: "result-without-ts",
      detail: "stable-tail",
      source: "task",
    },
  ]);
  assert.deepEqual(detail.delivery, { status: "ready", summary: "完成交付" });
  assert.deepEqual(detail.evidence, []);
  assert.deepEqual(detail.artifacts, []);
  assert.deepEqual(detail.related_tasks, []);
  assert.equal(detail.workflow?.timeline.length, 1);
});

test("normalizeRunTimeline returns task timeline and events when workflow data is absent", () => {
  const timeline = normalizeRunTimeline({
    run_id: "run-2",
    tenant_id: "tenant-1",
    task: {
      task_id: "task-2",
      run_id: "run-2",
      kind: "agent.run",
      status: "succeeded",
      result: {
        timeline: [{ ts: "2026-06-30T11:00:00Z", step_id: "answer", kind: "completed", detail: { final_answer: "ok" } }],
      },
      events: [{ step_id: "fallback-event", kind: "event", content: "tail" }],
    },
    workflow: null,
    evidence: [],
    artifacts: [],
    validation: {},
    delivery: {},
    related_tasks: [],
  });

  assert.deepEqual(timeline, [
    {
      ts: "2026-06-30T11:00:00Z",
      step_id: "answer",
      kind: "completed",
      detail: { final_answer: "ok" },
      source: "task",
    },
    {
      ts: "",
      step_id: "fallback-event",
      kind: "event",
      detail: "tail",
      source: "task",
    },
  ]);
});

test("normalizeRunDetail keeps task.input from the backend contract", () => {
  const detail = normalizeRunDetail({
    run_id: "run-input",
    tenant_id: "tenant-1",
    task: {
      task_id: "task-input",
      run_id: "run-input",
      kind: "agent.run",
      status: "running",
      input: { goal: "写一个运行摘要", role: "planner" },
      result: { final_answer: "done" },
    },
    workflow: null,
    evidence: [],
    artifacts: [],
    validation: { checks: 1 },
    delivery: { status: "pending" },
    related_tasks: [],
  });

  assert.deepEqual(detail.task?.input, { goal: "写一个运行摘要", role: "planner" });
  assert.equal("input_payload" in (detail.task ?? {}), false);
  assert.deepEqual(detail.task?.result, { final_answer: "done" });
  assert.deepEqual(detail.validation, { checks: 1 });
  assert.deepEqual(detail.delivery, { status: "pending" });
});

test("getRunDetail preserves task.input from backend payloads", async () => {
  const originalGet = api.get;
  api.get = async () => ({
    data: {
      run_id: "run-input-api",
      tenant_id: "tenant-1",
      task: {
        task_id: "task-input-api",
        run_id: "run-input-api",
        kind: "agent.run",
        status: "succeeded",
        input: { goal: "保留真实合同字段" },
        result: { final_answer: "ok" },
      },
      workflow: null,
      evidence: [],
      artifacts: [],
      validation: {},
      delivery: {},
      related_tasks: [],
    },
  });

  try {
    const detail = await getRunDetail("run-input-api");
    assert.deepEqual(detail.task?.input, { goal: "保留真实合同字段" });
    assert.equal("input_payload" in (detail.task ?? {}), false);
  } finally {
    api.get = originalGet;
  }
});

test("getRunDetail requests an encoded run path and returns normalized detail", async () => {
  const originalGet = api.get;
  const calls = [];
  api.get = async (url) => {
    calls.push(url);
    return {
      data: {
        run_id: "run id/with spaces",
        tenant_id: "tenant-1",
        task: null,
        workflow: null,
        evidence: [],
        artifacts: [],
        validation: {},
        delivery: { status: "pending" },
        related_tasks: [],
      },
    };
  };

  try {
    const detail = await getRunDetail("run id/with spaces");
    assert.deepEqual(calls, ["/runs/run%20id%2Fwith%20spaces"]);
    assert.equal(detail.run_id, "run id/with spaces");
    assert.deepEqual(detail.delivery, { status: "pending" });
    assert.deepEqual(detail.timeline, []);
  } finally {
    api.get = originalGet;
  }
});

test("artifact panel avoids clickable links for empty and placeholder URIs", async () => {
  const panelSource = await readFile(new URL("../src/components/runs/RunArtifactsPanel.tsx", import.meta.url), "utf8");

  assert.match(panelSource, /function isOpenableArtifactUri\(uri: string\): boolean/);
  assert.match(panelSource, /const canOpen = isOpenableArtifactUri\(artifact\.uri\);/);
  assert.match(panelSource, /\{canOpen \? \(/);
  assert.match(panelSource, /href=\{artifact\.uri\}/);
  assert.match(panelSource, /占位产物/);
  assert.match(panelSource, /暂无链接/);
});

test("run route and page composition expose the runtime console panels", async () => {
  const [appSource, pageSource, consoleSource] = await Promise.all([
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/RunPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/runs/RunConsole.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(appSource, /path="\/runs\/:runId"/);
  assert.match(pageSource, /RunConsole/);
  assert.match(consoleSource, /RunTimelinePanel/);
  assert.match(consoleSource, /RunEvidencePanel/);
  assert.match(consoleSource, /RunArtifactsPanel/);
});
