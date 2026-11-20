# Run GroundTruth Node #001 (FastAPI + Cloudflare Tunnel)
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Starting GroundTruth Protocol: Node #001 (Portland)    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

# 1. Start FastAPI server in background
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ServerJob = Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn src.main:app --port 8000 --host 127.0.0.1 --proxy-headers" -PassThru -NoNewWindow
Write-Host "FastAPI server running on PID $($ServerJob.Id)..." -ForegroundColor Green

Start-Sleep -Seconds 3

# 2. Launch Cloudflare Tunnel
$Cloudflared = "C:\Users\tobia\.local\bin\cloudflared.exe"
if (Test-Path $Cloudflared) {
    $NamedTunnel = $env:CLOUDFLARE_TUNNEL_NAME
    if ($NamedTunnel) {
        Write-Host "Starting named Cloudflare Tunnel: $NamedTunnel..." -ForegroundColor Yellow
        Write-Host "Press Ctrl+C to terminate the tunnel and server." -ForegroundColor Gray
        try {
            & $Cloudflared tunnel run $NamedTunnel
        } finally {
            Write-Host "Shutting down FastAPI server..." -ForegroundColor Yellow
            Stop-Process -Id $ServerJob.Id -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "Starting Cloudflare Quick Tunnel to http://127.0.0.1:8000..." -ForegroundColor Yellow
        Write-Host "Press Ctrl+C to terminate the tunnel and server." -ForegroundColor Gray
        try {
            & $Cloudflared tunnel --url http://127.0.0.1:8000
        } finally {
            Write-Host "Shutting down FastAPI server..." -ForegroundColor Yellow
            Stop-Process -Id $ServerJob.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "Cloudflared not found at $Cloudflared. Running local only." -ForegroundColor Red
    Wait-Process -Id $ServerJob.Id
}
