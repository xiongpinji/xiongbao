# X-Agent v1.3.2 发布说明

> 发布日期：2026-09-06 · 上一版本：v1.3.1（同日）
> 本版主题：**蒸馏技能默认停用（人工启用门）——用户全功能实测发现的技能污染根治**

---

## 一、背景：全功能实测发现「掺词绕过」

v1.3.1 的全泛词门禁上线后，用户视角全功能实测（设置→技能分区）发现新蒸馏技能
「HelloFileVerify」（触发 `创建|Python|Hello Agent|读取|确认`）——**掺一个具体词即绕过**
全泛词检查，且其提示绑定死内容（print Hello Agent），匹配到的创建类任务仍会被污染。
根因不在词典，在于**自动蒸馏入库即参与注入**这一机制本身。

## 二、修复：蒸馏技能启用门（机制级根治）

| 变更 | 说明 |
|---|---|
| `Skill.enabled` 字段 | 新增独立启用态（与 retired 正交）；`is_active = enabled and not retired`；旧 JSON 无该字段默认启用（存量技能行为不变） |
| 蒸馏入库默认停用 | auto_distill / failure_distill 产出的技能 `enabled=False`，**入库不注入**，等待人工评估 |
| 匹配注入过滤 | `match()` / `build_prompt_injection()` 跳过未启用技能 |
| 生命周期 API | `POST /skills/{id}/enable`、`POST /skills/{id}/disable`（system:manage 权限） |
| 设置页 UI | 技能卡新增「待启用」徽标 + 启用/停用按钮（含说明 tooltip） |

这同时是对标 Hermes「人工 PR 门禁」的机制对齐：自动学习 → 人工审核 → 生效。

## 三、测试

- `test_skill_anti_poison.py` 扩至 19 项：蒸馏默认停用/启用门控注入/手工默认启用/旧 JSON 兼容
- `test_skill_distill_gate.py` 契约更新：入库即 match → 入库停用+启用后 match
- 技能相关套件 56 项全过；ruff 基线计数不变；mypy 干净；前端 54 项单测全绿

## 四、升级与兼容

- 无迁移；存量技能（含已启用的手工/导入技能）行为不变
- 此后自动蒸馏出的技能会在设置→技能区显示「待启用」，人工点「启用」后才开始注入
