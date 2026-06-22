$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps\api"
$Web = Join-Path $Root "apps\web"
$Sdk = Join-Path $Root "packages\sdk-ts"

# ponytail: UTF-8 avoids Windows GBK choking on .pth files under Chinese paths.
$env:PYTHONUTF8 = "1"
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")

Write-Host "== Tool versions =="
py -3.11 --version
python --version
node --version
npm --version
docker --version
rustc --version
cargo --version
ollama --version

Write-Host "== API deps =="
Set-Location $Api
if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
py -3.11 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# ponytail: non-editable install avoids UTF-8 .pth files breaking under Windows GBK paths.
pip install ".[dev]"
python -m pip check
deactivate

Write-Host "== Web deps =="
Set-Location $Web
npm install

Write-Host "== SDK deps =="
Set-Location $Sdk
npm install

Write-Host "== Done =="
Write-Host "Docker Desktop must be running before: docker compose up -d"
