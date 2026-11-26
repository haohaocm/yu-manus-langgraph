#!/usr/bin/env bash
# 实验室本机：检测 Qwen(:8000) / bge(:8001) 是否在听、进程是否在。
# 用法（在实验室）：bash check_lab_services.sh
# 也可由本机 ensure_env.ps1 经 SSH 调用。
set -euo pipefail

ok=0
fail=0

check_port() {
  local port="$1" name="$2"
  if ss -lntp 2>/dev/null | grep -q ":${port} "; then
    echo "[OK] ${name} listening :${port}"
    ok=$((ok + 1))
  else
    echo "[FAIL] ${name} NOT listening :${port}"
    fail=$((fail + 1))
  fi
}

echo "=== lab service check $(date -Is) ==="
check_port 8000 "Qwen/vLLM"
check_port 8001 "bge"

echo "--- processes ---"
ps -ef | grep -E 'vllm.entrypoints.openai.api_server|serve_bge_embeddings.py' | grep -v grep || echo "(no matching procs)"

echo "--- /v1/models ---"
if curl -sf -m 8 http://127.0.0.1:8000/v1/models >/dev/null; then
  echo "[OK] Qwen /v1/models"
  ok=$((ok + 1))
else
  echo "[FAIL] Qwen /v1/models"
  fail=$((fail + 1))
fi
if curl -sf -m 8 http://127.0.0.1:8001/v1/models >/dev/null; then
  echo "[OK] bge /v1/models"
  ok=$((ok + 1))
else
  echo "[FAIL] bge /v1/models"
  fail=$((fail + 1))
fi

echo "=== summary ok=${ok} fail=${fail} ==="
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
