# X-Agent Desktop（Tauri 2.x）

桌面壳，加载 `../web/dist`（React 工作台）。

## 前置

- Rust toolchain + Tauri 2 prerequisites
- 先 `cd ../web && npm install && npm run build` 产出 `dist/`

## 开发

```bash
cargo tauri dev
```

## 打包

```bash
cargo tauri build   # 产出 MSI / NSIS 安装包
```

## 说明

- 前端主链路：浏览器 HTTP/SSE 直连后端 `localhost:8000`（CSP 已放行）。
- 备用：`call_backend_api` Rust 命令做带鉴权转发（`invoke` 调用）。
- lite 模式后端可匿名；full 模式需在 Web 设置页填 token。
