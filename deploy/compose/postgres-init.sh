#!/bin/bash
# Postgres 初始化：创建 compose 里附加服务所需数据库（POSTGRES_DB 已建默认库）
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE langfuse' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
    SELECT 'CREATE DATABASE contextforge' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'contextforge')\gexec
    SELECT 'CREATE DATABASE openfga' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'openfga')\gexec
EOSQL
