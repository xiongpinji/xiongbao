FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev curl git && rm -rf /var/lib/apt/lists/*

# 先复制元数据 + 源码（pyproject 引用 README，需一并复制）
COPY pyproject.toml README.md ./
COPY xagent ./xagent
# 装构建后端再装包（非 editable，避免 hatchling editable 元数据问题）
RUN pip install --upgrade pip hatchling && pip install ".[dev]" && \
    pip install "bcrypt==4.0.1" --force-reinstall --no-deps

# 移除 /app 下的源码副本：cwd 在 sys.path 中会遮蔽 site-packages 已安装包，
# 而 settings.py 按安装布局（parents[4]）推算项目根，/app/xagent 布局过浅会导致 IndexError。
RUN rm -rf /app/xagent

COPY migrations ./migrations
COPY alembic.ini ./

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "xagent.main:app", "--host", "0.0.0.0", "--port", "8000"]
