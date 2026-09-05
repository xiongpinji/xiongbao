param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$sourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[a-f0-9]{40}$') {
    throw 'unable to resolve the source SHA'
}
$worktreeStatus = & git -C $RepoRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'unable to inspect worktree status' }
if ($worktreeStatus) { throw 'commercial kernel gate requires a clean worktree' }

$evidence = Join-Path $RepoRoot "output/commercial-delivery/$sourceSha/kernel"
$gatePath = Join-Path $evidence 'gate.json'
$commandsPath = Join-Path $evidence 'commands.raw.json'
$transcriptPath = Join-Path $evidence 'gate.log'
$startedAt = [DateTimeOffset]::UtcNow.ToString('o')
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$transcriptStarted = $false
$gateStatus = 'failed'
$temporaryRoot = $null
$temporaryEnv = $null
$temporaryReport = $null

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

function Resolve-PythonCommand {
    $candidates = [System.Collections.Generic.List[string]]::new()
    $candidates.Add((Join-Path $RepoRoot 'apps/api/.venv/Scripts/python.exe'))
    $commonDir = (& git -C $RepoRoot rev-parse --git-common-dir).Trim()
    if ($LASTEXITCODE -eq 0 -and $commonDir) {
        if (-not [System.IO.Path]::IsPathRooted($commonDir)) {
            $commonDir = Join-Path $RepoRoot $commonDir
        }
        $commonRoot = Split-Path -Parent ([System.IO.Path]::GetFullPath($commonDir))
        $candidates.Add((Join-Path $commonRoot 'apps/api/.venv/Scripts/python.exe'))
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

$pythonCommand = Resolve-PythonCommand
Assert-Python311 -PythonCommand $pythonCommand
$env:PYTHONNOUSERSITE = '1'
$currentApiPath = Join-Path $RepoRoot 'apps/api'
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = $currentApiPath + [System.IO.Path]::PathSeparator + $env:PYTHONPATH
} else {
    $env:PYTHONPATH = $currentApiPath
}
try {
    Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
    $transcriptStarted = $true
    Push-Location $RepoRoot
    try {
        Invoke-Checked $pythonCommand 'scripts/verify_release_versions.py' '--tag' 'v1.1.3'
        Invoke-Checked $pythonCommand '-m' 'pytest' '-q' `
            'tests/release/test_release_version_gate.py' `
            'tests/release/test_r2_preflight.py' `
            'tests/release/test_migrate_llm_overrides.py' `
            'tests/release/test_container_contract.py' `
            'tests/release/test_helm_image_contract.py' `
            'tests/security/test_scan.py' `
            'apps/api/tests/test_secure_json.py' `
            'apps/api/tests/test_llm_config_security.py'

        $temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) `
            ("xagent-kernel-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
        Copy-Item -LiteralPath 'deploy/compose/r2.env.example' `
            -Destination (Join-Path $temporaryRoot 'r2.env.example')
        $temporaryEnv = Join-Path $temporaryRoot 'r2.env.local'
        $temporaryReport = Join-Path $temporaryRoot 'preflight.json'
        Invoke-Checked $pythonCommand 'scripts/r2_preflight.py' `
            '--init-env' $temporaryEnv '--output' $temporaryReport
        if (-not (Test-Path -LiteralPath $temporaryEnv -PathType Leaf)) {
            throw 'Windows preflight did not create its isolated output'
        }

        Invoke-Checked 'pip-audit' '-r' 'apps/api/requirements.lock' '--no-deps' '--disable-pip'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'audit' '--omit=dev' '--audit-level=high'
        Invoke-Checked 'npm' '--prefix' 'packages/sdk-ts' 'audit' '--omit=dev' '--audit-level=high'
        Invoke-Checked 'cargo' 'audit' '--file' 'apps/desktop/Cargo.lock'
        Invoke-Checked 'helm' 'template' 'xagent' 'deploy/helm' `
            '--set' 'image.digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' `
            '--set' 'web.image.digest=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'

        $imageTag = "xagent-api:commercial-kernel-$($sourceSha.Substring(0, 8))"
        Invoke-Checked 'docker' 'build' '-f' 'apps/api/Dockerfile' '-t' $imageTag 'apps/api'
        $containerIdentity = (& docker run --rm --entrypoint id $imageTag).Trim()
        if ($LASTEXITCODE -ne 0 -or $containerIdentity -notmatch 'uid=10001') {
            throw 'commercial API image did not run as uid 10001'
        }

        $finalSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
        $finalStatus = & git -C $RepoRoot status --porcelain
        if ($LASTEXITCODE -ne 0 -or $finalSha -ne $sourceSha -or $finalStatus) {
            throw 'source SHA or worktree changed during commercial kernel gate'
        }

        $gateStatus = 'passed'
        [ordered]@{
            gate = 'commercial_kernel'
            source_sha = $sourceSha
            status = $gateStatus
            container_identity = $containerIdentity
            secret_values_recorded = $false
            release = 'not_authorized'
        } | ConvertTo-Json -Depth 4 | Set-Content `
            -LiteralPath (Join-Path $evidence 'details.json') -Encoding utf8
        @(
            @{ command = 'verify release versions'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'kernel pytest contracts'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'Windows Unicode preflight'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'Python locked dependency audit'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'Node locked dependency audits'; exit_code = 0; passed = 2; failed = 0; skipped = 0 }
            @{ command = 'Rust locked dependency audit'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'Helm immutable digest render'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'non-root API container build and run'; exit_code = 0; passed = 2; failed = 0; skipped = 0 }
        ) | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $commandsPath -Encoding utf8
    } finally {
        Pop-Location
    }
} finally {
    if ($temporaryEnv -and (Test-Path -LiteralPath $temporaryEnv -PathType Leaf)) {
        Remove-Item -LiteralPath $temporaryEnv -Force
    }
    if ($temporaryReport -and (Test-Path -LiteralPath $temporaryReport -PathType Leaf)) {
        Remove-Item -LiteralPath $temporaryReport -Force
    }
    if ($temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot -PathType Container)) {
        $temporaryTemplate = Join-Path $temporaryRoot 'r2.env.example'
        if (Test-Path -LiteralPath $temporaryTemplate -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryTemplate -Force
        }
        Remove-Item -LiteralPath $temporaryRoot -Force
    }
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}

if ($gateStatus -ne 'passed') { throw 'commercial kernel gate did not pass' }
Invoke-Checked $pythonCommand 'scripts/gate_evidence.py' 'build' `
    '--gate' 'commercial_kernel' '--repo-root' $RepoRoot `
    '--source-sha' $sourceSha '--started-at' $startedAt `
    '--commands' $commandsPath '--artifacts-root' $evidence '--output' $gatePath
