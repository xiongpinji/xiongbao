import { createJobConfirmation, getSchedulerJobActions } from "../api/scheduler";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

describe("durable scheduler controls", () => {
  it("shows pause or resume without hiding manual run and delete", () => {
    assert(
      getSchedulerJobActions(true).join(",") === "run,pause,delete",
      "Enabled jobs should run, pause or delete",
    );
    assert(
      getSchedulerJobActions(false).join(",") === "run,resume,delete",
      "Paused jobs should still support manual run, resume or delete",
    );
  });

  it("uses exact job id confirmation", () => {
    assert(createJobConfirmation("job-1").confirm_job_id === "job-1", "Job id drifted");
  });
});
