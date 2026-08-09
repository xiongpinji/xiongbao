param(
    [string]$EnvFile = "deploy/compose/r2.env.local",
    [string]$ProjectName = "xagent-r2",
    [switch]$Init,
    [switch]$ValidateEnvOnly,
    [switch]$AllowRunningProject
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction Stop).Source
$arguments = @(
    "-S",
    (Join-Path $repoRoot "scripts/r2_preflight.py"),
    "--env-file", (Join-Path $repoRoot $EnvFile),
    "--compose-file", (Join-Path $repoRoot "deploy/compose/docker-compose.yml"),
    "--project-name", $ProjectName,
    "--expected-branch", "feature/webapi-r2-staging-readiness",
    "--output", (Join-Path $repoRoot "output/r2-runtime/preflight.json")
)
if ($Init) {
    $arguments += @("--init-env", (Join-Path $repoRoot $EnvFile))
}
if ($ValidateEnvOnly) {
    $arguments += "--validate-env-only"
}
if ($AllowRunningProject) {
    $arguments += "--allow-running-project"
}
& $python @arguments
exit $LASTEXITCODE
