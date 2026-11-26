#!/usr/bin/env bash
# 实验室本机：一键关闭本账号下的 Qwen(vLLM :8000) 与 bge(:8001)。
# 用法：bash stop_lab_services.sh
# 只杀匹配命令行的进程；不碰他人无关进程。
set -euo pipefail

echo "=== stop lab services $(date -Is) ==="

stop_match() {
  local pattern="$1" name="$2"
  local pids
  pids=$(ps -ef | grep -E "$pattern" | grep -v grep | awk '{print $2}' || true)
  if [[ -z "${pids}" ]]; then
    echo "[SKIP] ${name}: not running"
    return 0
  fi
  echo "[STOP] ${name}: PIDs ${pids}"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 2
  pids=$(ps -ef | grep -E "$pattern" | grep -v grep | awk '{print $2}' || true)
  if [[ -n "${pids}" ]]; then
    echo "[KILL -9] ${name}: ${pids}"
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

stop_match "vllm.entrypoints.openai.api_server" "Qwen/vLLM"
stop_match "serve_bge_embeddings.py" "bge"

# 残留 multiproc worker（无监听时占显存）
orphans=$(ps -ef | grep -E "multiprocessing.spawn.*spawn_main" | grep "/home/taihy/.conda/envs/llm" | grep -v grep | awk '{print $2}' || true)
if [[ -n "${orphans}" ]]; then
  echo "[STOP] orphan llm workers: ${orphans}"
  # shellcheck disable=SC2086
  kill ${orphans} 2>/dev/null || true
  sleep 1
  # shellcheck disable=SC2086
  kill -9 ${orphans} 2>/dev/null || true
fi

echo "--- after ---"
ss -lntp 2>/dev/null | grep -E ":8000|:8001" || echo "(no :8000/:8001 listeners)"
ps -ef | grep -E "vllm.entrypoints|serve_bge_embeddings.py" | grep -v grep || echo "(no target procs)"
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv 2>/dev/null || true
echo "=== done ==="
