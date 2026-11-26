# 本机一键关闭：经 SSH 停实验室 Qwen+bge；可选停本机 :8200 应用。
# 用法：
#   .\scripts\stop_env.ps1              # 只停实验室模型服务
#   .\scripts\stop_env.ps1 -AlsoApp     # 同时尝试结束占用 8200 的本机进程
param(
    [switch]$AlsoApp
)

$ErrorActionPreference = "Continue"
$Key = Join-Path $env:USERPROFILE ".ssh\lab_server_key"
if (-not (Test-Path $Key)) {
    $src = "D:\support\keys\实验室服务器"
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination $Key -Force
        icacls $Key /inheritance:r | Out-Null
        icacls $Key /grant:r "$($env:USERNAME):(R)" | Out-Null
    }
}

if (-not (Test-Path $Key)) {
    Write-Host "[FAIL] SSH key missing: $Key"
    exit 2
}

$remote = Get-Content -Raw (Join-Path $PSScriptRoot "stop_lab_services.sh")
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remote))
Write-Host "=== stop lab via SSH ==="
ssh -i $Key -p 6007 -o BatchMode=yes -o ServerAliveInterval=30 taihy@47.98.139.186 "echo $b64 | base64 -d | bash"

if ($AlsoApp) {
    Write-Host "=== stop local :8200 ==="
    try {
        $conns = Get-NetTCPConnection -LocalPort 8200 -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $pid = $c.OwningProcess
            if ($pid) {
                Write-Host "[STOP] PID $pid on :8200"
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        }
        if (-not $conns) { Write-Host "[SKIP] nothing listening on :8200" }
    } catch {
        Write-Host "[WARN] could not stop :8200 :: $($_.Exception.Message)"
    }
}

Write-Host "=== local probe ==="
foreach ($u in @(
    "http://127.0.0.1:18000/v1/models",
    "http://127.0.0.1:18001/v1/models"
)) {
    try {
        Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 3 | Out-Null
        Write-Host "[STILL UP] $u"
    } catch {
        Write-Host "[DOWN] $u"
    }
}
Write-Host "=== done ==="
