# Web/API P0 发布可信基线实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复流式并发工具执行缺陷，建立不掩盖高风险错误的静态门禁，收紧 Web 发布范围，并保证 GitHub Release 只能在 Web/API 全部门禁成功后创建。

**架构：** 编排层以显式工具执行结果代替并发闭包修改计数器；CI 将关键 Ruff 规则设为硬门禁，并对完整 Ruff/mypy 建立只降不升的基线。Web 路由把短剧与剪辑入口统一映射为排除说明页，Release job 依赖全部 Web/API 验证任务。

**技术栈：** Python 3.11、FastAPI、pytest、Ruff、mypy、React 18、TypeScript、Node.js 20、GitHub Actions。

---

## 文件结构

- 修改 `apps/api/xagent/core/orchestration/loop.py`：统一流式并发工具执行结果与统计聚合。
- 修改 `apps/api/tests/test_orchestration.py`：增加流式双工具并发回归。
- 创建 `.quality-baseline.json`：记录完整 Ruff/mypy 的最大允许存量。
- 创建 `scripts/check_static_quality.py`：执行关键硬门禁和存量基线检查。
- 创建 `apps/api/tests/test_static_quality_gate.py`：验证基线比较与输出解析。
- 修改 `.github/workflows/ci.yml`：执行关键静态门禁、Web 全量单元测试和 tag 后发布。
- 创建 `apps/web/scripts/run-all-tests.mjs`：默认发现并运行全部 Web 单元测试文件。
- 修改 `apps/web/package.json`：默认 `npm test` 指向全量测试入口。
- 修改 `apps/web/src/tests/shellNavigation.test.ts`：断言发布导航不包含短剧。
- 创建 `apps/web/src/pages/ExcludedModulePage.tsx`：为排除模块提供诚实说明。
- 修改 `apps/web/src/App.tsx`：短剧、画布和剪辑路由统一进入排除说明页。
- 修改 `apps/web/src/pages/ProfessionalModePage.tsx`：专业模式只展示工作流。
- 修改 `apps/web/src/shell/shellRoutes.ts`：移除短剧主导航 surface。
- 创建 `scripts/verify_release_versions.py`：验证 API、Web、README 和 tag 版本一致。
- 创建 `apps/api/tests/test_verify_release_versions.py`：验证版本解析和 tag 比较。
- 修改 `README.md`：修正版本和 Web/API 发布范围口径。
- 修改 `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`：记录本阶段真实边界。
- 修改 `docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`：逐包更新状态和证据。

## 任务 1：修复流式并发工具执行

**文件：**

- 修改：`apps/api/xagent/core/orchestration/loop.py:13-25,1451-1588`
- 测试：`apps/api/tests/test_orchestration.py`

- [x] **步骤 1：编写流式双工具失败测试**

在 `test_orchestration.py` 增加一个 `LiteLLMClient` 测试替身。第一轮流返回两个 `echo` tool call，第二轮返回最终回答；工具注册表对两个调用分别返回 `a`、`b`。

```python
from xagent.adapters.llm.litellm_client import LiteLLMClient, StreamChunk
from xagent.adapters.tools.base import ToolResult


class _ParallelEchoRegistry:
    def specs(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "echo",
                "description": "回显文本",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            },
        }]

    async def call(self, name, args, ctx):  # noqa: ARG002
        return ToolResult(ok=True, output=args["text"])


class _StreamingParallelLLM(LiteLLMClient):
    def __init__(self) -> None:
        self.calls = 0
        self.second_call_messages: list[Message] = []

    async def stream_with_tools(self, messages, tools, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield StreamChunk(
                tool_call_deltas=[
                    {"index": 0, "id": "call_a", "function": {"name": "echo", "arguments": '{"text":"a"}'}},
                    {"index": 1, "id": "call_b", "function": {"name": "echo", "arguments": '{"text":"b"}'}},
                ],
                finished=True,
            )
            return
        self.second_call_messages = list(messages)
        yield StreamChunk(delta_content="并发工具执行完成。", finished=True)

    async def complete(self, messages, **kwargs):
        return LLMResponse(content="并发工具执行完成。", model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):
        raise AssertionError("流式回归不得进入非流式路径")

    async def health(self) -> bool:
        return True
```

测试断言如下：

```python
async def test_streaming_parallel_tools_return_real_results(monkeypatch) -> None:
    llm = _StreamingParallelLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr("xagent.core.orchestration.loop.get_tool_registry", lambda: _ParallelEchoRegistry())
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    run = await run_agent_builtin("并发调用两个 echo", principal=principal, role_name="general")
    results = [event.content for event in run.events if event.kind == StepKind.tool_result]
    assert results == ["a", "b"]
    assert all("UnboundLocalError" not in str(value) for value in results)
    assert {message.tool_call_id for message in llm.second_call_messages if message.role == "tool"} == {"call_a", "call_b"}
```

- [x] **步骤 2：运行测试验证正确失败**

运行：

```powershell
$env:PYTHONPATH = (Resolve-Path apps/api)
& 'D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\apps\api\.venv\Scripts\python.exe' -X utf8 -m pytest apps/api/tests/test_orchestration.py::test_streaming_parallel_tools_return_real_results -q
```

预期：FAIL；tool result 包含 `UnboundLocalError: cannot access local variable '_tool_success'`，证明覆盖真实缺陷。

- [x] **步骤 3：增加显式执行结果模型**

在 `loop.py` 增加：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class _ToolExecutionOutcome:
    name: str
    call_id: str
    text: str
    executed: bool = False
    succeeded: bool | None = None
    elapsed_seconds: float | None = None
```

`_exec_one_inner` 返回 `_ToolExecutionOutcome`，不再直接执行 `_tool_success += 1` 或 `_tool_fail += 1`。拒绝、参数错误和缓存命中使用 `executed=False`；真实工具调用使用 `executed=True` 并携带 `succeeded`、耗时和文本。

- [x] **步骤 4：在聚合阶段更新统计**

`asyncio.gather` 返回后，在原始 call 顺序的聚合循环中统一更新：

```python
if isinstance(result, Exception):
    _tool_fail += 1
    _tool_fail_by_type[tool_name] = _tool_fail_by_type.get(tool_name, 0) + 1
    result_text = f"[错误] {type(result).__name__}: {result}"
else:
    result_text = result.text
    if result.executed and result.succeeded is True:
        _tool_success += 1
        _tool_success_by_type[tool_name] = _tool_success_by_type.get(tool_name, 0) + 1
    elif result.executed and result.succeeded is False:
        _tool_fail += 1
        _tool_fail_by_type[tool_name] = _tool_fail_by_type.get(tool_name, 0) + 1
    if result.elapsed_seconds is not None:
        _tool_time_by_type.setdefault(tool_name, []).append(result.elapsed_seconds)
```

将 semaphore 作为 `_exec_one` 的显式参数传入，避免闭包捕获循环变量。

- [x] **步骤 5：运行红绿与相关回归**

运行：

```powershell
python -m pytest apps/api/tests/test_orchestration.py -q
ruff check apps/api/xagent/core/orchestration/loop.py apps/api/tests/test_orchestration.py --select F823
```

预期：编排测试全部通过；本任务直接触发的 `F823` 为 0。完整
`F821,F822,F823,B023` 集合由任务 2 在修复两处模型降级闭包后统一清零。

- [x] **步骤 6：提交 P0-A**

```powershell
git add apps/api/xagent/core/orchestration/loop.py apps/api/tests/test_orchestration.py docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "fix(编排): 修复流式并发工具结果统计"
```

## 任务 2：建立关键静态门禁和存量基线

**文件：**

- 创建：`.quality-baseline.json`
- 创建：`scripts/check_static_quality.py`
- 创建：`apps/api/tests/test_static_quality_gate.py`
- 修改：`.github/workflows/ci.yml:28-35`
- 修改：`apps/api/xagent/core/orchestration/loop.py:1834,2054`

- [x] **步骤 1：编写基线比较失败测试**

脚本暴露纯函数：

```python
def parse_ruff_count(output: str) -> int:
    return len(json.loads(output))

def parse_mypy_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if ": error:" in line)

def exceeded(current: dict[str, int], baseline: dict[str, int]) -> dict[str, tuple[int, int]]:
    return {name: (current[name], limit) for name, limit in baseline.items() if current[name] > limit}
```

测试断言 Ruff JSON 可计数、mypy error 行可计数，且 `ruff=287` 相对基线 `286` 被拒绝。

测试通过 `importlib.util.spec_from_file_location` 从仓库根的 `scripts/check_static_quality.py` 加载模块；仓库根由 `Path(__file__).resolve().parents[3]` 确定，不要求把 `scripts/` 变成运行时 Python 包。

- [x] **步骤 2：运行测试验证脚本尚不存在**

运行：

```powershell
python -m pytest apps/api/tests/test_static_quality_gate.py -q
```

预期：FAIL，`ModuleNotFoundError` 或导入目标不存在。

- [x] **步骤 3：实现静态质量脚本与基线**

`.quality-baseline.json` 固定当前新鲜基线：

```json
{
  "ruff": 286,
  "mypy": 74
}
```

脚本从仓库根定位 `apps/api`，分别运行 Ruff JSON 输出和 mypy 文本输出；任一当前计数超过基线时退出 1。命令本身缺失或输出不可解析时同样退出 1，禁止误报通过。

- [x] **步骤 4：修复剩余关键 B023**

将两处循环内 lambda 显式绑定模型：

```python
lambda selected_model=target_model: llm.complete_with_tools(
    state.messages, specs, model=selected_model
)
```

提示工程路径使用同样绑定方式。运行关键 Ruff 集合，预期 0。

- [x] **步骤 5：修改 CI**

后端 job 使用：

```yaml
- name: Critical lint gate
  run: ruff check xagent tests --select F821,F822,F823,B023

- name: Static quality baseline
  working-directory: ../..
  run: python scripts/check_static_quality.py
```

删除 Ruff/mypy 的 `|| true`。完整检查由基线脚本执行并阻止新增，不把 286/74 写成零错误。

- [x] **步骤 6：验证并提交 P0-B**

运行：

```powershell
python -m pytest apps/api/tests/test_static_quality_gate.py apps/api/tests/test_orchestration.py -q
python scripts/check_static_quality.py
ruff check apps/api/xagent apps/api/tests --select F821,F822,F823,B023
```

预期：全部退出 0，脚本报告 `ruff <= 286`、`mypy <= 74`。

提交：

```powershell
git add .quality-baseline.json scripts/check_static_quality.py apps/api/tests/test_static_quality_gate.py apps/api/xagent/core/orchestration/loop.py .github/workflows/ci.yml docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "ci(质量): 阻断关键静态错误并固定基线"
```

## 任务 3：让 Web 测试覆盖真实发布范围

**文件：**

- 创建：`apps/web/scripts/run-all-tests.mjs`
- 修改：`apps/web/package.json`
- 修改：`apps/web/src/tests/shellNavigation.test.ts`
- 创建：`apps/web/src/pages/ExcludedModulePage.tsx`
- 修改：`apps/web/src/App.tsx`
- 修改：`apps/web/src/pages/ProfessionalModePage.tsx`
- 修改：`apps/web/src/shell/shellRoutes.ts`
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：增加发布导航失败测试**

在 `shellNavigation.test.ts` 增加：

```typescript
it("excludes creative studio from the Web API release navigation", () => {
  assert(
    PRIMARY_SHELL_SURFACES.every((surface) => surface.taskId !== "creative"),
    "Creative studio must not appear in the Web/API release navigation",
  );
});
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
npm test -- shellNavigation.test.ts
```

预期：FAIL，当前 `PRIMARY_SHELL_SURFACES` 包含 `taskId=creative`。

- [ ] **步骤 3：实现全量 Web 测试入口**

`run-all-tests.mjs` 枚举 `src/tests` 下所有 `.test.ts` 和 `.test.tsx`，逐个调用现有 `run-tests.mjs`；任一文件失败即退出非零。`package.json` 调整为：

```javascript
import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const testsDir = path.join(projectRoot, "src", "tests");
const runner = path.join(projectRoot, "scripts", "run-tests.mjs");
const testFiles = readdirSync(testsDir)
  .filter((name) => /\.test\.tsx?$/.test(name))
  .sort();

if (testFiles.length === 0) {
  console.error("No Web unit test files found");
  process.exit(1);
}

for (const testFile of testFiles) {
  const result = spawnSync(process.execPath, [runner, testFile], {
    cwd: projectRoot,
    stdio: "inherit",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
```

```json
{
  "scripts": {
    "test": "node ./scripts/run-all-tests.mjs",
    "test:file": "node ./scripts/run-tests.mjs"
  }
}
```

- [ ] **步骤 4：收紧 Web 路由和导航**

`ExcludedModulePage` 固定显示：

```tsx
import { Link } from "react-router-dom";

export default function ExcludedModulePage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <h1 className="text-xl font-semibold text-white">当前 Web/API 发布不包含此模块</h1>
      <p className="max-w-xl text-sm text-neutral-400">短剧能力由独立项目运行，稳定后再按集成规格接入 X-Agent。</p>
      <Link className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black" to="/chat">
        返回对话
      </Link>
    </div>
  );
}
```

在 `App.tsx` 将 `/creative`、`/creative/canvas`、`/canvas`、`/editor` 映射到此页，并删除 Creative/Editor 的 lazy import 与全屏分支。`shellRoutes.ts` 删除 creative 主 surface。`ProfessionalModePage` 只保留 workflow 模式和 `WorkflowsPage`，不保留短剧 tab 或剪辑链接。

- [ ] **步骤 5：把 Web test 加入 CI**

在 frontend job 的 typecheck 前增加：

```yaml
- name: Unit test
  run: npm test
```

- [ ] **步骤 6：验证并提交 P0-C**

运行：

```powershell
npm test
npm run lint
npm run typecheck
npm run build
```

预期：2 个测试文件全部执行并通过；lint 仍为 0 error，warning 不得超过基线 100；typecheck/build 退出 0；build 产物不再包含 `CreativeStudioPage` 和 `EditorPage` chunk。

提交：

```powershell
git add apps/web .github/workflows/ci.yml docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "feat(Web): 收紧 Web API 发布入口与测试范围"
```

## 任务 4：统一版本事实源并建立 CI 后发布

**文件：**

- 创建：`scripts/verify_release_versions.py`
- 创建：`apps/api/tests/test_verify_release_versions.py`
- 修改：`README.md`
- 修改：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：编写版本校验失败测试**

测试在临时目录写入 API `pyproject.toml`、Web `package.json` 和 README，通过纯函数验证：

```python
assert verify_versions(root, tag="v1.0.0") == []
(root / "README.md").write_text("**当前 Web/API 版本：0.1.0**", encoding="utf-8")
assert "README" in "\n".join(verify_versions(root, tag="v1.0.0"))
assert "tag" in "\n".join(verify_versions(root, tag="v1.0.1"))
```

测试同样通过 `importlib.util.spec_from_file_location` 加载仓库根的 `scripts/verify_release_versions.py`，避免改变应用包结构。

- [ ] **步骤 2：运行测试验证脚本尚不存在**

运行：

```powershell
python -m pytest apps/api/tests/test_verify_release_versions.py -q
```

预期：FAIL，版本校验模块不存在。

- [ ] **步骤 3：实现版本校验脚本**

脚本使用 `tomllib` 读取 API 版本、`json` 读取 Web 版本、正则读取 README `当前 Web/API 版本`。传入 `--tag` 时去掉 `v` 后比较。任一不一致打印逐项错误并退出 1。

- [ ] **步骤 4：修正文档口径**

README 顶部改为：

```markdown
**当前 Web/API 版本：1.0.0**（API `pyproject.toml` 为版本事实源；Web package 与发布 tag 必须通过 CI 一致性检查）
```

状态事实源明确：当前增强阶段只验收 Web/API；短剧与桌面端不构成本阶段发布结论。

- [ ] **步骤 5：增加 tag 版本 job 与 Release job**

新增 `release-version` job，仅 tag push 执行：

```yaml
release-version:
  if: startsWith(github.ref, 'refs/tags/v')
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: python scripts/verify_release_versions.py --tag "${GITHUB_REF_NAME}"
```

新增 `release` job：

```yaml
release:
  needs: [backend, frontend, license-gate, config-governance, docker-build, e2e-api, load-test, promptfoo-eval, release-version]
  if: startsWith(github.ref, 'refs/tags/v')
  permissions:
    contents: write
  steps:
    - uses: actions/checkout@v4
    - run: gh release create "${GITHUB_REF_NAME}" --verify-tag --generate-notes
      env:
        GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **步骤 6：验证并提交 P0-D**

运行：

```powershell
python -m pytest apps/api/tests/test_verify_release_versions.py -q
python scripts/verify_release_versions.py --tag v1.0.0
python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))"
```

预期：版本测试和当前 v1.0.0 校验通过；workflow YAML 可解析；release `needs` 覆盖全部 Web/API gate。

提交：

```powershell
git add scripts/verify_release_versions.py apps/api/tests/test_verify_release_versions.py README.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md .github/workflows/ci.yml docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "ci(发布): 统一 Web API 版本并门禁 Release"
```

## 任务 5：P0 完成审计

**文件：**

- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`
- 创建：`docs/coordination/reports/WEB_API_P0_RELEASE_FOUNDATION_EVIDENCE.md`

- [ ] **步骤 1：运行后端 P0 验证**

```powershell
python -m pytest apps/api/tests/test_orchestration.py apps/api/tests/test_static_quality_gate.py apps/api/tests/test_verify_release_versions.py -q
ruff check apps/api/xagent apps/api/tests --select F821,F822,F823,B023
python scripts/check_static_quality.py
python scripts/verify_release_versions.py --tag v1.0.0
```

- [ ] **步骤 2：运行前端 P0 验证**

```powershell
Set-Location apps/web
npm test
npm run lint
npm run typecheck
npm run build
```

- [ ] **步骤 3：运行仓库一致性检查**

```powershell
git diff --check HEAD~4..HEAD
git status --short
rg -n "ruff check.*\|\| true|mypy.*\|\| true" .github/workflows/ci.yml
rg -n "CreativeStudioPage|EditorPage" apps/web/dist/assets
```

预期：diff check 退出 0；工作树无未提交改动；CI 不含 Ruff/mypy `|| true`；production assets 不含排除页面 chunk。

- [ ] **步骤 4：写证据报告并更新任务板**

证据报告逐命令记录退出码、通过数、静态错误基线、Web warning 数和剩余风险。P0-A 至 P0-E 全部有证据后转 DONE；P1-A 转 READY。

- [ ] **步骤 5：提交 P0 证据**

```powershell
git add docs/coordination/WEB_API_RELEASE_TASK_BOARD.md docs/coordination/reports/WEB_API_P0_RELEASE_FOUNDATION_EVIDENCE.md
git commit -m "docs(验收): 归档 Web API P0 发布基线证据"
```
