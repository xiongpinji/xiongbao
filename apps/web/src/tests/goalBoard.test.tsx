import { render, screen } from "./testing-library-react";
import GoalBoard from "../components/spine/GoalBoard";

describe("GoalBoard", () => {
  it("renders goal board columns and next action", () => {
    render(
      <GoalBoard
        snapshot={{
          goal: { title: "Phase 1", phase: "execution", status: "active" },
          columns: {
            ready: [{ task_id: "t-1", title: "Build taskboard" }],
            blocked: [],
            review: [],
          },
          next_action: { kind: "execute", task_id: "t-1" },
        }}
      />,
    );

    expect(screen.getByText("Phase 1")).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("Build taskboard")).toBeInTheDocument();
    expect(screen.getByText(/execute/i)).toBeInTheDocument();
  });

  it("renders release pane separately from core task columns", () => {
    render(
      <GoalBoard
        snapshot={{
          goal: { title: "Phase 1", phase: "release", status: "active" },
          columns: {
            ready: [{ task_id: "t-1", title: "Build taskboard" }],
            release_ready: [{ task_id: "t-2", title: "Cut candidate" }],
            deploying: [{ task_id: "t-3", title: "Deploy candidate" }],
            recovery: [{ task_id: "t-4", title: "Rollback" }],
          },
          next_action: { kind: "recovery", task_id: "t-4", reason: "verify failed" },
        }}
      />,
    );

    expect(screen.getByText("Release / Recovery")).toBeInTheDocument();
    expect(screen.getByText("release_ready")).toBeInTheDocument();
    expect(screen.getByText("deploying")).toBeInTheDocument();
    expect(screen.getByText("recovery")).toBeInTheDocument();
    expect(screen.getByText("Cut candidate")).toBeInTheDocument();
    expect(screen.getByText("Rollback")).toBeInTheDocument();
    expect(screen.getByText(/下一步: recovery/i)).toBeInTheDocument();
    expect(screen.getByText("Build taskboard")).toBeInTheDocument();
  });

  it("hides non-release next action from release pane", () => {
    const { container } = render(
      <GoalBoard
        snapshot={{
          goal: { title: "Phase 1", phase: "execution", status: "active" },
          columns: {
            ready: [{ task_id: "t-1", title: "Build taskboard" }],
            release_ready: [{ task_id: "t-2", title: "Cut candidate" }],
          },
          next_action: { kind: "execute", task_id: "t-1" },
        }}
      />,
    );

    if (container.textContent?.includes("下一步: execute · t-1")) {
      throw new Error("release pane should not render non-release next action");
    }
  });
});
