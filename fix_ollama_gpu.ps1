# fix_ollama_gpu.ps1
# Run this in PowerShell to fully restart Ollama with GPU variables active
# Usage: Right-click PowerShell > Run as Administrator, then paste this

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  OLLAMA GPU FIX — Forcing full restart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Step 1: Kill ALL Ollama processes
Write-Host "`n[1/5] Killing all Ollama processes..." -ForegroundColor Yellow
$ollamaProcs = Get-Process -Name "ollama*" -ErrorAction SilentlyContinue
if ($ollamaProcs) {
    $ollamaProcs | ForEach-Object {
        Write-Host "  Killing: $($_.Name) (PID $($_.Id))"
        Stop-Process -Id $_.Id -Force
    }
    Start-Sleep -Seconds 3
    Write-Host "  Done." -ForegroundColor Green
} else {
    Write-Host "  No Ollama processes found — already stopped." -ForegroundColor Gray
}

# Step 2: Set environment variables for THIS session
# (These override whatever Windows stored until Ollama picks them up permanently)
Write-Host "`n[2/5] Setting GPU environment variables for this session..." -ForegroundColor Yellow
$env:OLLAMA_NUM_GPU         = "999"
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:OLLAMA_NUM_PARALLEL    = "2"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
Write-Host "  OLLAMA_NUM_GPU         = $env:OLLAMA_NUM_GPU" -ForegroundColor Green
Write-Host "  OLLAMA_FLASH_ATTENTION = $env:OLLAMA_FLASH_ATTENTION" -ForegroundColor Green
Write-Host "  OLLAMA_NUM_PARALLEL    = $env:OLLAMA_NUM_PARALLEL" -ForegroundColor Green
Write-Host "  OLLAMA_MAX_LOADED_MODELS = $env:OLLAMA_MAX_LOADED_MODELS" -ForegroundColor Green

# Step 3: Also write them permanently to user environment (in case they didn't save)
Write-Host "`n[3/5] Writing variables to permanent user environment..." -ForegroundColor Yellow
[System.Environment]::SetEnvironmentVariable("OLLAMA_NUM_GPU",          "999",  "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION",  "1",    "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL",     "2",    "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS","1",    "User")
Write-Host "  Written permanently." -ForegroundColor Green

# Step 4: Start Ollama serve in background with these variables active
Write-Host "`n[4/5] Starting Ollama with GPU variables active..." -ForegroundColor Yellow

# Find ollama.exe
$ollamaPath = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollamaPath) {
    $ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
}
if (-not (Test-Path $ollamaPath)) {
    $ollamaPath = "C:\Users\User\AppData\Local\Programs\Ollama\ollama.exe"
}

Write-Host "  Ollama path: $ollamaPath"

if (Test-Path $ollamaPath) {
    # Start ollama serve as a background job so this script keeps running
    Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden
    Write-Host "  Ollama started in background." -ForegroundColor Green
} else {
    Write-Host "  Could not find ollama.exe — starting via command..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-Command ollama serve" -WindowStyle Minimized
}

# Step 5: Wait for Ollama to be ready, then test
Write-Host "`n[5/5] Waiting for Ollama to be ready..." -ForegroundColor Yellow
$ready = $false
$attempts = 0
while (-not $ready -and $attempts -lt 20) {
    Start-Sleep -Seconds 2
    $attempts++
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
        $ready = $true
        Write-Host "  Ollama is ready! ($($attempts * 2)s)" -ForegroundColor Green
    } catch {
        Write-Host "  Waiting... ($($attempts * 2)s)" -ForegroundColor Gray
    }
}

if (-not $ready) {
    Write-Host "  Ollama did not start in time. Try launching it manually from Start menu." -ForegroundColor Red
    exit 1
}

# Quick GPU verification test using qwen3:14b (the right size for 16GB VRAM)
Write-Host "`n  Testing qwen3:14b with GPU..." -ForegroundColor Yellow
$testBody = @{
    model = "qwen3:14b"
    messages = @(@{ role = "user"; content = "Say: GPU ONLINE" })
    stream = $false
    options = @{
        num_predict = 10
        num_gpu = -1
        temperature = 0.1
    }
} | ConvertTo-Json -Depth 5

try {
    $start = Get-Date
    $result = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" `
        -Method POST `
        -Body $testBody `
        -ContentType "application/json" `
        -TimeoutSec 120
    $elapsed = ((Get-Date) - $start).TotalSeconds
    $reply = $result.message.content

    Write-Host "  Response: '$reply'" -ForegroundColor Green
    Write-Host "  Time: $([math]::Round($elapsed, 1))s" -ForegroundColor Cyan

    if ($elapsed -lt 10) {
        Write-Host "  GPU IS WORKING — fast response confirms GPU acceleration" -ForegroundColor Green
    } elseif ($elapsed -lt 30) {
        Write-Host "  Moderate speed — GPU may be partially engaged" -ForegroundColor Yellow
    } else {
        Write-Host "  Slow response — GPU may not be fully engaged yet" -ForegroundColor Red
        Write-Host "  Try rebooting your PC — environment variables need a fresh session" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Test failed: $_" -ForegroundColor Red
    Write-Host "  The model may still be loading — wait 30s and try again" -ForegroundColor Yellow
}

# Check VRAM after loading
Write-Host "`n  VRAM check after model load:" -ForegroundColor Yellow
try {
    $nvidiaSmi = nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
    $parts = $nvidiaSmi.Trim() -split ",\s*"
    Write-Host "  Used: $($parts[0])MB / $($parts[1])MB  |  GPU Util: $($parts[2])%" -ForegroundColor Cyan

    $used = [int]$parts[0]
    if ($used -gt 5000) {
        Write-Host "  CONFIRMED: Model loaded into GPU VRAM ($($used)MB)" -ForegroundColor Green
    } else {
        Write-Host "  Low VRAM usage — model may not be GPU-accelerated" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  nvidia-smi not in PATH — skipping VRAM check" -ForegroundColor Gray
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "  DONE. Ollama is running with GPU variables set." -ForegroundColor Cyan
Write-Host "  Now restart NEX (run launch_habitat.py)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan