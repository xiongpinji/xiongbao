# RFC-001：沙箱默认安全姿态与分级演进

- **状态**：Draft（提案，未实施）
- **作者**：工作流 F（竞品差距推进）
- **日期**：2026-08-02
- **关联**：README「安全默认姿态」、`xagent/adapters/sandbox/base.py`、`xagent/infra/settings.py`（`ToolsSettings`）

## 1. 背景与问题

X-Agent 当前执行类能力的安全默认：

- `shell_exec` 工具默认禁用（`XAGENT_TOOLS__ENABLE_SHELL=true` 显式放开）；
- 沙箱适配层默认 `DisabledSandbox`：拒绝执行，绝不在宿主机直接 exec 不可信代码；
- `python_exec` / `file_write` 等 power tools 直接运行在 API 进程内，仅靠 `_WORKSPACE` 目录约束。

问题：一旦用户显式打开 shell / python 执行，代码实际跑在**宿主机 API 进程**里，文件系统隔离是「自律式」的（路径前缀检查），无法防御：

- 路径逃逸（symlink、`..` 变体、绝对路径绕过）；
- 资源耗尽（fork bomb、磁盘写满、内存打爆）；
- 网络侧信道（执行代码随意外连，数据外泄）；
- 多租户串扰（同进程内不同租户的任务互相可见）。

随着短剧工厂开放给外部试点客户，「agent 能跑代码」与「私有化交付安全底线」之间的矛盾必须先于 GA 解决。

## 2. 目标与非目标

**目标**

1. 保持 lite 模式「默认禁执行」的零配置安全体验不变；
2. 为需要执行能力的部署提供**有真实隔离边界**的分级选项；
3. 每一级的开启都是显式配置，且 `validate_for_production()` 能硬校验「生产模式不允许宿主机裸奔执行」。

**非目标**

- 不自研容器运行时 / microVM；
- 不引入 AGPL 组件（Daytona 等）；
- 不改变 lite 单机零依赖的交付形态（Docker 不是 lite 的硬依赖）。

## 3. 方案：三级演进

### Level 0 — lite 默认：禁执行（现状，保持）

- `enable_shell=false`、`DisabledSandbox`；执行类工具不注册。
- 适用：本地演示、单机试点、只读型 agent 场景。
- 成本：零。

### Level 1 — Docker 沙箱（私有化主力，建议下个迭代落地）

- 新增 `DockerSandbox(Sandbox)`：`docker run --rm --network=none --memory=512m --cpus=1 --read-only -v <workspace-ro>:/work` 一次性容器执行，stdout/stderr 回收为 `SandboxResult`。
- 配置：`XAGENT_SANDBOX__BACKEND=docker`，`XAGENT_SANDBOX__DOCKER_IMAGE=xagent-sandbox:py3.12`（预装 python/node 最小镜像，离线可构建）。
- shell/python 工具在 `backend=docker` 时把调用路由进沙箱，而非宿主机；`_WORKSPACE` 以只读 + 显式可写子目录挂载。
- 隔离收益：网络默认关闭、资源限额、只读根 fs、进程级隔离，多租户串扰面收敛到 Docker daemon 本身。
- 生产硬校验新增：`is_production and tools.enable_shell and sandbox.backend in ("disabled","host")` → 配置问题清单报错。
- 风险与缓解：Windows 宿主机需 Docker Desktop/WSL2（部署文档标注）；镜像构建纳入 release 流水线。

### Level 2 — E2B（云托管 / 高并发租户隔离，企业版选项）

- 新增 `E2BSandbox(Sandbox)`：走 E2B（Apache-2.0 SDK）firecracker microVM，每任务独立 VM，秒级冷启动。
- 配置：`XAGENT_SANDBOX__BACKEND=e2b` + `XAGENT_SANDBOX__E2B_API_KEY`。
- 适用：SaaS 化 / 多租户高并发 / 不可信代码占比高的场景；私有化纯内网部署留在 Level 1。
- 与现有架构对齐：README 架构表已把 `adapters/sandbox` 定位为「E2B / microsandbox (+docker 兜底)」，本 RFC 是把该叙事落到分级实现。

### 分级对照

| 级别 | 后端 | 隔离边界 | 网络 | 适用 |
|---|---|---|---|---|
| L0 | disabled | 不执行 | — | lite 默认 |
| L1 | docker | 容器（namespace/cgroup） | 默认禁 | 私有化主力 |
| L2 | e2b | microVM | 受控白名单 | 云/企业版 |

## 4. 实施步骤（Level 1，建议范围）

1. `adapters/sandbox/` 新增 `docker_sandbox.py`，实现 `Sandbox` 协议（run_code/health）；
2. `SandboxSettings` 增加 `backend / docker_image / mem_limit / cpu_limit / network` 字段；
3. `power_tools.shell_exec` / `python_exec` 增加沙箱路由分支（backend!=host 时走沙箱）；
4. 沙箱镜像 Dockerfile + 离线构建脚本（`scripts/`）；
5. `validate_for_production()` 增加「生产禁宿主机执行」硬校验；
6. 测试：mock docker CLI 验证命令拼装与限额参数；集成测试（有 docker 时）跑通 hello-world。

## 5. 度量

- 生产部署中 `backend=host` 配置数为 0（硬校验保证）；
- 沙箱任务 P95 启动开销 < 3s（L1）/ < 5s（L2）；
- 逃逸类安全工单为 0。
