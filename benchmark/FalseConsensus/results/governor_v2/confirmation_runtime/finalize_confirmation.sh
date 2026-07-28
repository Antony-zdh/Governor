#!/usr/bin/env bash
# Run the strict final audit after all runners complete. Release GPU0/1 only
# after the audit passes, leaving the repository ready for reviewed commit/push.
set -euo pipefail

REPO=/localdata/dzhaoah/Governor
RUNTIME_DIR="$REPO/benchmark/FalseConsensus/results/governor_v2/confirmation_runtime"
AUDIT="$REPO/benchmark/FalseConsensus/governor_v2/audit_confirmation.py"
PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
STATUS="$RUNTIME_DIR/status_finalizer.json"
LOG="$RUNTIME_DIR/logs/finalizer.log"
AUDIT_JSON="$RUNTIME_DIR/audit_final.json"
AUDIT_STDOUT="$RUNTIME_DIR/audit_final.stdout"
QWEN_SERVER_SCRIPT="$RUNTIME_DIR/serve_qwen3.sh"
DEEPSEEK_SERVER_SCRIPT="$RUNTIME_DIR/serve_deepseek.sh"

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

read_state() {
  local path="$1"
  jq -r '.state // "missing"' "$path" 2>/dev/null || echo missing
}

write_status "waiting" "Qwen partitions A/B and DeepSeek"
log "waiting for all three runners to report complete"
while true; do
  state_a="$(read_state "$RUNTIME_DIR/status_qwen3_a.json")"
  state_b="$(read_state "$RUNTIME_DIR/status_qwen3_b.json")"
  state_deepseek="$(read_state "$RUNTIME_DIR/status_deepseek.json")"
  if [[ "$state_a" == "complete" ]] &&
    [[ "$state_b" == "complete" ]] &&
    [[ "$state_deepseek" == "complete" ]]; then
    break
  fi
  for state in "$state_a" "$state_b" "$state_deepseek"; do
    if [[ "$state" == "completed_with_failures" ]]; then
      write_status "failed" "runner completed with failures"
      log "a runner reported completed_with_failures; preserving servers"
      exit 1
    fi
  done
  sleep 60
done

write_status "auditing" "strict 18-environment audit"
log "all runners complete; checking for active collectors"
if pgrep -af \
  "collect_main.py|dense_probe.py|adaptive_probe.py|run_qwen3_partition.sh|run_confirmation.sh deepseek" |
  grep -vF "pgrep -af" >/dev/null; then
  write_status "failed" "collector or runner still active"
  log "refusing final audit while a collector or runner remains active"
  exit 1
fi

log "running strict confirmation audit"
if ! "$PY" "$AUDIT" --output "$AUDIT_JSON" >"$AUDIT_STDOUT"; then
  write_status "audit_failed" "strict audit failed; servers preserved"
  log "strict audit failed; preserving servers for repair"
  exit 1
fi
if [[ "$(jq -r '.valid' "$AUDIT_JSON")" != "true" ]]; then
  write_status "audit_failed" "audit valid flag is not true"
  log "audit process exited zero but valid flag was not true"
  exit 1
fi

write_status "releasing_gpus" "strict audit passed"
log "strict audit passed; releasing verified inference servers"
qwen_pid="$(
  pgrep -f -- "-csh -c bash $QWEN_SERVER_SCRIPT" | head -n 1 || true
)"
deepseek_pid="$(
  pgrep -f -- "-csh -c bash $DEEPSEEK_SERVER_SCRIPT" | head -n 1 || true
)"
if [[ -z "$qwen_pid" ]] || [[ -z "$deepseek_pid" ]]; then
  write_status "release_failed" "could not resolve both server process groups"
  log "could not resolve both verified server launcher processes"
  exit 1
fi
for pid in "$qwen_pid" "$deepseek_pid"; do
  pgid="$(ps -p "$pid" -o pgid= | tr -d ' ')"
  if [[ "$pgid" != "$pid" ]]; then
    write_status "release_failed" "server PID/PGID identity mismatch"
    log "refusing to signal server PID $pid with unexpected PGID $pgid"
    exit 1
  fi
done
/bin/kill -TERM -- "-$qwen_pid"
/bin/kill -TERM -- "-$deepseek_pid"

for _ in $(seq 1 60); do
  if ! ps -p "$qwen_pid" >/dev/null 2>&1 &&
    ! ps -p "$deepseek_pid" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ps -p "$qwen_pid" >/dev/null 2>&1 ||
  ps -p "$deepseek_pid" >/dev/null 2>&1; then
  write_status "release_failed" "server process remained after SIGTERM"
  log "one or more server launchers remained after SIGTERM"
  exit 1
fi
if ss -ltn | grep -Eq ':18000 |:18001 |:18002 '; then
  write_status "release_failed" "confirmation port remained active"
  log "one or more confirmation ports remained active"
  exit 1
fi

write_status "ready_to_commit" "audit passed and GPU0/1 released"
log "finalizer complete: strict audit passed, GPU0/1 released"
