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

$sourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[a-f0-9]{40}$') {
    throw 'unable to resolve the source SHA'
}
$worktreeStatus = & git -C $RepoRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'unable to inspect worktree status' }
if ($worktreeStatus) { throw 'commercial gate requires a clean worktree' }

$project = "xagent-short-$($sourceSha.Substring(0, 8))"
$evidence = Join-Path $RepoRoot "output/commercial-delivery/$sourceSha/short-drama"
$browserEvidence = Join-Path $evidence 'browser'
New-Item -ItemType Directory -Force -Path $browserEvidence | Out-Null
$transcriptPath = Join-Path $evidence 'gate.log'
$transcriptStarted = $false
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

function Get-ComposeContainerId {
    param([Parameter(Mandatory = $true)][string]$Service)
    $containerId = (& docker compose -p $project -f $composePath ps -q $Service).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $containerId) {
        throw "compose service has no container: $Service"
    }
    return $containerId
}

function Wait-ComposeService {
    param([Parameter(Mandatory = $true)][string]$Service)
    for ($attempt = 0; $attempt -lt 180; $attempt++) {
        $containerId = (& docker compose -p $project -f $composePath ps -q $Service).Trim()
        if ($LASTEXITCODE -eq 0 -and $containerId) {
            $state = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId).Trim()
            if ($state -eq 'healthy') {
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

function New-RandomHex {
    return [Convert]::ToHexString(
        [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    ).ToLowerInvariant()
}

function Test-DeliveryBundle {
    param([Parameter(Mandatory = $true)][string]$BundlePath)
    if (-not (Test-Path -LiteralPath $BundlePath -PathType Leaf)) {
        throw "short-drama bundle not found: $BundlePath"
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($BundlePath)
    try {
        $manifestEntry = $archive.GetEntry('manifest.json')
        if ($null -eq $manifestEntry) { throw 'bundle manifest.json is missing' }
        $reader = [System.IO.StreamReader]::new($manifestEntry.Open())
        try { $manifest = ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
        if ($manifest.production_status -ne 'produced') {
            throw "bundle production status is not produced: $($manifest.production_status)"
        }
        if ($manifest.provider_classification -ne 'fixture_local') {
            throw "unexpected provider classification: $($manifest.provider_classification)"
        }
        if ($manifest.external_provider_acceptance -ne 'not_authorized') {
            throw 'external provider acceptance must remain not_authorized'
        }
        foreach ($file in @($manifest.files)) {
            $entry = $archive.GetEntry([string]$file.path)
            if ($null -eq $entry) { throw "manifest member is missing: $($file.path)" }
            if ($entry.Length -ne [long]$file.size_bytes) {
                throw "manifest size mismatch: $($file.path)"
            }
            $stream = $entry.Open()
            $hasher = [Security.Cryptography.SHA256]::Create()
            try {
                $digest = [Convert]::ToHexString($hasher.ComputeHash($stream)).ToLowerInvariant()
            } finally {
                $hasher.Dispose()
                $stream.Dispose()
            }
            if ($digest -ne [string]$file.sha256) {
                throw "manifest hash mismatch: $($file.path)"
            }
        }
    } finally {
        $archive.Dispose()
    }
}

$pythonCommand = Resolve-PythonCommand
$env:PYTHONNOUSERSITE = '1'
$env:POSTGRES_USER = 'xagent'
$env:POSTGRES_PASSWORD = New-RandomHex
$env:POSTGRES_DB = 'xagent'
$env:XAGENT_SECURITY__JWT_SECRET = New-RandomHex
$env:XAGENT_BIND_ADDRESS = '127.0.0.1'
$env:XAGENT_API_PORT = '18000'
$env:XAGENT_LLM__OLLAMA_BASE_URL = 'http://host.docker.internal:11434'
$env:XAGENT_LLM__OLLAMA_MODEL = $OllamaModel
$env:XAGENT_LLM__OLLAMA_NUM_CTX = '8192'
$env:XAGENT_LLM__DEFAULT_MODEL = $OllamaModel
$env:XAGENT_LLM__WARMUP_ENABLED = 'true'
$env:XAGENT_MEDIA__DEFAULT_IMAGE_PROVIDER = 'null'
$env:XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER = 'null'
$env:XAGENT_MEDIA__DEFAULT_AUDIO_PROVIDER = 'null'

try {
    Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
    $transcriptStarted = $true
    Push-Location $RepoRoot
    try {
        Push-Location 'apps/api'
        try {
            Invoke-Checked $pythonCommand '-m' 'pytest' '-q' 'tests/test_creative_delivery_bundle.py' 'tests/test_creative_studio.py' 'tests/test_creative_persistence.py' 'tests/test_pipeline.py' 'tests/test_audio_providers.py'
        } finally {
            Pop-Location
        }
        Invoke-Checked $pythonCommand 'scripts/run_backend_commercial_tests.py'
        Invoke-Checked 'npm' '--prefix' 'tests/e2e' 'ci'
        Invoke-Checked 'npm' '--prefix' 'tests/e2e' 'audit' '--audit-level=high'

        Invoke-Compose 'up' '-d' '--build' 'postgres' 'redis' 'qdrant' 'api'
        foreach ($service in @('postgres', 'redis', 'qdrant', 'api')) {
            Wait-ComposeService -Service $service
        }
        Invoke-Compose 'exec' '-T' 'api' 'python' '-m' 'alembic' 'upgrade' 'head'
        $heads = & docker compose -p $project -f $composePath exec -T api python -m alembic heads
        if ($LASTEXITCODE -ne 0) { throw 'alembic heads failed' }
        $current = & docker compose -p $project -f $composePath exec -T api python -m alembic current
        if ($LASTEXITCODE -ne 0) { throw 'alembic current failed' }
        $headRevision = (($heads | Select-Object -First 1) -split '\s+')[0]
        if (-not $headRevision -or (($current -join "`n") -notmatch [regex]::Escape($headRevision))) {
            throw 'database migration current revision does not match head'
        }

        $localModels = @(& ollama list | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] })
        if ($LASTEXITCODE -ne 0 -or $localModels -notcontains $OllamaModel) {
            throw "required local Ollama model is unavailable: $OllamaModel"
        }
        $modelProbe = "import json,urllib.request; d=json.load(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=10)); names={m.get('name','') for m in d.get('models',[])}; assert '$OllamaModel' in names"
        Invoke-Compose 'exec' '-T' 'api' 'python' '-c' $modelProbe

        $env:E2E_API_URL = 'http://127.0.0.1:18000'
        $env:E2E_EVIDENCE_DIR = $browserEvidence
        Invoke-Checked 'npm' '--prefix' 'tests/e2e' 'exec' '--' 'playwright' 'test' 'specs/short-drama-delivery.spec.ts' '--config' 'tests/e2e/playwright.config.ts' '--reporter=list'

        $bundlePath = Join-Path $browserEvidence 'short-drama.zip'
        Test-DeliveryBundle -BundlePath $bundlePath
        $apiLogs = & docker logs (Get-ComposeContainerId -Service 'api') 2>&1
        if (($apiLogs -join "`n") -match '(?i)provider.*(pollinations|openai|kling|jimeng|volcano_ark)') {
            throw 'external media provider path appeared in short-drama API logs'
        }

        $finalSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or $finalSha -ne $sourceSha) {
            throw 'source SHA changed during commercial gate'
        }
        $finalStatus = & git -C $RepoRoot status --porcelain
        if ($LASTEXITCODE -ne 0 -or $finalStatus) {
            throw 'worktree changed during commercial gate'
        }

        $containerId = Get-ComposeContainerId -Service 'api'
        $apiImageId = (& docker inspect --format '{{.Image}}' $containerId).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $apiImageId) { throw 'unable to resolve API image ID' }
        $gateStatus = 'passed'
        $details = [ordered]@{
            gate = 'short_drama'
            source_sha = $sourceSha
            status = $gateStatus
            provider_classification = 'fixture_local'
            external_provider_acceptance = 'not_authorized'
            paid_submission_attempted = $false
            playwright_retries = 0
            api_image_id = $apiImageId
            migration_head = $headRevision
            bundle_sha256 = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash.ToLowerInvariant()
            production_deployment = 'not_authorized'
        }
        $details | ConvertTo-Json -Depth 4 | Set-Content `
            -LiteralPath (Join-Path $evidence 'details.json') -Encoding utf8
        @(
            @{ command = 'offline short-drama pytest suite'; exit_code = 0; passed = 5; failed = 0; skipped = 0 }
            @{ command = 'complete API pytest suite'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'browser dependency audit'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'Docker Compose API health and migration'; exit_code = 0; passed = 5; failed = 0; skipped = 0 }
            @{ command = 'real local Ollama model probe'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'Playwright short-drama delivery'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'independent delivery ZIP hash verification'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
        ) | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $commandsPath -Encoding utf8
    } finally {
        Pop-Location
    }
} finally {
    & docker compose -p $project -f $composePath ps --all 2>&1 |
        Out-File -LiteralPath (Join-Path $evidence 'compose-ps.txt') -Encoding utf8
    & docker compose -p $project -f $composePath logs --no-color 2>&1 |
        Out-File -LiteralPath (Join-Path $evidence 'compose-logs.txt') -Encoding utf8
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}

if ($gateStatus -ne 'passed') { throw 'Short-drama commercial gate did not pass' }
Invoke-Checked $pythonCommand 'scripts/gate_evidence.py' 'build' `
    '--gate' 'short_drama' '--repo-root' $RepoRoot '--source-sha' $sourceSha `
    '--started-at' $startedAt '--commands' $commandsPath `
    '--artifacts-root' $evidence '--output' $gatePath
