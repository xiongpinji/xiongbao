# X-Agent 生产部署 Runbook

## 1. 前置检查

```bash
# 确认版本
git log --oneline -1
cat apps/api/xagent/__init__.py | grep __version__

# 确认 CI 全绿
gh run list --limit 5

# 确认备份
python scripts/backup.py --pg-url "$DATABASE_URL" --output ./backups
```

## 2. 部署步骤

### 2.1 滚动更新（Docker Compose）

```bash
cd deploy/compose

# 拉取最新镜像
docker compose pull api worker web

# 滚动重启（零停机）
docker compose up -d --no-deps api
docker compose exec api python -c "import httpx; r=httpx.get('http://localhost:8000/health'); print(r.json())"

# 确认健康后更新 worker
docker compose up -d --no-deps worker
```

### 2.2 数据库迁移

```bash
docker compose exec api python -m alembic upgrade head
```

### 2.3 前端更新

```bash
docker compose up -d --no-deps web
```

## 3. 验证清单

| 检查项 | 命令 | 预期 |
|--------|------|------|
| 存活探针 | `curl /health` | `{"status":"ok"}` |
| 就绪探针 | `curl /ready` | `{"ready":true}` |
| API 版本 | `curl /api/versions` | `{"current":"v1"}` |
| 指标端点 | `curl /metrics` | Prometheus 格式 |
| 登录流程 | `POST /api/v1/auth/login` | 200 + token |
| Grafana | 浏览器 :3002 | 仪表盘正常 |
| Prometheus | 浏览器 :9090 | 目标 UP |

## 4. 回滚方案

```bash
# 回滚到上一版本
docker compose pull api:previous-tag
docker compose up -d --no-deps api worker

# 数据库回滚（如需）
docker compose exec api python -m alembic downgrade -1

# 数据恢复（极端情况）
python scripts/restore.py --pg-url "$DATABASE_URL" --pg-backup ./backups/pg_backup_YYYYMMDD.sql
```

## 5. 紧急处理

### 5.1 服务不可用

```bash
# 查看日志
docker compose logs api --tail 100

# 重启
docker compose restart api

# 检查资源
docker stats --no-stream
```

### 5.2 数据库连接耗尽

```bash
# 查看连接数
docker compose exec postgres psql -U xagent -c "SELECT count(*) FROM pg_stat_activity;"

# 终止空闲连接
docker compose exec postgres psql -U xagent -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle' AND query_start < now() - interval '5 minutes';"
```

### 5.3 LLM 超时

```bash
# 检查 Ollama
curl http://localhost:11434/api/tags

# 切换模型（.env）
XAGENT_LLM__DEFAULT_MODEL=qwen3:4b
docker compose up -d --no-deps api
```

## 6. 监控 & 告警

- **Grafana**: http://localhost:3002 (admin/admin)
- **Prometheus**: http://localhost:9090
- **告警规则**: `deploy/grafana/alert-rules.yml`
- **SLO 定义**: `deploy/slo.yml`

## 7. 定期维护

| 频率 | 任务 |
|------|------|
| 每日 | 自动备份（cron: `0 3 * * * python scripts/backup.py`） |
| 每周 | 检查备份完整性 + 清理旧日志 |
| 每月 | SLO 复盘 + 错误预算消耗评估 |
| 每季 | 依赖升级 + 安全扫描 |
