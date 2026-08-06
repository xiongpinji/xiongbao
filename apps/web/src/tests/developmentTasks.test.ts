import {
  createDevelopmentTaskConfirmation,
  getDevelopmentTaskActions,
} from "../api/developmentTasks";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

describe("development task controls", () => {
  it("shows only legal actions for each task status", () => {
    assert(
      getDevelopmentTaskActions("running").join(",") === "cancel",
      "Running tasks should only be cancellable",
    );
    assert(
      getDevelopmentTaskActions("awaiting_review").join(",") === "approve,reject",
      "Awaiting tasks should support approve and reject",
    );
    assert(
      getDevelopmentTaskActions("approved").join(",") === "apply,reject",
      "Approved tasks should support apply and reject",
    );
    assert(
      getDevelopmentTaskActions("conflict").join(",") === "reject",
      "Conflict tasks should only support cleanup by rejection",
    );
    assert(getDevelopmentTaskActions("applied").length === 0, "Applied tasks are terminal");
  });

  it("uses the exact task id as the mutation confirmation", () => {
    const body = createDevelopmentTaskConfirmation("dev-task-123");
    assert(body.confirm_task_id === "dev-task-123", "Confirmation must preserve task id");
  });
});
