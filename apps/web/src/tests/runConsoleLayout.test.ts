import {
  RUN_CONSOLE_HEADER_LAYOUT,
  RUN_CONSOLE_RUN_ID_LAYOUT,
} from "../components/runs/RunConsole.tsx";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

describe("run console responsive header", () => {
  it("keeps the summary stacked until the workspace has xl width", () => {
    assert(
      RUN_CONSOLE_HEADER_LAYOUT.includes(
        "xl:flex-row xl:items-start xl:justify-between",
      ),
      "Run header must not switch to a row while the workspace sidebar leaves insufficient width",
    );
    assert(
      RUN_CONSOLE_RUN_ID_LAYOUT.includes("break-all"),
      "Long run IDs must wrap instead of overlapping the summary card",
    );
  });
});
