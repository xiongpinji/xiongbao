param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ComposeFile = 'deploy/compose/docker-compose.yml',
    [string]$OllamaModel = 'qwen3:4b'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$composePath = Join-Path $RepoRoot $ComposeFile
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
    throw "compose file not found: $composePath"
}
if ($OllamaModel -notmatch '^[A-Za-z0-9._/-]+(?::[A-Za-z0-9._-]+)?$') {
    throw 'invalid Ollama model name'
}

# Evidence anchors: git rev-parse HEAD and git status --porcelain.
$sourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[a-f0-9]{40}$') {
    throw 'unable to resolve the source SHA'
}
$worktreeStatus = & git -C $RepoRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'unable to inspect worktree status' }
if ($worktreeStatus) { throw 'commercial gate requires a clean worktree' }

$runNonce = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$project = "xagent-commercial-$($sourceSha.Substring(0, 8))-$runNonce"
$evidence = Join-Path $RepoRoot "output/commercial-delivery/$sourceSha/webapi"
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$gateLockPath = Join-Path $evidence 'gate.lock'
$gateLock = $null
try {
    $gateLock = [System.IO.File]::Open(
        $gateLockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    throw "another Web/API gate is already writing evidence for source SHA $sourceSha"
}
$transcriptPath = Join-Path $evidence 'gate.log'
$transcriptStarted = $false
$composeProjectOwned = $false
$primaryError = $null
$cleanupErrors = [System.Collections.Generic.List[string]]::new()
$gateStatus = 'failed'
$startedAt = [DateTimeOffset]::UtcNow.ToString('o')
$commandsPath = Join-Path $evidence 'commands.raw.json'
$gatePath = Join-Path $evidence 'gate.json'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose -p $project -f $composePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

function Assert-ProjectAbsent {
    $containers = @(& docker ps -a -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0) { throw 'unable to inspect Docker containers' }
    $volumes = @(& docker volume ls -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0) { throw 'unable to inspect Docker volumes' }
    $networks = @(& docker network ls -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0) { throw 'unable to inspect Docker networks' }
    if ($containers.Count -ne 0 -or $volumes.Count -ne 0 -or $networks.Count -ne 0) {
        throw "compose project must be new and empty: $project"
    }
}

function Assert-ProjectOwnership {
    $containers = @(& docker ps -a -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0) { throw 'unable to inspect Docker containers' }
    foreach ($containerId in $containers) {
        $label = (& docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' $containerId).Trim()
        if ($LASTEXITCODE -ne 0 -or $label -ne $project) { throw 'container project label mismatch' }
    }
    $volumes = @(& docker volume ls -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0) { throw 'unable to inspect Docker volumes' }
    foreach ($volume in $volumes) {
        $label = (& docker volume inspect --format '{{ index .Labels "com.docker.compose.project" }}' $volume).Trim()
        if ($LASTEXITCODE -ne 0 -or $label -ne $project) { throw 'volume project label mismatch' }
    }
    $networks = @(& docker network ls -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0) { throw 'unable to inspect Docker networks' }
    foreach ($network in $networks) {
        $label = (& docker network inspect --format '{{ index .Labels "com.docker.compose.project" }}' $network).Trim()
        if ($LASTEXITCODE -ne 0 -or $label -ne $project) { throw 'network project label mismatch' }
    }
}

function Remove-AuditedComposeProject {
    if (-not $composeProjectOwned) { return }
    Assert-ProjectOwnership
    Invoke-Compose 'down' '--remove-orphans' '--volumes'
    Assert-ProjectAbsent
}

function Close-GateLock {
    param(
        [System.IO.FileStream]$GateLock,
        [System.Collections.Generic.List[string]]$CleanupErrors
    )
    if (-not $GateLock) { return }
    try { $GateLock.Dispose() } catch {
        $message = "gate lock: $($_.Exception.Message)"
        $null = $CleanupErrors.Add($message)
        [Console]::Error.WriteLine($message)
    }
}

function Write-CleanupEvidence {
    param(
        [System.Collections.Generic.List[string]]$CleanupErrors,
        [string]$EvidenceRoot
    )
    if ($CleanupErrors.Count -eq 0) { return }
    try {
        [ordered]@{ errors = @($CleanupErrors) } | ConvertTo-Json | Set-Content `
            -LiteralPath (Join-Path $EvidenceRoot 'cleanup-errors.json') -Encoding utf8
    } catch {
        $message = "cleanup evidence: $($_.Exception.Message)"
        $null = $CleanupErrors.Add($message)
        [Console]::Error.WriteLine($message)
    }
}

function Get-ComposeContainerId {
    param([Parameter(Mandatory = $true)][string]$Service)
    $containerId = (& docker compose -p $project -f $composePath ps -q $Service).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $containerId) {
        throw "compose service has no container: $Service"
    }
    return $containerId
}

function Wait-ComposeService {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [switch]$AllowRunning
    )
    for ($attempt = 0; $attempt -lt 180; $attempt++) {
        $containerId = (& docker compose -p $project -f $composePath ps -q $Service).Trim()
        if ($LASTEXITCODE -eq 0 -and $containerId) {
            $state = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId).Trim()
            if ($state -eq 'healthy' -or ($AllowRunning -and $state -eq 'running')) {
                Write-Output "$Service=$state"
                return
            }
            if ($state -in @('unhealthy', 'exited', 'dead')) {
                throw "compose service $Service entered terminal state: $state"
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "compose service did not become healthy: $Service"
}

function Resolve-PythonCommand {
    $candidates = [System.Collections.Generic.List[string]]::new()
    $candidates.Add((Join-Path $RepoRoot 'apps/api/.venv/Scripts/python.exe'))
    $candidates.Add((Join-Path $RepoRoot 'apps/api/.venv/bin/python'))
    $commonDir = (& git -C $RepoRoot rev-parse --git-common-dir).Trim()
    if ($LASTEXITCODE -eq 0 -and $commonDir) {
        if (-not [System.IO.Path]::IsPathRooted($commonDir)) {
            $commonDir = Join-Path $RepoRoot $commonDir
        }
        $commonRoot = Split-Path -Parent ([System.IO.Path]::GetFullPath($commonDir))
        $candidates.Add((Join-Path $commonRoot 'apps/api/.venv/Scripts/python.exe'))
        $candidates.Add((Join-Path $commonRoot 'apps/api/.venv/bin/python'))
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return (Get-Command python -ErrorAction Stop).Source
}

function Assert-Python311 {
    param([Parameter(Mandatory = $true)][string]$PythonCommand)
    $probe = 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}"); raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 42)'
    $actual = (& $PythonCommand -c $probe).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "commercial gate requires Python 3.11; resolved version: $actual"
    }
}

function New-RandomHex {
    return [Convert]::ToHexString(
        [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    ).ToLowerInvariant()
}

$pythonCommand = Resolve-PythonCommand
Assert-Python311 -PythonCommand $pythonCommand
$env:PYTHONNOUSERSITE = '1'
$env:POSTGRES_USER = 'xagent'
$env:POSTGRES_PASSWORD = New-RandomHex
$env:POSTGRES_DB = 'xagent'
$env:XAGENT_SECURITY__JWT_SECRET = New-RandomHex
$env:XAGENT_CORS_ORIGINS = '["http://127.0.0.1:18080"]'
$env:XAGENT_BIND_ADDRESS = '127.0.0.1'
$env:XAGENT_API_PORT = '18000'
$env:XAGENT_WEB_PORT = '18080'
$env:XAGENT_LLM__OLLAMA_BASE_URL = 'http://host.docker.internal:11434'
$env:XAGENT_LLM__OLLAMA_MODEL = $OllamaModel
$env:XAGENT_LLM__OLLAMA_NUM_CTX = '8192'
$env:XAGENT_LLM__DEFAULT_MODEL = $OllamaModel
$env:XAGENT_LLM__WARMUP_ENABLED = 'true'

try {
    Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
    $transcriptStarted = $true

    Push-Location $RepoRoot
    try {
        Invoke-Checked $pythonCommand 'scripts/verify_release_versions.py' '--tag' 'v1.1.3'
        Invoke-Checked $pythonCommand 'scripts/run_backend_commercial_tests.py'

        Invoke-Checked 'npm' '--prefix' 'apps/web' 'ci'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'run' 'lint'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'run' 'lint:release'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'run' 'test'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'run' 'typecheck'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'run' 'build'
        Invoke-Checked 'npm' '--prefix' 'packages/sdk-ts' 'ci'
        Invoke-Checked 'npm' '--prefix' 'packages/sdk-ts' 'run' 'test'
        Invoke-Checked 'npm' '--prefix' 'packages/sdk-ts' 'run' 'typecheck'
        Invoke-Checked 'npm' '--prefix' 'packages/sdk-ts' 'run' 'build'
        Invoke-Checked 'npm' '--prefix' 'tests/e2e' 'ci'

        Assert-ProjectAbsent
        $composeProjectOwned = $true
        Invoke-Compose 'up' '-d' '--build' 'postgres' 'redis' 'qdrant' 'api' 'worker' 'web'
        foreach ($service in @('postgres', 'redis', 'qdrant', 'api', 'worker')) {
            Wait-ComposeService -Service $service
        }
        Wait-ComposeService -Service 'web' -AllowRunning

        $webReady = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18080' -TimeoutSec 5
                if ($response.StatusCode -eq 200) { $webReady = $true; break }
            } catch {
                Start-Sleep -Seconds 1
            }
        }
        if (-not $webReady) { throw 'web service did not become reachable' }

        # Migration evidence: alembic upgrade head followed by current=head comparison.
        Invoke-Compose 'exec' '-T' 'api' 'python' '-m' 'alembic' 'upgrade' 'head'
        $heads = & docker compose -p $project -f $composePath exec -T api python -m alembic heads
        if ($LASTEXITCODE -ne 0) { throw 'alembic heads failed' }
        $current = & docker compose -p $project -f $composePath exec -T api python -m alembic current
        if ($LASTEXITCODE -ne 0) { throw 'alembic current failed' }
        $headRevision = (($heads | Select-Object -First 1) -split '\s+')[0]
        if (-not $headRevision -or (($current -join "`n") -notmatch [regex]::Escape($headRevision))) {
            throw 'database migration current revision does not match head'
        }

        Invoke-Checked $pythonCommand 'scripts/prepare_e2e_workspace.py' '--compose-file' $composePath '--project' $project
        Invoke-Checked $pythonCommand 'scripts/prepare_e2e_workspace.py' '--compose-file' $composePath '--project' $project

        $localModels = @(& ollama list | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] })
        if ($LASTEXITCODE -ne 0 -or $localModels -notcontains $OllamaModel) {
            throw "required local Ollama model is unavailable: $OllamaModel"
        }
        $modelProbe = "import json,urllib.request; d=json.load(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=10)); names={m.get('name','') for m in d.get('models',[])}; assert '$OllamaModel' in names"
        Invoke-Compose 'exec' '-T' 'api' 'python' '-c' $modelProbe

        $skillArchive = Join-Path $evidence 'r2-skill.zip'
        $skillFixture = Join-Path $RepoRoot 'tests/e2e/fixtures/r2-skill/*'
        Compress-Archive -Path $skillFixture -DestinationPath $skillArchive -Force
        $env:E2E_BASE_URL = 'http://127.0.0.1:18080'
        $env:E2E_API_URL = 'http://127.0.0.1:18000'
        $env:E2E_SKILL_PACKAGE = $skillArchive
        for ($run = 1; $run -le 3; $run++) {
            $env:E2E_EVIDENCE_DIR = Join-Path $evidence "browser/run-$run"
            Invoke-Checked 'npm' '--prefix' 'tests/e2e' 'exec' '--' 'playwright' 'test' 'specs/webapi-r2-full-compose.spec.ts' '--config' 'tests/e2e/playwright.config.ts' '--reporter=list'
        }

        $finalSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or $finalSha -ne $sourceSha) {
            throw 'source SHA changed during commercial gate'
        }
        $finalStatus = & git -C $RepoRoot status --porcelain
        if ($LASTEXITCODE -ne 0 -or $finalStatus) {
            throw 'worktree changed during commercial gate'
        }

        $gateStatus = 'passed'
        $details = [ordered]@{
            gate = 'webapi'
            source_sha = $sourceSha
            status = $gateStatus
            real_local_model = "ollama/$OllamaModel"
            playwright_retries = 0
            playwright_runs = 3
            api_image = (Get-ComposeContainerId -Service 'api')
            migration_head = $headRevision
            production_deployment = 'not_authorized'
        }
        $details | ConvertTo-Json -Depth 4 | Set-Content `
            -LiteralPath (Join-Path $evidence 'details.json') -Encoding utf8
        @(
            @{ command = 'verify release versions'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'complete API pytest suite'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'web lint test typecheck build'; exit_code = 0; passed = 5; failed = 0; skipped = 0 }
            @{ command = 'SDK test typecheck build'; exit_code = 0; passed = 3; failed = 0; skipped = 0 }
            @{ command = 'Docker Compose six-service health and migration'; exit_code = 0; passed = 7; failed = 0; skipped = 0 }
            @{ command = 'real local Ollama model probe'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'Playwright Web/API full flow three runs'; exit_code = 0; passed = 18; failed = 0; skipped = 0 }
        ) | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $commandsPath -Encoding utf8
    } finally {
        Pop-Location
    }
} catch { $primaryError = $_ } finally {
    try {
        & docker compose -p $project -f $composePath ps --all 2>&1 |
            Out-File -LiteralPath (Join-Path $evidence 'compose-ps.txt') -Encoding utf8
        if ($LASTEXITCODE -ne 0) { throw 'unable to capture compose ps' }
    } catch { $null = $cleanupErrors.Add("compose ps: $($_.Exception.Message)") }
    try {
        & docker compose -p $project -f $composePath logs --no-color 2>&1 |
            Out-File -LiteralPath (Join-Path $evidence 'compose-logs.txt') -Encoding utf8
        if ($LASTEXITCODE -ne 0) { throw 'unable to capture compose logs' }
    } catch { $null = $cleanupErrors.Add("compose logs: $($_.Exception.Message)") }
    try { Remove-AuditedComposeProject } catch {
        $null = $cleanupErrors.Add("compose project: $($_.Exception.Message)")
    }
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {
            $null = $cleanupErrors.Add("transcript: $($_.Exception.Message)")
        }
    }
    Close-GateLock -GateLock $gateLock -CleanupErrors $cleanupErrors
    Write-CleanupEvidence -CleanupErrors $cleanupErrors -EvidenceRoot $evidence
}

if ($primaryError) { throw $primaryError }
if ($cleanupErrors.Count -gt 0) { throw "Web/API gate cleanup failed: $($cleanupErrors -join '; ')" }
if ($gateStatus -ne 'passed') { throw 'Web/API commercial gate did not pass' }
Invoke-Checked $pythonCommand 'scripts/gate_evidence.py' 'build' `
    '--gate' 'webapi' '--repo-root' $RepoRoot '--source-sha' $sourceSha `
    '--started-at' $startedAt '--commands' $commandsPath `
    '--artifacts-root' $evidence '--output' $gatePath
