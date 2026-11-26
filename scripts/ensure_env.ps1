# 本机：检测隧道 +（可选）经 SSH 检测/补启实验室服务。
# 用法：
#   .\scripts\ensure_env.ps1              # 只检测
#   .\scripts\ensure_env.ps1 -StartMissing  # 检测；缺 Qwen 且 :8000 空闲则启动；bge 已占用则不杀不重启
# 注意：Qwen tp=2 util=0.55 + bge@GPU1。若 GPU1 有孤儿 vLLM worker 占显存会 OOM；
#       脚本不会擅自杀孤儿——用 stop_env.ps1 或人工清理后再 -StartMissing。
param(
    [switch]$StartMissing
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

function Test-Url([string]$Url, [string]$Name) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
        Write-Host "[OK] $Name -> $($r.StatusCode) $Url"
        return $true
    } catch {
        Write-Host "[FAIL] $Name -> $Url :: $($_.Exception.Message)"
        return $false
    }
}

Write-Host "=== local probes ==="
$qwenLocal = Test-Url "http://127.0.0.1:18000/v1/models" "Qwen tunnel :18000"
$bgeLocal  = Test-Url "http://127.0.0.1:18001/v1/models" "bge tunnel :18001"
$appLocal  = Test-Url "http://127.0.0.1:8200/" "app :8200"

Write-Host "=== lab via SSH ==="
if (-not (Test-Path $Key)) {
    Write-Host "[FAIL] SSH key missing: $Key"
    exit 2
}

$remoteCheck = @'
set -e
ss -lntp | grep -E ":8000|:8001" || true
ps -ef | grep -E "vllm.entrypoints.openai.api_server|serve_bge_embeddings.py" | grep -v grep || true
curl -sf -m 8 http://127.0.0.1:8000/v1/models >/dev/null && echo QWEN_API_OK || echo QWEN_API_FAIL
curl -sf -m 8 http://127.0.0.1:8001/v1/models >/dev/null && echo BGE_API_OK || echo BGE_API_FAIL
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteCheck))
$labOut = ssh -i $Key -p 6007 -o BatchMode=yes -o ConnectTimeout=20 taihy@47.98.139.186 "echo $b64 | base64 -d | bash"
Write-Host $labOut

$labQwen = $labOut -match "QWEN_API_OK"
$labBge  = $labOut -match "BGE_API_OK"
$port8000 = $labOut -match ":8000"
$port8001 = $labOut -match ":8001"

if ($StartMissing) {
    if (-not $labQwen) {
        if ($port8000) {
            Write-Host "[STOP] :8000 occupied but /v1/models failed — do NOT kill; inspect manually."
        } else {
            Write-Host "[START] launching Qwen (start_qwen_vllm.sh) ..."
            $startCmd = @'
mkdir -p /home/data/data_taihy/logs
nohup bash /home/data/data_taihy/start_qwen_vllm.sh > /home/data/data_taihy/logs/qwen.log 2>&1 &
echo STARTED_QWEN
'@
            $b64s = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($startCmd))
            ssh -i $Key -p 6007 -o BatchMode=yes -o ServerAliveInterval=30 taihy@47.98.139.186 "echo $b64s | base64 -d | bash"
            Write-Host "Waiting for Qwen :8000 ..."
            $up = $false
            for ($i = 1; $i -le 90; $i++) {
                Start-Sleep -Seconds 10
                $probe = ssh -i $Key -p 6007 -o BatchMode=yes -o ConnectTimeout=15 taihy@47.98.139.186 "curl -sf -m 5 http://127.0.0.1:8000/v1/models >/dev/null && echo OK || echo WAIT"
                if ($probe -match "OK") { $up = $true; Write-Host "[OK] Qwen up after ~${i}0s"; break }
                Write-Host "  ... still loading ($i)"
            }
            if (-not $up) {
                Write-Host "[FAIL] Qwen did not become ready; check /home/data/data_taihy/logs/qwen.log"
            } else {
                $labQwen = $true
            }
        }
    } else {
        Write-Host "[SKIP] Qwen already OK on lab"
    }

    if (-not $labBge) {
        if ($port8001) {
            Write-Host "[STOP] :8001 occupied but API failed — do NOT kill; inspect manually."
        } else {
            Write-Host "[START] launching bge ..."
            $startBge = @'
mkdir -p /home/data/data_taihy/logs
nohup bash /home/data/data_taihy/start_bge_embeddings.sh > /home/data/data_taihy/logs/bge.log 2>&1 &
echo STARTED_BGE
'@
            $b64b = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($startBge))
            ssh -i $Key -p 6007 -o BatchMode=yes taihy@47.98.139.186 "echo $b64b | base64 -d | bash"
            Start-Sleep -Seconds 15
            $probeB = ssh -i $Key -p 6007 -o BatchMode=yes taihy@47.98.139.186 "curl -sf -m 8 http://127.0.0.1:8001/v1/models >/dev/null && echo OK || echo FAIL"
            Write-Host "bge probe: $probeB"
            $labBge = $probeB -match "OK"
        }
    } else {
        Write-Host "[SKIP] bge already OK on lab (will not restart)"
    }
}

Write-Host "=== re-probe local tunnels ==="
$qwenLocal = Test-Url "http://127.0.0.1:18000/v1/models" "Qwen tunnel :18000"
$bgeLocal  = Test-Url "http://127.0.0.1:18001/v1/models" "bge tunnel :18001"

Write-Host "=== RESULT ==="
Write-Host "lab Qwen=$labQwen  lab bge=$labBge  local18000=$qwenLocal  local18001=$bgeLocal  app8200=$appLocal"
if (-not $qwenLocal -and $labQwen) {
    Write-Host "NOTE: lab Qwen OK but local :18000 failed — open SSH -L 18000:127.0.0.1:8000 tunnel."
}
if (-not $bgeLocal -and $labBge) {
    Write-Host "NOTE: lab bge OK but local :18001 failed — open SSH -L 18001:127.0.0.1:8001 tunnel."
}

if ($labQwen -and $labBge -and $qwenLocal -and $bgeLocal) { exit 0 }
exit 1
