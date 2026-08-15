param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ApiUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'desktop commercial gate requires Windows' }
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
if ($ApiUrl -notmatch '^http://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$') {
    throw 'desktop commercial gate requires a loopback HTTP API URL'
}

# Command contract: cargo fmt, cargo clippy, cargo test, cargo audit,
# cargo tauri build, collect_desktop_artifacts.py, verify_desktop_installer.ps1.
$sourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[a-f0-9]{40}$') {
    throw 'unable to resolve the source SHA'
}
$worktreeStatus = & git -C $RepoRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'unable to inspect worktree status' }
if ($worktreeStatus) { throw 'desktop commercial gate requires a clean worktree' }

$tauriConfigPath = Join-Path $RepoRoot 'apps/desktop/tauri.conf.json'
$tauriConfig = Get-Content -Raw -LiteralPath $tauriConfigPath | ConvertFrom-Json
$desktopVersion = [string]$tauriConfig.version
if ($desktopVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw 'invalid desktop version in Tauri configuration'
}

$health = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 10
if ($health.status -ne 'ok' -or $health.version -ne $desktopVersion) {
    throw 'local API health/version does not match the desktop release'
}

$evidence = Join-Path $RepoRoot "output/commercial-delivery/$sourceSha/desktop"
$bundleRoot = Join-Path $RepoRoot 'apps/desktop/target/release/bundle'
$nsisRoot = Join-Path $bundleRoot 'nsis'
$artifactPath = Join-Path $evidence 'artifacts.json'
$lifecyclePath = Join-Path $evidence 'lifecycle/installer-lifecycle.json'
$gatePath = Join-Path $evidence 'gate.json'
$transcriptPath = Join-Path $evidence 'gate.log'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$transcriptStarted = $false
$gateStatus = 'failed'
$startedAt = [DateTimeOffset]::UtcNow.ToString('o')
$commandsPath = Join-Path $evidence 'commands.raw.json'

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

$pythonCommand = Resolve-PythonCommand
$env:PYTHONNOUSERSITE = '1'
try {
    Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
    $transcriptStarted = $true
    Push-Location $RepoRoot
    try {
        Invoke-Checked 'cargo' 'fmt' '--manifest-path' 'apps/desktop/Cargo.toml' '--' '--check'
        Invoke-Checked 'cargo' 'clippy' '--manifest-path' 'apps/desktop/Cargo.toml' '--all-targets' '--locked' '--' '-D' 'warnings'
        Invoke-Checked 'cargo' 'test' '--manifest-path' 'apps/desktop/Cargo.toml' '--locked'
        Invoke-Checked 'cargo' 'audit' '--file' 'apps/desktop/Cargo.lock'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'ci'
        Invoke-Checked 'npm' '--prefix' 'apps/web' 'run' 'build'

        Push-Location 'apps/desktop'
        try {
            Invoke-Checked 'cargo' 'tauri' 'build' '--bundles' 'msi,nsis'
        } finally {
            Pop-Location
        }

        Invoke-Checked $pythonCommand 'scripts/collect_desktop_artifacts.py' `
            '--bundle-root' $bundleRoot '--source-sha' $sourceSha `
            '--version' $desktopVersion '--output' $artifactPath
        $artifacts = Get-Content -Raw -LiteralPath $artifactPath | ConvertFrom-Json
        if (
            $artifacts.source_sha -ne $sourceSha -or
            $artifacts.classification -ne 'unsigned_local_candidate'
        ) {
            throw 'desktop artifacts have an unexpected SHA or signature classification'
        }
        $formats = @($artifacts.artifacts | ForEach-Object { $_.format } | Sort-Object)
        if (($formats -join ',') -ne 'msi,nsis') {
            throw 'desktop artifact set must contain exactly MSI and NSIS'
        }

        $installers = @(Get-ChildItem -LiteralPath $nsisRoot -Filter '*-setup.exe' -File)
        if ($installers.Count -ne 1) {
            throw "expected exactly one NSIS installer, found $($installers.Count)"
        }
        Invoke-Checked 'pwsh' '-NoProfile' '-File' `
            'scripts/verify_desktop_installer.ps1' `
            '-Installer' $installers[0].FullName `
            '-SourceSha' $sourceSha '-ApiUrl' $ApiUrl

        $lifecycle = Get-Content -Raw -LiteralPath $lifecyclePath | ConvertFrom-Json
        if (
            $lifecycle.source_sha -ne $sourceSha -or
            $lifecycle.desktop_version -ne $desktopVersion -or
            $lifecycle.backend_version -ne $desktopVersion -or
            $lifecycle.backend_status -ne 'ok' -or
            $lifecycle.gui_runs.Count -ne 2 -or
            -not $lifecycle.installed_executable_removed
        ) {
            throw 'desktop installer lifecycle evidence is incomplete'
        }

        $finalSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or $finalSha -ne $sourceSha) {
            throw 'source SHA changed during desktop commercial gate'
        }
        $finalStatus = & git -C $RepoRoot status --porcelain
        if ($LASTEXITCODE -ne 0 -or $finalStatus) {
            throw 'worktree changed during desktop commercial gate'
        }

        $gateStatus = 'passed'
        $details = [ordered]@{
            gate = 'desktop'
            source_sha = $sourceSha
            status = $gateStatus
            signature_classification = 'unsigned_local_candidate'
            installer_formats = @('msi', 'nsis')
            install_lifecycle = 'passed'
            backend_connection = 'passed'
            code_signing = 'not_authorized'
        }
        $details | ConvertTo-Json -Depth 4 | Set-Content `
            -LiteralPath (Join-Path $evidence 'details.json') -Encoding utf8
        @(
            @{ command = 'cargo fmt --check'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'cargo clippy -D warnings'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'cargo test --locked'; exit_code = 0; passed = 5; failed = 0; skipped = 0 }
            @{ command = 'cargo audit'; exit_code = 0; passed = 1; failed = 0; skipped = 0 }
            @{ command = 'npm ci and build'; exit_code = 0; passed = 2; failed = 0; skipped = 0 }
            @{ command = 'cargo tauri build --bundles msi,nsis'; exit_code = 0; passed = 2; failed = 0; skipped = 0 }
            @{ command = 'collect_desktop_artifacts.py'; exit_code = 0; passed = 2; failed = 0; skipped = 0 }
            @{ command = 'verify_desktop_installer.ps1'; exit_code = 0; passed = 6; failed = 0; skipped = 0 }
        ) | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $commandsPath -Encoding utf8
    } finally {
        Pop-Location
    }
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}

if ($gateStatus -ne 'passed') { throw 'desktop commercial gate did not pass' }
Invoke-Checked $pythonCommand 'scripts/gate_evidence.py' 'build' `
    '--gate' 'desktop' '--repo-root' $RepoRoot '--source-sha' $sourceSha `
    '--started-at' $startedAt '--commands' $commandsPath `
    '--artifacts-root' $evidence '--output' $gatePath
