class AssertionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AssertionError";
  }
}

const pendingTests: Promise<void>[] = [];
const runtime = globalThis as typeof globalThis & {
  process?: {
    exitCode?: number;
  };
};

function formatValue(value: unknown) {
  if (typeof value === "string") {
    return `"${value}"`;
  }
  return String(value);
}

globalThis.describe = function describe(_name: string, fn: () => void) {
  fn();
};

globalThis.it = function it(name: string, fn: () => void | Promise<void>) {
  const pending = Promise.resolve()
    .then(fn)
    .then(
      () => {
        console.log(`PASS ${name}`);
      },
      (error) => {
        const detail = error instanceof Error ? error.message : String(error);
        console.error(`FAIL ${name}`);
        console.error(detail);
        if (runtime.process) {
          runtime.process.exitCode = 1;
        }
      },
    );

  pendingTests.push(pending);
};

globalThis.expect = function expect(actual: unknown) {
  return {
    toBeInTheDocument() {
      if (actual == null) {
        throw new AssertionError(`Expected value to be present, received ${formatValue(actual)}`);
      }
    },
  };
};

export async function waitForTests() {
  await Promise.all(pendingTests);
  if (runtime.process?.exitCode && runtime.process.exitCode !== 0) {
    throw new Error("Test run failed");
  }
}
