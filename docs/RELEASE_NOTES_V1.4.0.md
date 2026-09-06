# X-Agent v1.4.0 发布说明

**发布日期：2026-09-06**

## 主题：设置界面全面扁平化 —— 对齐 ZCode / Codex 终端级视觉规范

本版本将全部设置界面从"卡片堆砌"重构为 ZCode / Codex 风格的扁平行式布局，消除视觉噪音，信息密度更高，操作路径更短。

## 界面变更

### 新增扁平设计原语（`settings/ui.tsx`）

- `SectionHeader`：等宽大写标题 + 发丝分隔线（`border-white/[0.05]`）+ 右侧操作区
- `Row`：左标签右控件的标准行，行间以细分隔线分区，取代圆角卡片容器
- `StatLine`：内联等宽统计行（支持 ok/warn/muted 语义色），取代统计卡片网格
- `GroupLabel` / ghost 按钮变体（primary/ok/warn/danger）/ flat 等宽输入框

### 8 个设置组件去卡片化

| 组件 | 变更 |
| --- | --- |
| 常规 General | Token 管理改为扁平行式；SectionTitle 全局改为 mono uppercase |
| 模型 Model | 表单改为左标签右输入框的扁平双列行布局 |
| MCP 服务 | 服务条目从卡片改为细分隔行 + ghost 操作 |
| 知识 Knowledge | 文档列表与配置区扁平化 |
| 技能 Skills | 统计卡片 → 内联统计行；技能卡 → 扁平行（`v1 · 来源 · 状态` mono 徽章 + `trigger:/uses:/success:/tools:` 元数据 + ghost 操作按钮） |
| 团队 Team | 租户/用户/API Key 三卡片 → StatLine 内联统计 |
| 用量 UsageStats | 统计网格 → StatLine |
| Webhook | 卡片容器 → 扁平行分组 |

## 工程变更

- 前端 lint 豁免指纹刷新（react_compiler_migration 组 sha256 更新，数量 89/10 不变）
- 全部门禁通过：typecheck / eslint 0 errors / lint:release 豁免门禁 / 单元测试（CI 同款入口）
- Playwright 1440×900 三区截图视觉验收（技能 / 团队 / 模型）：确认无卡片容器残留

## 升级说明

- 纯前端视觉重构，无 API / 数据 / 配置变更，可直接滚动升级
- 镜像：`ghcr.io/xiongpinji/xagent-web:1.4.0` / `ghcr.io/xiongpinji/xagent-api:1.4.0`

## 完整变更

- PR #34：设置界面去卡片化：统一 ZCode/Codex 扁平行式风格
