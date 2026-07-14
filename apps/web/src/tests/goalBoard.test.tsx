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
});
