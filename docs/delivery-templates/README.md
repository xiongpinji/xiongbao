# 交付模板包索引（P3 商业复制 v1）

> 用途：商业复制阶段的模板入口。与 DELIVERY_MATERIALS_INDEX_V1（本次交付的成套材料）的关系：**那里是"这一次的交付物"，这里是"复制下一次的模板"**。

| 模板 | 入口 | 用途 |
|---|---|---|
| 标准试点包 | [PILOT_PACK_TEMPLATE.md](PILOT_PACK_TEMPLATE.md) | 新试点的定义/进入条件/验收/退出 |
| 标准升级包 | [UPGRADE_PACK_TEMPLATE.md](UPGRADE_PACK_TEMPLATE.md) | 版本 A→B 升级与回滚纪律 |
| 标准恢复包 | [RECOVERY_PACK_TEMPLATE.md](RECOVERY_PACK_TEMPLATE.md) | 灾难恢复动作集与演练纪律 |
| 标准角色包 | [ROLE_PACK.md](ROLE_PACK.md) | TL/QA/DevOps/Owner 职责矩阵与人力模式 |
| 行业变体指南 | [INDUSTRY_VARIANT_GUIDE.md](INDUSTRY_VARIANT_GUIDE.md) | 行业/场景变体的裁剪矩阵与验收 |
| 研发效能变体包 v1 | [variants/dev-effectiveness/](variants/dev-effectiveness/README.md) | Codex 对标场景：裁剪决策 + 口径页 + 演示脚本 |

使用顺序建议：角色包定人 → 试点包开张 → 升级包迭代 → 恢复包兜底；做行业复制时先读变体指南。
