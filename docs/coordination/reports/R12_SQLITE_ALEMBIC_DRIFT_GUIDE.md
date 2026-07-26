# R12 SQLite/Alembic 漂移诊断与复验指南

- 任务包：R12 SQLite/Alembic 漂移诊断与复验指南
- 交付人：Codex
- 日期：2026-07-06
- 工作树：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 范围：本地 SQLite / Alembic revision 漂移诊断、影响范围、稳定复验办法与处置建议；不修改迁移脚本，不迁移用户历史数据。

## 结论

- 当前仓库 Alembic 迁移图只有 `0001 -> 0005`，`0005` 是 head。
- fresh SQLite DB 可以稳定执行 `alembic upgrade head`，并生成 `evidence_records`。
- R3 使用的 fresh `r3-e2e.db` 当前 `alembic_version=0005`，且存在 `evidence_records`。
- 现有本地默认库 `apps/api/xagent.db` 当前 `alembic_version=0007`，但当前仓库没有 revision `0007`；该库缺少 `evidence_records`。
- 因此，漂移复现条件是“历史本地 SQLite 文件保留了当前迁移图已不存在的 `0007` revision 指针”，不是 fresh migration 或当前迁移脚本本身失败。

## 证据

### 迁移图

命令：

```powershell
$env:XAGENT_DB__URL='sqlite+aiosqlite:///./r12-fresh.db'
.\.venv\Scripts\python.exe -X utf8 -m alembic heads
.\.venv\Scripts\python.exe -X utf8 -m alembic history --verbose
```

结果：

- `alembic heads`：`0005 (head)`
- `alembic history --verbose`：仅 `0001 initial schema` 与 `0005 unified run spine`

### fresh SQLite

命令：

```powershell
Remove-Item .\r12-fresh.db -Force -ErrorAction SilentlyContinue
$env:XAGENT_DB__URL='sqlite+aiosqlite:///./r12-fresh.db'
.\.venv\Scripts\python.exe -X utf8 -m alembic current
.\.venv\Scripts\python.exe -X utf8 -m alembic upgrade head
.\.venv\Scripts\python.exe -X utf8 -m alembic current
```

结果：

- 迁移执行 `base -> 0001 -> 0005`
- `alembic_version=0005`
- 表包含 `agent_tasks`、`artifacts`、`evidence_records`、`workflow_runs` 等运行主链表

### 现有本地默认库

检查对象：`apps/api/xagent.db`

结果：

- `alembic_version=0007`
- 表包含 `agent_tasks`、`artifacts`、`canvases`、`creative_productions`、`creative_timelines`、`media_tasks` 等历史表
- 缺少 `evidence_records`
- 执行 `alembic current` 或 `alembic upgrade head` 均失败：`Can't locate revision identified by '0007'`

### 伪造漂移库复现

命令：创建仅含 `alembic_version=0007` 的临时 `r12-drift-0007.db` 后执行：

```powershell
$env:XAGENT_DB__URL='sqlite+aiosqlite:///./r12-drift-0007.db'
.\.venv\Scripts\python.exe -X utf8 -m alembic current
.\.venv\Scripts\python.exe -X utf8 -m alembic upgrade head
```

结果：

- 两条命令均失败：`Can't locate revision identified by '0007'`

## 影响范围

受影响：

- 复用历史 `apps/api/xagent.db` 或其他 `alembic_version=0007` 的本地 SQLite 文件。
- 依赖 `evidence_records` 的 Run Console / runtime evidence 读取路径；在缺表库上会出现 `no such table: evidence_records` 类 warning。
- 使用 `xagent migrate` 或 `python -m alembic upgrade head` 针对该旧库执行迁移时，会因为未知 revision `0007` 失败。

不受影响：

- fresh SQLite DB。
- R3/R10 使用的 fresh 临时库路径。
- 当前迁移脚本 `0001 -> 0005` 自身。
- 未复用旧 SQLite 文件的目标环境。

## 稳定复验办法

### 判断当前 DB 是否漂移

```powershell
cd apps/api
@'
import sqlite3
from pathlib import Path
db = Path("xagent.db")
with sqlite3.connect(db) as conn:
    tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
    version = list(conn.execute("select version_num from alembic_version")) if "alembic_version" in tables else []
    print("version=", version)
    print("has_evidence_records=", "evidence_records" in tables)
'@ | .\.venv\Scripts\python.exe -X utf8 -
```

漂移判断：

- `version=[('0007',)]` 且当前仓库 `alembic heads` 为 `0005`。
- 或 `alembic current` 报 `Can't locate revision identified by '0007'`。

### fresh DB 复验

```powershell
cd apps/api
Remove-Item .\verify-fresh.db -Force -ErrorAction SilentlyContinue
$env:XAGENT_DB__URL='sqlite+aiosqlite:///./verify-fresh.db'
.\.venv\Scripts\python.exe -X utf8 -m alembic upgrade head
.\.venv\Scripts\python.exe -X utf8 -m alembic current
```

期望：

- `upgrade head` 退出码 0。
- `current` 输出 `0005 (head)`。
- SQLite 表包含 `evidence_records`。

## 处置建议

### 本地 dev / 无需保留数据

推荐处理：

1. 停止 API / worker。
2. 备份或删除旧 `apps/api/xagent.db`。
3. 设置新的 `XAGENT_DB__URL`，或让应用重新创建 fresh SQLite。
4. 执行 `alembic upgrade head` 或 `xagent migrate`。

这是最稳妥路径，因为旧库 revision 指针与当前迁移图不一致。

### 需要保留历史数据

不要直接 `stamp head` 掩盖漂移。应先：

1. 备份旧库。
2. 导出需要保留的业务表。
3. 用当前迁移图创建 fresh DB。
4. 编写一次性数据迁移脚本，将旧数据导入 fresh DB。
5. 跑 Run Console / creative smoke / evidence 读取路径验证。

### 目标环境

- 发布演练不得复用带未知 revision 的历史 SQLite 文件。
- 若目标环境 `alembic current` 不是当前仓库 head，应先停机备份并形成人工迁移方案。
- 对 Postgres / staging / prod，应以 `alembic current`、`alembic heads` 和一次 `upgrade head` 结果作为 R4 环境演练证据。

## 是否需要正式修复

- 不需要为了 fresh DB 修改当前 `0001 -> 0005` 迁移脚本。
- 需要在发布 / 运维层面明确：旧本地 SQLite `0007` 属于历史漂移库，不应作为当前发布证据。
- 若必须兼容旧库，应另拆“历史 SQLite 数据升级 / 合并迁移”任务，明确旧 `0007` 对应的表结构来源和数据保留范围。

