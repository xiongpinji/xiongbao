# 前端演示态标识补齐实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为当前前端工作区中容易误导为“真实智能执行”的页面补齐“预览 / 辅助 / 本地分析”标识，降低用户误解，同时不影响现有主执行入口。

**架构：** 本次只做前端文案与轻提示层收口，不改后端协议、不新增真实执行能力。改动集中在页面与组件的 header / helper 区域，以及现有 `ConversationalCommand` 附近；通过轻提示、小标签和 fallback 文案澄清“真实执行入口”和“本地回显 / 导航辅助入口”的边界。测试沿用现有 `apps/web/tests/*.mjs` 的源码断言模式，给受影响页面补静态源码级校验。

**技术栈：** React 18、TypeScript、Vite、node:test、assert/strict

---

## 文件结构与职责边界

### 核心修改文件

- `apps/web/src/pages/AgentsPage.tsx`
  - 为角色页补“预览角色 / 本地演示数据 / 调度建议非真实执行”提示。
- `apps/web/src/pages/MemoryPage.tsx`
  - 为记忆检索页补“辅助模式 / 不直接返回真实检索结果”提示。
- `apps/web/src/pages/OpenSourcePage.tsx`
  - 为开源比选页补“预览态 / 不直接返回实时仓库结果”提示。
- `apps/web/src/components/settings/SettingsLayout.tsx`
  - 为“配置助手”补“仅生成检查清单，不直接改配置”提示。
- `apps/web/src/components/layout/ShellContextPanel.tsx`
  - 为“上下文助手”补“只做总结 / 建议 / 跳转，不直接执行后台任务”提示。
- `apps/web/src/components/runs/RunConsole.tsx`
  - 为“运行分析助手”补“基于已加载运行详情做本地分析”提示。
- `apps/web/src/pages/WorkflowsPage.tsx`
  - 为“工作流编排助手”补“当前优先生成页面内步骤草案，执行仍以按钮为准”提示。
- `apps/web/src/pages/CreativeStudioPage.tsx`
  - 为创作草案 / 生产执行边界补提示。

### 测试文件

- `apps/web/tests/workspaceCatalog.test.mjs`
  - 新增，统一校验演示态 / 辅助态文案是否已写入关键页面源码。
- `apps/web/tests/runConsoleViews.test.mjs`
  - 补 `RunConsole` 的本地分析说明断言。

---

## 任务 1：为演示 / 辅助页面补齐静态提示文案

**文件：**
- 修改：`apps/web/src/pages/AgentsPage.tsx`
- 修改：`apps/web/src/pages/MemoryPage.tsx`
- 修改：`apps/web/src/pages/OpenSourcePage.tsx`
- 修改：`apps/web/src/components/settings/SettingsLayout.tsx`
- 修改：`apps/web/src/components/layout/ShellContextPanel.tsx`
- 测试：`apps/web/tests/workspaceCatalog.test.mjs`

- [ ] **步骤 1：先编写失败的源码断言测试**

```js
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function read(relativePath) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("workspace pages expose preview and helper disclaimers", async () => {
  const [agentsSource, memorySource, openSourceSource, settingsSource, contextPanelSource] = await Promise.all([
    read("../src/pages/AgentsPage.tsx"),
    read("../src/pages/MemoryPage.tsx"),
    read("../src/pages/OpenSourcePage.tsx"),
    read("../src/components/settings/SettingsLayout.tsx"),
    read("../src/components/layout/ShellContextPanel.tsx"),
  ]);

  assert.match(agentsSource, /预览态：当前“角色调度”优先生成任务拆解建议/);
  assert.match(agentsSource, /仅用于 UI 预览，不代表真实可调度角色集合/);
  assert.match(memorySource, /辅助模式：当前入口主要用于整理检索意图与跳转索引配置/);
  assert.match(openSourceSource, /预览态：当前入口优先整理开源比选目标与接入策略/);
  assert.match(settingsSource, /辅助模式：配置助手当前只生成检查清单与调整建议/);
  assert.match(contextPanelSource, /辅助模式：当前为上下文助手，优先提供总结、建议与跳转/);
});
```

- [ ] **步骤 2：运行测试，确认当前缺少这些文案而失败**

运行：

```bash
npm --prefix "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\apps\web" exec -- node --test tests/workspaceCatalog.test.mjs
```

预期：FAIL，至少报出某个页面源码中缺少 `预览态` / `辅助模式` 文案。

- [ ] **步骤 3：在 AgentsPage 中补角色预览与 fallback 明示**

在 `AgentsPage.tsx` 的角色描述区与 `ConversationalCommand` 之间插入：

```tsx
<div className="mb-5 rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm leading-6 text-neutral-400">
  当前页用于浏览和预览智能体角色。角色说明与调度建议可用于工作流设计，但真实执行能力仍以后端返回的可用角色与工具链为准。
</div>
<div className="mb-5 rounded-2xl border border-[#d6ad62]/18 bg-[#d6ad62]/[0.06] px-4 py-3 text-xs leading-6 text-[#f2d99c]">
  预览态：当前“角色调度”优先生成任务拆解建议，不直接触发真实智能体执行。
</div>
```

并将 fallback 提示文案改为：

```tsx
<div className="mb-5 rounded-2xl border border-amber-400/20 bg-amber-400/5 px-4 py-3 text-sm text-amber-200">
  后端角色接口暂不可用，当前展示的是本地演示角色，仅用于 UI 预览，不代表真实可调度角色集合。
</div>
```

- [ ] **步骤 4：在 MemoryPage 中补检索辅助说明**

在 `header` 之后、`ConversationalCommand` 之前插入：

```tsx
<div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm leading-6 text-neutral-400">
  辅助模式：当前入口主要用于整理检索意图与跳转索引配置，不直接展示真实知识库命中结果。
</div>
```

并将 `initialAssistantMessage` 改为：

```tsx
initialAssistantMessage="你可以先描述检索或沉淀目标。我会优先整理检索意图、隔离边界和下一步入口；真实知识库结果仍需进入索引库或后端检索链路查看。"
```

- [ ] **步骤 5：在 OpenSourcePage 中补比选预览说明**

在 `header` 之后、`ConversationalCommand` 之前插入：

```tsx
<div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm leading-6 text-neutral-400">
  预览态：当前入口优先整理开源比选目标与接入策略，不直接返回实时仓库搜索结果。
</div>
```

并将 `initialAssistantMessage` 改为：

```tsx
initialAssistantMessage="告诉我你要补齐的能力，我会先整理比选目标、许可证关注点和接入策略。真实候选仓库列表仍需进入开源发现链路进一步检索。"
```

- [ ] **步骤 6：在 SettingsLayout 中补配置助手非写入说明**

在 `ConversationalCommand` 之前插入：

```tsx
<div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm leading-6 text-neutral-400">
  辅助模式：配置助手当前只生成检查清单与调整建议，不会直接修改本地或远端配置。
</div>
```

并将 `initialAssistantMessage` 改为：

```tsx
initialAssistantMessage={`你可以直接告诉我想怎么配置「${active.label}」。我会把自然语言整理成检查清单与调整建议，但不会直接写入配置。`}
```

- [ ] **步骤 7：在 ShellContextPanel 中补上下文助手边界说明**

在 `ConversationalCommand` 之前插入：

```tsx
<div className="mb-3 rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-xs leading-6 text-neutral-500">
  辅助模式：当前为上下文助手，优先提供总结、建议与跳转，不直接执行后台任务。
</div>
```

并将 `initialAssistantMessage` 改为：

```tsx
initialAssistantMessage="我会根据当前页面上下文给出总结、建议与下一步入口，必要时再引导你进入真实执行页面。"
```

- [ ] **步骤 8：运行测试，确认静态提示文案已补齐**

运行：

```bash
npm --prefix "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\apps\web" exec -- node --test tests/workspaceCatalog.test.mjs
```

预期：PASS。

- [ ] **步骤 9：Commit**

```bash
git -C "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent" add apps/web/src/pages/AgentsPage.tsx apps/web/src/pages/MemoryPage.tsx apps/web/src/pages/OpenSourcePage.tsx apps/web/src/components/settings/SettingsLayout.tsx apps/web/src/components/layout/ShellContextPanel.tsx apps/web/tests/workspaceCatalog.test.mjs
git -C "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent" commit -m "feat: clarify preview boundaries for helper workspace pages"
```

---

## 任务 2：为运行台与流程页补执行边界提示

**文件：**
- 修改：`apps/web/src/components/runs/RunConsole.tsx`
- 修改：`apps/web/src/pages/WorkflowsPage.tsx`
- 修改：`apps/web/src/pages/CreativeStudioPage.tsx`
- 修改：`apps/web/tests/runConsoleViews.test.mjs`
- 测试：`apps/web/tests/workspaceCatalog.test.mjs`

- [ ] **步骤 1：补失败的源码断言测试**

在 `workspaceCatalog.test.mjs` 追加：

```js
test("run, workflow, and creative surfaces explain execution boundaries", async () => {
  const [runConsoleSource, workflowSource, creativeSource] = await Promise.all([
    read("../src/components/runs/RunConsole.tsx"),
    read("../src/pages/WorkflowsPage.tsx"),
    read("../src/pages/CreativeStudioPage.tsx"),
  ]);

  assert.match(runConsoleSource, /当前分析助手优先基于已加载的运行详情做本地总结/);
  assert.match(workflowSource, /预览态：这里会先生成页面内步骤草案/);
  assert.match(creativeSource, /当前输入会优先生成创作草案与页面节点意图/);
});
```

并在 `runConsoleViews.test.mjs` 的 `run console exposes validation risk and recovery panel contracts` 断言后追加：

```js
assert.match(consoleSource, /当前分析助手优先基于已加载的运行详情做本地总结/);
```

- [ ] **步骤 2：运行测试，确认当前缺少这些说明而失败**

运行：

```bash
npm --prefix "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\apps\web" exec -- node --test tests/workspaceCatalog.test.mjs tests/runConsoleViews.test.mjs
```

预期：FAIL，报出至少一个缺少的说明文案。

- [ ] **步骤 3：在 RunConsole 中补本地分析说明**

在 `ConversationalCommand` 之前插入：

```tsx
<div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm leading-6 text-neutral-400">
  说明：当前分析助手优先基于已加载的运行详情做本地总结，帮助你快速查看 Timeline、Evidence 和 Artifacts。
</div>
```

并将 `initialAssistantMessage` 改为：

```tsx
initialAssistantMessage="我会基于当前已加载的运行详情回答，并按时间线、证据和产物帮你快速定位信息。"
```

- [ ] **步骤 4：在 WorkflowsPage 中补草案与执行边界说明**

在 `ConversationalCommand` 之前插入：

```tsx
<div className="mb-4 rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm leading-6 text-neutral-400">
  预览态：这里会先生成页面内步骤草案；正式执行仍以“创建并执行”按钮触发的后端工作流为准。
</div>
```

并将 `initialAssistantMessage` 改为：

```tsx
initialAssistantMessage="你说一句目标，我会先把它写成页面内步骤草案并同步到画布；确认后再通过执行按钮提交后端工作流。"
```

- [ ] **步骤 5：在 CreativeStudioPage 中补草案与正式生产说明**

在 brief / 对话入口区域附近插入：

```tsx
<div className="mb-4 rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm leading-6 text-neutral-400">
  说明：当前输入会优先生成创作草案与页面节点意图；正式生产链路仍以明确的执行按钮和后端返回结果为准。
</div>
```

如果该页已有执行按钮区，再在按钮区附近补一条短提示：

```tsx
<div className="mt-3 text-xs leading-5 text-neutral-500">
  “创建画布”用于生成草案；“执行 / 生产”才会进入真实后端链路。
</div>
```

- [ ] **步骤 6：运行测试，确认边界说明已补齐**

运行：

```bash
npm --prefix "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\apps\web" exec -- node --test tests/workspaceCatalog.test.mjs tests/runConsoleViews.test.mjs
```

预期：PASS。

- [ ] **步骤 7：运行前端类型检查与构建**

运行：

```bash
npm --prefix "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\apps\web" run typecheck
npm --prefix "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\apps\web" run build
```

预期：
- `typecheck` PASS
- `build` PASS
- 若仍有 chunk size warning，记录为非阻断项，不当场扩 scope 处理

- [ ] **步骤 8：Commit**

```bash
git -C "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent" add apps/web/src/components/runs/RunConsole.tsx apps/web/src/pages/WorkflowsPage.tsx apps/web/src/pages/CreativeStudioPage.tsx apps/web/tests/workspaceCatalog.test.mjs apps/web/tests/runConsoleViews.test.mjs
git -C "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent" commit -m "feat: clarify preview boundaries for runtime and workflow helpers"
```

---

## 自检

### 规格覆盖度

- Agents / Memory / Open Source / Settings / ShellContextPanel 的演示态标识：任务 1 覆盖
- RunConsole / Workflows / Creative 的边界说明：任务 2 覆盖
- 文案边界收口后的类型检查与构建验证：任务 2 步骤 7 覆盖

### 占位符扫描

- 无 TODO / 待定 / 后续实现 占位
- 每个步骤均给出精确文件、代码片段、测试命令与预期结果

### 类型一致性

- 所有新增提示均为现有 JSX 文案层插入，不引入新类型
- 新增测试沿用现有 `read()` + `assert.match()` 的源码断言模式
- `workspaceCatalog.test.mjs` 为新增测试文件，职责仅验证演示态 / 辅助态说明是否写入关键页面源码

---

计划已完成并保存到 `docs/superpowers/plans/2026-07-03-frontend-preview-boundaries.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
