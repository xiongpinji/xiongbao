param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
    [string]$ApiUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$configPath = Join-Path $repoRoot 'apps/desktop/tauri.conf.json'
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$productVersion = [string]$config.version
if ($productVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw 'invalid desktop version in Tauri configuration'
}
if ($ApiUrl -notmatch '^http://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$') {
    throw 'desktop installer verification requires a loopback HTTP API URL'
}

$nsisRoot = (Resolve-Path -LiteralPath (
    Join-Path $repoRoot 'apps/desktop/target/release/bundle/nsis'
)).Path
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$installerParent = Split-Path -Parent $installerPath
$expectedInstallerName = "X-Agent_${productVersion}_x64-setup.exe"
if (
    -not $installerParent.Equals($nsisRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    -not ([System.IO.Path]::GetFileName($installerPath)).Equals(
        $expectedInstallerName,
        [System.StringComparison]::OrdinalIgnoreCase
    )
) {
    throw 'installer is not the exact NSIS artifact from this repository'
}

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw 'LOCALAPPDATA is required for isolated installer verification'
}
$allowedBase = [System.IO.Path]::GetFullPath((
    Join-Path $env:LOCALAPPDATA 'XAgentCommercialTest'
)).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
$testRoot = [System.IO.Path]::GetFullPath((Join-Path $allowedBase $SourceSha))
$allowedPrefix = $allowedBase + [System.IO.Path]::DirectorySeparatorChar
if (-not $testRoot.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'resolved test install root escaped allowlist'
}

$evidenceRoot = Join-Path $repoRoot "output/commercial-delivery/$SourceSha/desktop/lifecycle"
$diagnosticsPath = [System.IO.Path]::GetFullPath((
    Join-Path $evidenceRoot 'diagnostics.json'
))
$evidencePath = Join-Path $evidenceRoot 'installer-lifecycle.json'
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null

$knownAppPaths = @(
    (Join-Path $testRoot 'X-Agent.exe'),
    (Join-Path $testRoot 'xagent-desktop.exe')
)
$knownUninstallerPaths = @((Join-Path $testRoot 'uninstall.exe'))
if (@($knownAppPaths + $knownUninstallerPaths | Where-Object {
            Test-Path -LiteralPath $_ -PathType Leaf
        }).Count -ne 0) {
    throw 'isolated test install root contains a previous installation'
}

function Resolve-ExactSinglePath {
    param(
        [Parameter(Mandatory = $true)][string[]]$Candidates,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $matches = @($Candidates | Where-Object {
            Test-Path -LiteralPath $_ -PathType Leaf
        })
    if ($matches.Count -ne 1) {
        throw "expected exactly one $Label, found $($matches.Count)"
    }
    $resolved = (Resolve-Path -LiteralPath $matches[0]).Path
    $resolvedParent = Split-Path -Parent $resolved
    if (-not $resolvedParent.Equals(
            $testRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "$Label escaped isolated install root"
    }
    return $resolved
}

function Invoke-GuiCycle {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][int]$Sequence
    )
    $guiProcess = Start-Process -FilePath $Executable -PassThru
    $guiPid = $guiProcess.Id
    $windowObserved = $false
    try {
        for ($attempt = 0; $attempt -lt 40; $attempt++) {
            if ($guiProcess.HasExited) {
                throw "GUI cycle $Sequence exited before a window was observed"
            }
            $guiProcess.Refresh()
            if ($guiProcess.MainWindowHandle -ne 0) {
                $windowObserved = $true
                break
            }
            Start-Sleep -Milliseconds 250
        }
        if (-not $windowObserved) {
            throw "GUI cycle $Sequence did not expose a window within 10 seconds"
        }

        $closeMode = 'CloseMainWindow'
        if (-not $guiProcess.CloseMainWindow()) {
            $closeMode = 'Stop-Process'
            Stop-Process -Id $guiPid -Force
        } elseif (-not $guiProcess.WaitForExit(10000)) {
            $closeMode = 'Stop-Process'
            Stop-Process -Id $guiPid -Force
        }
        $guiProcess.WaitForExit(10000) | Out-Null
        return [ordered]@{
            sequence = $Sequence
            pid = $guiPid
            window_observed = $windowObserved
            close_mode = $closeMode
            exit_code = $guiProcess.ExitCode
        }
    } catch {
        if (-not $guiProcess.HasExited) {
            Stop-Process -Id $guiPid -Force
            $guiProcess.WaitForExit(10000) | Out-Null
        }
        throw
    }
}

$installProcess = Start-Process -FilePath $installerPath `
    -WindowStyle Hidden -Wait -PassThru `
    -ArgumentList @('/S', "/D=$testRoot")
if ($installProcess.ExitCode -ne 0) {
    throw "NSIS installer failed with exit code $($installProcess.ExitCode)"
}

$appPath = Resolve-ExactSinglePath -Candidates $knownAppPaths -Label 'installed executable'
$uninstallerPath = Resolve-ExactSinglePath `
    -Candidates $knownUninstallerPaths -Label 'uninstaller'

$previousApiUrl = $env:XAGENT_DESKTOP_API_URL
try {
    $env:XAGENT_DESKTOP_API_URL = $ApiUrl
    $diagnosticsProcess = Start-Process -FilePath $appPath `
        -WindowStyle Hidden -Wait -PassThru `
        -ArgumentList @('--diagnostics-file', ('"{0}"' -f $diagnosticsPath))
} finally {
    $env:XAGENT_DESKTOP_API_URL = $previousApiUrl
}
if ($diagnosticsProcess.ExitCode -ne 0) {
    throw "installed diagnostics failed with exit code $($diagnosticsProcess.ExitCode)"
}
if (-not (Test-Path -LiteralPath $diagnosticsPath -PathType Leaf)) {
    throw 'installed diagnostics did not create evidence JSON'
}
$diagnostics = Get-Content -Raw -LiteralPath $diagnosticsPath | ConvertFrom-Json
if (
    $diagnostics.desktop_version -ne $productVersion -or
    $diagnostics.backend_version -ne $productVersion -or
    $diagnostics.backend_status -ne 'ok' -or
    $diagnostics.backend_url -ne $ApiUrl
) {
    throw 'installed diagnostics did not prove the expected desktop/backend versions'
}

$guiRuns = @(
    (Invoke-GuiCycle -Executable $appPath -Sequence 1),
    (Invoke-GuiCycle -Executable $appPath -Sequence 2)
)

$uninstallProcess = Start-Process -FilePath $uninstallerPath `
    -WindowStyle Hidden -Wait -PassThru -ArgumentList @('/S')
if ($uninstallProcess.ExitCode -ne 0) {
    throw "NSIS uninstaller failed with exit code $($uninstallProcess.ExitCode)"
}
for ($attempt = 0; $attempt -lt 40 -and (
        Test-Path -LiteralPath $appPath -PathType Leaf
    ); $attempt++) {
    Start-Sleep -Milliseconds 250
}
if (Test-Path -LiteralPath $appPath -PathType Leaf) {
    throw 'installed executable still exists after uninstall'
}

$evidence = [ordered]@{
    schema_version = '1.0'
    source_sha = $SourceSha
    installer = $installerPath
    installer_exit_code = $installProcess.ExitCode
    install_root = $testRoot
    installed_executable = $appPath
    diagnostics_file = $diagnosticsPath
    diagnostics_exit_code = $diagnosticsProcess.ExitCode
    desktop_version = $diagnostics.desktop_version
    backend_url = $diagnostics.backend_url
    backend_status = $diagnostics.backend_status
    backend_version = $diagnostics.backend_version
    gui_runs = $guiRuns
    uninstaller = $uninstallerPath
    uninstaller_exit_code = $uninstallProcess.ExitCode
    installed_executable_removed = $true
}
$temporaryEvidence = "$evidencePath.tmp"
$evidence | ConvertTo-Json -Depth 6 | Set-Content `
    -LiteralPath $temporaryEvidence -Encoding utf8
Move-Item -LiteralPath $temporaryEvidence -Destination $evidencePath -Force
$evidence | ConvertTo-Json -Depth 6
