# 标准升级包模板（P3 商业复制）

> 用途：从版本 A 升级到版本 B 的标准动作集。依据 RELEASE_RUNBOOK_V1 + alembic 迁移纪律。

## 1. 升级对象

| 项 | 内容 |
|---|---|
| 从版本 | `<tag/commit>` |
| 到版本 | `<tag/commit + CI run id>` |
| 环境 | `<试点/生产；compose/helm>` |
| 数据 | `<SQLite/Postgres；数据量级>` |

## 2. 升级前检查

- [ ] 目标版本 CI 全绿
- [ ] 备份完成（DB dump + 数据目录；恢复演练在本周期内做过）
- [ ] `alembic current` 与目标 head 的迁移路径已审阅（含 SQLite/Postgres 双方言）
- [ ] 配置 diff 已审阅（settings 新增项/废弃项；secretRef 引用可达）
- [ ] 回滚镜像/包已就位

## 3. 执行步骤

1. 公告与冻结写入（如适用）
2. 备份 → 记录校验值
3. 部署新版本（compose pull/up 或 helm upgrade）
4. `alembic upgrade head`（如需）
5. smoke：`/health` `/ready` 登录 主链路一发
6. 发布后观测（post_deploy_summary.py，≥30min 窗口）

## 4. 回滚触发与动作

| 触发 | 动作 |
|---|---|
| smoke 任一失败 | 立即回滚到备份版本 + `alembic downgrade`（如迁移过） |
| 观测窗 5xx 率 > 基线 2× | ROLLBACK_RECOMMENDED 评估，30min 内决策 |

## 5. 归档

- [ ] 升级记录（时间/版本/操作人/观测结论）
- [ ] 备份位置与校验值
- [ ] 遗留问题清单
