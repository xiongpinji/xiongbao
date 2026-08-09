import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { URL } from "node:url";
import { readAgentRunStream } from "../src/api/chatStream.ts";

function sseResponse(body) {
  return new globalThis.Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

test("readAgentRunStream resolves when a done event carries a run id", async () => {
  const finalAnswers = [];
  const doneRunIds = [];

  const runId = await readAgentRunStream(
    sseResponse(
      [
        'event: final\ndata: {"final_answer":"完成"}',
        'event: done\ndata: {"run_id":"run-1","steps":2}',
        "",
      ].join("\n\n"),
    ),
    {
      onFinalAnswer: (answer) => finalAnswers.push(answer),
      onDone: (nextRunId) => doneRunIds.push(nextRunId),
    },
  );

  assert.equal(runId, "run-1");
  assert.deepEqual(finalAnswers, ["完成"]);
  assert.deepEqual(doneRunIds, ["run-1"]);
});

test("readAgentRunStream rejects when the stream ends before a done event", async () => {
  await assert.rejects(
    () =>
      readAgentRunStream(
        sseResponse('event: final\ndata: {"final_answer":"缺少 done"}\n\n'),
      ),
    /SSE stream ended before done event/,
  );
});

test("ChatPage keeps the run detail link visible for done-only SSE runs", async () => {
  const source = await readFile(new URL("../src/pages/ChatPage.tsx", import.meta.url), "utf8");

  assert.match(source, /\(loading \|\| streamText \|\| run \|\| error \|\| runId\) &&/);
  assert.match(source, /\{runId && \(/);
});

test("ChatPage explicitly requests the no-tools chat route", async () => {
  const source = await readFile(new URL("../src/pages/ChatPage.tsx", import.meta.url), "utf8");

  assert.match(
    source,
    /JSON\.stringify\(\{ goal: nextGoal, conversation_id: conversationId \|\| undefined, tool_mode: "none" \}\)/,
  );
  assert.match(source, /runAgent\(\{ goal: nextGoal, tool_mode: "none" \}\)/);
});
