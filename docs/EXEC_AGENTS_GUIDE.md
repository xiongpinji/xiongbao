# 执行 Agent 真实接入指南

本文档说明 browser-use / UI-TARS / OpenHands 三类执行 agent 的真实部署与接入。
接口已在 adapters 层就绪，配置对应运行时后即启用。

## 1. 浏览器自动化（browser-use）

### 安装
```bash
pip install -e ".[browser]"   # browser-use + playwright
playwright install chromium    # 装浏览器
```

### 启用
无需额外配置——`get_browser_agent()` 检测到 `browser_use` 可导入即自动启用 `BrowserUseAgent`，
LLM 模型用 `XAGENT_LLM__DEFAULT_MODEL`。调用方式：编排中用 `browser_run` 工具，
或直接 `POST /api/v1/agents/run` 让 agent 自主决定调用。

### 验证脚本
```bash
python scripts/verify_browser_agent.py
```

## 2. 桌面 computer-use（UI-TARS）

### 部署 UI-TARS 模型服务
UI-TARS-desktop（Apache-2.0）可自部署为 HTTP 服务，或用兼容端点。

### 启用
```bash
export XAGENT_DESKTOP__UI_TARS_URL=http://<ui-tars-host>:<port>
```
`get_desktop_agent()` 检测到该环境变量即启用 `UITarsAgent`，否则 stub。

### 验证
```bash
python scripts/verify_desktop_agent.py
```

## 3. 自主编码（OpenHands Issue→PR）

### 部署 OpenHands
OpenHands（MIT）自托管运行时，暴露 issue-to-pr HTTP 接口。

### 启用
```bash
export XAGENT_CODING__OPENHANDS_URL=http://<openhands-host>:<port>
```
`get_coding_agent()` 检测到该环境变量即启用 `OpenHandsAgent`，否则 stub。

### 验证
```bash
python scripts/verify_coding_agent.py
```

## 安全注意事项

- 浏览器/桌面 agent 执行真实操作，建议在隔离环境（容器/VM）运行。
- OpenHands 执行代码合并，必须经审批门（`/workflows/{id}/approve/{step}`）通过后才合并。
- 所有执行 agent 调用受 RBAC + 租户隔离 + 审计链约束，与普通 agent 一致。
