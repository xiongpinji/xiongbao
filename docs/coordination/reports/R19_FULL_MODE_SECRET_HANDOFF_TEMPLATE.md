# R19 Full-Mode Secret Handoff Template

> Date: 2026-07-07
> Owner: Codex
> Scope: no-secret handoff template for R4 full-mode rehearsal recovery.

## Purpose

This template gives the environment / release owner one place to provide full-mode configuration readiness evidence without exposing secret values in Git, chat, screenshots, or delivery reports.

It is an input to R4. It is not proof that R4 target-environment rehearsal has completed.

## Boundaries

- Do not paste real secret values into this file.
- Do not commit `.env`, `.env.rehearsal`, provider keys, passwords, private URLs, or token screenshots.
- Do not use lite/dev default accounts as full-mode rehearsal evidence.
- Do not mark R4, R5, R16, U2, or R19 as release-complete from this template alone.

## Candidate Binding

| Field | Required value / evidence |
|---|---|
| Candidate branch | `<branch name>` |
| Candidate commit | `<commit sha>` |
| Remote CI run | `<CI run URL or run id>` |
| Web build artifact | `<apps/web/dist build timestamp and command output>` |
| R18 freshness decision | `<new candidate required / PR #6 d59faa3 only / other>` |
| Handoff owner | `<name or role>` |
| Handoff timestamp | `<ISO timestamp>` |

## Secret And Config Handoff

Use secret-store references or ticket IDs, not values.

| Variable / item | Required for full mode | Source reference, not value | Validation evidence |
|---|---|---|---|
| `XAGENT_MODE` | `full` | `deploy/compose/.env.rehearsal` or platform env | Config dump shows `full` without exposing secrets |
| `XAGENT_CORS_ORIGINS` | Target web origin only; no wildcard | Config/ticket reference | Reviewer confirms allowed origin list |
| `XAGENT_SECURITY__JWT_SECRET` | 32+ chars random secret | Secret manager path / CI secret name | `docker compose --env-file .env.rehearsal config --quiet` exits 0 |
| `XAGENT_SECURITY__REQUIRE_AUTH` | `true` | Config/ticket reference | Runtime config review confirms auth required |
| `LANGFUSE_NEXTAUTH_SECRET` | Random secret | Secret manager path / CI secret name | Compose config exits 0 |
| `LANGFUSE_SALT` | Random secret | Secret manager path / CI secret name | Compose config exits 0 |
| `LANGFUSE_INIT_USER_PASSWORD` | Strong one-time bootstrap password | Secret manager path / bootstrap ticket | Langfuse bootstrap/login evidence path |
| `POSTGRES_PASSWORD` | Strong password or managed DB credential | Secret manager path / DB credential ref | DB connection check evidence |
| `XAGENT_DB__URL` | Target Postgres URL | Secret/config reference | `/ready` DB component is healthy |
| `XAGENT_CACHE__REDIS_URL` | Target Redis URL | Secret/config reference | `/ready` cache component is healthy |
| `XAGENT_MEMORY__QDRANT_URL` | Target Qdrant URL | Config reference | `/ready` vector-store component is healthy |
| `XAGENT_OBSERVABILITY__LANGFUSE_PUBLIC_KEY` | Langfuse project public key if tracing enabled | Secret/config reference | Trace appears in Langfuse or explicit disabled decision |
| `XAGENT_OBSERVABILITY__LANGFUSE_SECRET_KEY` | Langfuse project secret key if tracing enabled | Secret manager path / CI secret name | Trace appears in Langfuse or explicit disabled decision |
| `XAGENT_LLM__PROXY_URL` | Required if using LiteLLM path | Config reference | Test prompt or health evidence |
| `XAGENT_LLM__PROXY_API_KEY` | Required if LiteLLM proxy auth is enabled | Secret manager path / CI secret name | Test prompt succeeds |
| `XAGENT_LLM__OLLAMA_BASE_URL` / `XAGENT_LLM__OLLAMA_MODEL` | Required if using Ollama path | Host/network evidence | Model availability evidence |
| Provider API key such as `XAGENT_LLM__OPENAI_API_KEY` or `XAGENT_LLM__DEEPSEEK_API_KEY` | Required if using direct provider path | Secret manager path / provider vault ref | Test prompt succeeds; no key in logs |
| `E2E_USERNAME` / `E2E_PASSWORD` | Full-mode test account | Account source ticket + secret reference | Login and Playwright evidence |

## Full-Mode Account Source

Choose one and attach proof path:

| Option | Owner-filled evidence |
|---|---|
| Keycloak / OIDC user source | `<realm/client/user setup evidence path>` |
| DB / explicit initialization flow | `<migration/init command and result path>` |
| Existing staging user | `<user approval and rotation evidence path>` |

Required account evidence:

- Account is not a lite/dev fallback.
- Account has the role needed for Run Console, workflows, settings, and the R4 smoke path.
- Password or login token is only referenced through a secret manager path.
- `E2E_USERNAME` and `E2E_PASSWORD` map to the same full-mode account source.

## Port And Dependency Handoff

| Service | Default port | Owner-filled status |
|---|---:|---|
| Postgres | 5432 | `<free / remapped to ... / managed>` |
| Redis | 6379 | `<free / remapped to ... / managed>` |
| Qdrant HTTP | 6333 | `<free / remapped to ... / managed>` |
| Qdrant gRPC | 6334 | `<free / remapped to ... / managed>` |
| Langfuse | 3001 | `<free / remapped to ... / disabled with reason>` |
| LiteLLM | 4000 | `<free / remapped to ... / not used>` |
| ContextForge | 8080 | `<free / remapped to ... / not used>` |
| OpenFGA | 8081 | `<free / remapped to ... / not used>` |
| API | 8000 | `<free / remapped to ...>` |
| Web | 3000 | `<free / remapped to ...>` |

Port preflight command:

```powershell
Get-NetTCPConnection -LocalPort 5432,6379,6333,6334,3001,4000,8080,8081,8000,3000 -ErrorAction SilentlyContinue
```

## R4 Recovery Evidence Checklist

The R4 executor should attach command output paths for each item.

| Step | Evidence required |
|---|---|
| Candidate freeze | Branch/commit and R18 freshness decision |
| Env generation | `.env.rehearsal` generated from `.env.example`; values not printed |
| Compose config | `docker compose --env-file .env.rehearsal config --quiet` exits 0 |
| Web build | `npm ci` and `npm run build` outputs for current candidate |
| Dependency startup | `docker compose --env-file .env.rehearsal up -d --build postgres redis qdrant litellm langfuse contextforge openfga` and `ps` output |
| App startup | `docker compose --env-file .env.rehearsal up -d --build api worker web` and `ps` output |
| Logs | `api`, `worker`, `web`, and dependency logs paths |
| Health | `/health`, `/ready`, and web root smoke outputs |
| Auth | Full-mode login proof for the explicit account |
| LLM | One successful LLM path proof, or explicit release-owner waiver |
| E2E | `creative-smoke` and optional `full-flow` output paths |
| Backup / migration | Alembic current/upgrade output and DB backup path if applicable |

## Reviewer Checklist

- The handoff contains no secret values.
- Every required secret has a source reference and validation evidence field.
- Full-mode account source is explicit.
- At least one LLM path is selected and testable.
- Ports are either free, remapped with evidence, or replaced by managed services.
- R4 remains BLOCKED until these fields are filled and the rehearsal commands actually run.
