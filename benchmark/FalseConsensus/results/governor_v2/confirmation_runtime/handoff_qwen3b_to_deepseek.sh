#!/usr/bin/env bash
# After Qwen3 partition B completes, move GPU0 back to the fixed DeepSeek
# server and resume the cached DeepSeek confirmation runner.
set -euo pipefail

if [[ "$#" -ne 1 ]] || [[ ! "$1" =~ ^[0-9]+$ ]]; then
  echo "usage: $0 <gpu0-qwen-server-process-group-id>" >&2
  exit 2
fi

QWEN_SERVER_PGID="$1"
REPO=/localdata/dzhaoah/Governor
RUNTIME_DIR="$REPO/benchmark/FalseConsensus/results/governor_v2/confirmation_runtime"
PARTITION_STATUS="$RUNTIME_DIR/status_qwen3_b.json"
STATUS="$RUNTIME_DIR/status_qwen3b_to_deepseek.json"
LOG="$RUNTIME_DIR/logs/qwen3b_to_deepseek.log"
QWEN_SERVER_SCRIPT="$RUNTIME_DIR/serve_qwen3_gpu0.sh"
DEEPSEEK_SERVER_SCRIPT="$RUNTIME_DIR/serve_deepseek.sh"
DEEPSEEK_RUNNER="$RUNTIME_DIR/run_confirmation.sh"

cd "$REPO"
mkdir -p "$RUNTIME_DIR/logs"

log() {
  echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"
}

write_status() {
  local state="$1"
  local detail="$2"
  local temporary="${STATUS}.tmp.$$"
  printf \
    '{"state":"%s","detail":"%s","updated_at":"%s"}\n' \
    "$state" "$detail" "$(date +%Y-%m-%dT%H:%M:%S)" >"$temporary"
  mv "$temporary" "$STATUS"
}

write_status "waiting" "Qwen3 partition B"
log "waiting for Qwen3 partition B to complete"
while true; do
  partition_state="$(
    jq -r '.state // "missing"' "$PARTITION_STATUS" 2>/dev/null ||
      echo missing
  )"
  if [[ "$partition_state" == "complete" ]]; then
    break
  fi
  if [[ "$partition_state" == "completed_with_failures" ]]; then
    write_status "failed" "Qwen3 partition B completed with failures"
    log "partition B reported failures; refusing model handoff"
    exit 1
  fi
  command_line="$(ps -p "$QWEN_SERVER_PGID" -o args= || true)"
  if [[ "$command_line" != *"$QWEN_SERVER_SCRIPT"* ]]; then
    write_status "failed" "GPU0 Qwen server identity mismatch"
    log "unexpected GPU0 server process: $command_line"
    exit 1
  fi
  sleep 30
done

log "partition B complete; waiting for its runner process to exit"
for _ in $(seq 1 30); do
  if ! pgrep -af "run_qwen3_partition.sh b" |
    grep -vF "pgrep -af" >/dev/null; then
    break
  fi
  sleep 1
done
if pgrep -af "run_qwen3_partition.sh b" |
  grep -vF "pgrep -af" >/dev/null; then
  write_status "failed" "partition B runner still active"
  log "partition B runner remained active after completion"
  exit 1
fi

write_status "stopping_qwen3" "partition B complete"
command_line="$(ps -p "$QWEN_SERVER_PGID" -o args= || true)"
if [[ "$command_line" != *"$QWEN_SERVER_SCRIPT"* ]]; then
  write_status "failed" "GPU0 Qwen server identity mismatch at handoff"
  log "refusing to signal unexpected process: $command_line"
  exit 1
fi
log "stopping verified GPU0 Qwen server process group $QWEN_SERVER_PGID"
/bin/kill -TERM -- "-$QWEN_SERVER_PGID"
for _ in $(seq 1 60); do
  if ! ps -p "$QWEN_SERVER_PGID" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ps -p "$QWEN_SERVER_PGID" >/dev/null 2>&1; then
  write_status "failed" "GPU0 Qwen server did not stop"
  log "GPU0 Qwen server did not stop after SIGTERM"
  exit 1
fi
if ss -ltn | grep -q ':18002 '; then
  write_status "failed" "port 18002 still listening"
  log "port 18002 remained active after Qwen shutdown"
  exit 1
fi

write_status "starting_deepseek" "fixed snapshot on GPU0"
log "starting fixed-revision DeepSeek server on GPU0"
tmux new-window -d -t confirm -n deepseek_srv2 \
  "bash $DEEPSEEK_SERVER_SCRIPT"
server_ready=false
for _ in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:18000/health \
    >/dev/null 2>&1; then
    server_ready=true
    break
  fi
  sleep 1
done
if [[ "$server_ready" != "true" ]]; then
  write_status "failed" "DeepSeek server health timeout"
  log "DeepSeek server did not become healthy within 120 seconds"
  exit 1
fi
if ! ps -eo args= |
  grep -F "vllm serve" |
  grep -F "916b56a44061fd5cd7d6a8fb632557ed4f724f60" |
  grep -F -- "--port 18000" >/dev/null; then
  write_status "failed" "DeepSeek server identity verification failed"
  log "DeepSeek server process did not match the fixed snapshot and port"
  exit 1
fi

write_status "resuming_deepseek" "cached confirmation runner"
log "DeepSeek server healthy; resuming confirmation runner"
tmux new-window -d -t confirm -n deepseek_run2 \
  "bash $DEEPSEEK_RUNNER deepseek"
write_status "complete" "DeepSeek runner resumed"
log "Qwen3-to-DeepSeek handoff complete"
