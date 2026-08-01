# X-Agent 开发环境一键启动脚本
# 用法: .\scripts\dev-start.ps1 [-Port 8000] [-SkipFrontend]

param(
    [int]$Port = 8000,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "=== X-Agent Dev Start ===" -ForegroundColor Cyan
Write-Host "  Backend port : $Port"
Write-Host "  Project root : $Root"
Write-Host ""

# ── 1. 检测端口占用 ──
$existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" }

if ($existing) {
    $pid = $existing[0].OwningProcess
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    Write-Host "[!] 端口 $Port 已被占用 (PID: $pid, 进程: $($proc.ProcessName))" -ForegroundColor Yellow
    $answer = Read-Host "    是否终止该进程? (y/N)"
    if ($answer -eq "y" -or $answer -eq "Y") {
        Stop-Process -Id $pid -Force
        Write-Host "    已终止 PID $pid" -ForegroundColor Green
        Start-Sleep -Milliseconds 500
    } else {
        Write-Host "    跳过。请手动释放端口或使用 -Port 指定其他端口。" -ForegroundColor Red
        exit 1
    }
}

# ── 2. 启动后端 ──
Write-Host ""
Write-Host "[*] 启动后端 (uvicorn, port=$Port)..." -ForegroundColor Cyan

$env:XAGENT_DEV_API_TARGET = "http://localhost:$Port"

$backendJob = Start-Job -ScriptBlock {
    param($root, $port)
    Set-Location "$root\apps\api"
    python -m uvicorn xagent.main:app --host 0.0.0.0 --port $port --reload 2>&1
} -ArgumentList $Root, $Port

Write-Host "    后端 Job ID: $($backendJob.Id)" -ForegroundColor Green

# 等待后端就绪
Write-Host "    等待后端就绪..." -NoNewline
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$Port/health" -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Write-Host "." -NoNewline
}
Write-Host ""

if ($ready) {
    Write-Host "    后端已就绪 http://localhost:$Port" -ForegroundColor Green
} else {
    Write-Host "    [!] 后端未在 15s 内响应，请检查日志: Receive-Job -Id $($backendJob.Id)" -ForegroundColor Yellow
}

# ── 3. 启动前端 ──
if (-not $SkipFrontend) {
    Write-Host ""
    Write-Host "[*] 启动前端 (vite dev, port=3000)..." -ForegroundColor Cyan
    $env:XAGENT_DEV_API_TARGET = "http://localhost:$Port"
    Set-Location "$Root\apps\web"
    npx vite --port 3000
} else {
    Write-Host ""
    Write-Host "[*] 跳过前端启动。后端运行中，按 Ctrl+C 停止。" -ForegroundColor Cyan
    # 保持脚本运行以便后端 Job 继续
    while ($true) {
        Start-Sleep -Seconds 5
        $state = $backendJob.State
        if ($state -eq "Failed" -or $state -eq "Completed") {
            Write-Host "[!] 后端已退出 ($state)" -ForegroundColor Red
            Receive-Job -Id $backendJob.Id
            break
        }
    }
}
