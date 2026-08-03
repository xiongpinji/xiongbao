# 沙箱部署指南（RFC-001 分级执行隔离）

> 适用场景：开启 shell / python 执行类工具（`XAGENT_TOOLS__ENABLE_SHELL` /
> `XAGENT_TOOLS__ENABLE_PYTHON_EXEC`）时，为不可信代码选择隔离后端。
> 默认 `disabled`：不执行任何不可信代码，绝不在宿主机裸跑。
>
> 注意（2026-08-03 起）：`python_exec` 在 `backend=disabled` 或沙箱不可用/执行失败时**一律 fail-closed 拒绝执行**，不再回退宿主机子进程；启用 `XAGENT_TOOLS__ENABLE_PYTHON_EXEC=true` 必须同时配置 docker/e2b 沙箱后端。

---

## 1. 分级对照

| 级别 | 后端 | 隔离边界 | 网络 | 适用 |
|---|---|---|---|---|
| L0 | `disabled` | 不执行 | — | lite 默认 / 本地演示 / 只读型 agent |
| L1 | `docker` | 容器（namespace/cgroup） | **默认禁网**（`--network=none`） | 私有化主力 / 单机生产 |
| L2 | `e2b` | firecracker microVM（每任务独立 VM） | **模板默认有网**（见 §4 警告） | 云 / SaaS 多租户 / 高并发 |

生产模式（`XAGENT_MODE=full`）开启执行类工具时，启动校验强制要求
`XAGENT_SANDBOX__BACKEND=docker`（或 `e2b`），否则拒绝启动。

---

## 2. L1：Docker（私有化默认）

```bash
XAGENT_SANDBOX__BACKEND=docker
XAGENT_SANDBOX__DOCKER_IMAGE=python:3.11-slim   # 建议预构建最小镜像
XAGENT_SANDBOX__MEM_LIMIT=512m
XAGENT_SANDBOX__CPU_QUOTA=100000                # 100000 = 1 CPU
XAGENT_SANDBOX__NETWORK_DISABLED=true           # 默认 --network=none
XAGENT_SANDBOX__READONLY_ROOTFS=true            # 默认 --read-only
XAGENT_SANDBOX__TIMEOUT_SECONDS=30
```

- 依赖：宿主机 Docker daemon（Windows 需 Docker Desktop，走 npipe）。
- 安全语义：一次性容器（create → start → wait → logs → remove --force）、
  默认禁网、资源限额、只读根 fs、超时 kill、输出 64K 截断、
  工作区只读挂载 `/work`。
- 选型：私有化 / 内网 / 单机生产的首选，零外部依赖、零按量成本。

## 3. L2：E2B（云 / 企业场景）

```bash
XAGENT_SANDBOX__BACKEND=e2b
XAGENT_SANDBOX__E2B_API_KEY=e2b_***             # 也可读 E2B_API_KEY 环境变量
XAGENT_SANDBOX__E2B_TEMPLATE=code-interpreter   # 默认值
XAGENT_SANDBOX__E2B_BASE_URL=https://api.e2b.dev  # 官方云，可指自托管网关
XAGENT_SANDBOX__TIMEOUT_SECONDS=30
```

- 依赖：`pip install e2b-code-interpreter`（官方 SDK，优先）；
  未安装时自动退化到 E2B REST API（httpx：POST /sandboxes 创建 →
  POST /sandboxes/{id}/code 执行 → DELETE 销毁）。两者都不可用 → 明确中文报错，
  绝不静默降级到宿主机。
- 安全语义（与 L1 对齐）：一次性 sandbox（用后 kill/DELETE 销毁）、
  执行超时透传并销毁、输出 64K 截断、无 key 明确报错。
- 选型：SaaS 化 / 多租户高并发 / 不可信代码占比高的场景。每任务独立
  microVM，串扰面收敛到 E2B 平台；不占用宿主机 Docker 容量，天然水平扩展。

## 4. ⚠️ 网络隔离差异（L1 vs L2 的重要区别）

- **L1 docker 默认 `--network=none`**：容器无任何网络，防数据外泄。
- **L2 E2B 官方模板（含默认 `code-interpreter`）默认有外网访问**。
  需要禁网 / 出口白名单时，必须自建 E2B 模板（自定义 Dockerfile +
  防火墙规则），并用 `XAGENT_SANDBOX__E2B_TEMPLATE` 指向自建模板。
- 处理敏感数据的私有化部署：优先 L1；或 L2 + 自建禁网模板。

## 5. 选型速查

| 场景 | 推荐 |
|---|---|
| 本地演示 / 试点（不执行代码） | L0 disabled（默认，零配置） |
| 私有化 / 内网生产，需执行代码 | L1 docker |
| 云 SaaS / 多租户高并发 | L2 e2b（官方云） |
| 企业自托管云沙箱 | L2 e2b + `E2B_BASE_URL` 指自托管网关 + 自建模板 |
| 敏感数据 + 云部署 | L2 e2b + 自建禁网/白名单模板 |
