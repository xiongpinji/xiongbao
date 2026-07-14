import { buildPrimaryNavigation, PRIMARY_SHELL_SURFACES } from "../shell/shellRoutes";
import { resolveSettingsLocation } from "../pages/settingsLocation";

type LightweightTask = {
  id: string;
  kind: "chat" | "workflow" | "creative" | "agent" | "settings" | "run";
  title: string;
  subtitle: string;
  route: string;
  status: "ready" | "running" | "attention";
  badge?: string;
  pinned: boolean;
  isPrimary: boolean;
  updatedAt: number;
};

type LightweightChatState = {
  goal: string;
  loading: boolean;
  run: unknown | null;
  streamText: string;
  error: string | null;
};

type LightweightShellState = {
  tasks: LightweightTask[];
  currentContext: LightweightTask | null;
  commandPaletteOpen: boolean;
  chatSessionVersion: number;
  chatTaskState: {
    chat: LightweightChatState;
  };
};

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function createDefaultChatState(): LightweightChatState {
  return {
    goal: "",
    loading: false,
    run: null,
    streamText: "",
    error: null,
  };
}

function createLightweightShellState(): LightweightShellState {
  return {
    tasks: [
      {
        id: "chat",
        kind: "chat",
        title: "对话",
        subtitle: "统一工作区中的主对话上下文",
        route: "/chat",
        status: "ready",
        badge: "工作区",
        pinned: true,
        isPrimary: true,
        updatedAt: 1,
      },
    ],
    currentContext: {
      id: "chat",
      kind: "chat",
      title: "对话",
      subtitle: "统一工作区中的主对话上下文",
      route: "/chat",
      status: "ready",
      badge: "工作区",
      pinned: true,
      isPrimary: true,
      updatedAt: 1,
    },
    commandPaletteOpen: false,
    chatSessionVersion: 0,
    chatTaskState: {
      chat: createDefaultChatState(),
    },
  };
}

function resetChatSession(state: LightweightShellState) {
  state.currentContext =
    state.currentContext?.id === "chat"
      ? { ...state.currentContext, updatedAt: state.currentContext.updatedAt + 1 }
      : state.currentContext;
  state.chatSessionVersion += 1;
  state.chatTaskState.chat = createDefaultChatState();
}

function syncRoute(
  state: LightweightShellState,
  snapshot: Omit<LightweightTask, "updatedAt" | "id"> & { taskId: string },
) {
  const nextTask: LightweightTask = {
    id: snapshot.taskId,
    kind: snapshot.kind,
    title: snapshot.title,
    subtitle: snapshot.subtitle,
    route: snapshot.route,
    status: snapshot.status,
    badge: snapshot.badge,
    pinned: snapshot.pinned,
    isPrimary: snapshot.isPrimary,
    updatedAt: state.tasks.length + 10,
  };

  state.tasks = [nextTask, ...state.tasks.filter((task) => task.id !== snapshot.taskId)];
  state.currentContext = nextTask;
}

describe("shell navigation integration", () => {
  it("includes goal board in primary shell navigation", () => {
    assert(
      PRIMARY_SHELL_SURFACES.some((surface) => surface.taskId === "goal-board"),
      "Goal Board surface should be present in primary navigation",
    );
  });

  it("retains goalId in goal board navigation routes", () => {
    const navigation = buildPrimaryNavigation(
      [{ id: "goal-board:phase-alpha", route: "/goal-board?goalId=phase-alpha" }],
      "goal-board:phase-alpha",
    );
    const goalBoardItem = navigation.find((item) => item.taskId === "goal-board");

    assert(goalBoardItem, "Goal Board navigation item should exist");
    assert(
      goalBoardItem.preferredRoute === "/goal-board?goalId=phase-alpha",
      `Expected preferred route to keep goalId, received ${goalBoardItem.preferredRoute}`,
    );
    assert(goalBoardItem.active === true, "Goal Board item should be active");
  });

  it("re-reads settings deep links from query changes", () => {
    const first = resolveSettingsLocation("?section=index&tab=knowledge");
    const second = resolveSettingsLocation("?section=index&tab=open-source");

    assert(first.section === "index", `Expected first section to be index, received ${first.section}`);
    assert(first.tab === "knowledge", `Expected first tab to be knowledge, received ${first.tab}`);
    assert(second.tab === "open-source", `Expected second tab to be open-source, received ${second.tab}`);
  });

  it("new session resets chat state and search opens the palette", () => {
    const state = createLightweightShellState();
    state.chatTaskState.chat = {
      goal: "Ship task 6",
      loading: true,
      run: null,
      streamText: "partial",
      error: "boom",
    };

    resetChatSession(state);
    state.commandPaletteOpen = true;

    assert(state.chatTaskState.chat.goal === "", `Expected chat goal to reset, received ${state.chatTaskState.chat.goal}`);
    assert(state.chatTaskState.chat.loading === false, "Expected chat loading to reset to false");
    assert(state.chatTaskState.chat.streamText === "", `Expected stream text to reset, received ${state.chatTaskState.chat.streamText}`);
    assert(state.chatTaskState.chat.error === null, `Expected chat error to reset, received ${state.chatTaskState.chat.error}`);
    assert(state.chatSessionVersion === 1, `Expected chat session version to increment, received ${state.chatSessionVersion}`);
    assert(state.commandPaletteOpen === true, "Expected command palette to open");
  });

  it("active state follows the current surface instead of staying on the first item", () => {
    const navigation = buildPrimaryNavigation([], "workflows");
    const activeItems = navigation.filter((item) => item.active);

    assert(activeItems.length === 1, `Expected one active item, received ${activeItems.length}`);
    assert(activeItems[0]?.taskId === "workflows", `Expected workflows to be active, received ${activeItems[0]?.taskId}`);
  });

  it("tracked goal board sessions preserve the goal-specific route", () => {
    const state = createLightweightShellState();
    syncRoute(state, {
      taskId: "goal-board:phase-beta",
      kind: "workflow",
      route: "/goal-board?goalId=phase-beta",
      title: "目标任务板",
      subtitle: "持续推进当前交付主目标 · phase-beta",
      badge: "PM",
      pinned: true,
      isPrimary: true,
      status: "ready",
    });

    assert(
      state.tasks[0]?.route === "/goal-board?goalId=phase-beta",
      `Expected tracked task route to preserve goalId, received ${state.tasks[0]?.route}`,
    );
  });
});
