import {
  canResumeCheckpoint,
  checkpointStatusLabel,
} from "../api/checkpoints.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

describe("checkpoint timeline actions", () => {
  it("blocks duplicate resume while a child run is pending or running", () => {
    assert(!canResumeCheckpoint("pending"), "Pending checkpoint must not resume again");
    assert(!canResumeCheckpoint("running"), "Running checkpoint must not resume again");
    assert(
      !canResumeCheckpoint("available", "child-run"),
      "Checkpoint with an existing child run must not resume again",
    );
    assert(canResumeCheckpoint("available"), "Available checkpoint should be resumable");
    assert(canResumeCheckpoint("failed"), "Failed resume should remain recoverable");
  });

  it("shows explicit recovery and rollback states", () => {
    assert(checkpointStatusLabel("completed") === "恢复完成", "Resume state drifted");
    assert(checkpointStatusLabel("rolled_back") === "已回滚", "Rollback state drifted");
    assert(checkpointStatusLabel("rollback_failed") === "回滚失败", "Failure state drifted");
  });
});
