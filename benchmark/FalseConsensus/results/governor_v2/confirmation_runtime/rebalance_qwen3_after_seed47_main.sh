#!/usr/bin/env bash
# At the seed-47 main boundary, move seed-46 main generation to GPU0 and then
# resume partition B. This balances the two Qwen3 partitions without changing
# any samples, seeds, protocol settings, or final output paths.
set -euo pipefail

if [[ "$#" -ne 1 ]] || [[ ! "$1" =~ ^[0-9]+$ ]]; then
  echo "usage: $0 <current-partition-b-process-group-id>" >&2
  exit 2
fi

OLD_PGID="$1"
REPO=/localdata/dzhaoah/Governor
BANK="$REPO/benchmark/FalseConsensus/results/governor_v2"
RUNTIME_DIR="$BANK/confirmation_runtime"
SEED47_MAIN="$BANK/confirmation__qwen-qwen3-8b__math500__seed_47/main"
SEED46_MAIN="$BANK/confirmation__qwen-qwen3-8b__math500__seed_46/main"
LOG="$RUNTIME_DIR/logs/qwen3_rebalance.log"
STATUS="$RUNTIME_DIR/status_qwen3_rebalance.json"
PREFETCH="$RUNTIME_DIR/prefetch_qwen3_math500_seed46_main.sh"
PARTITION_RUNNER="$RUNTIME_DIR/run_qwen3_partition.sh"

cd "$REPO"
mkdir -p "$RUNTIME_DIR/logs"

log() {
  echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"
}

file_count() {
  local directory="$1"
  if [[ ! -d "$directory" ]]; then
    echo 0
    return
  fi
  find "$directory" -maxdepth 1 -type f -name 'problem_*.json' | wc -l
}

write_status() {
  local state="$1"
  local detail="$2"
  local temporary="${STATUS}.tmp.$$"
  printf \
    '{"state":"%s","detail":"%s","seed47_main_files":%s,"seed46_main_files":%s,"updated_at":"%s"}\n' \
    "$state" "$detail" \
    "$(file_count "$SEED47_MAIN/traj")" \
    "$(file_count "$SEED46_MAIN/traj")" \
    "$(date +%Y-%m-%dT%H:%M:%S)" >"$temporary"
  mv "$temporary" "$STATUS"
}

write_status "waiting" "seed47 main boundary"
log "waiting for Qwen3 math500 seed47 main to reach 100/100"
while [[ ! -f "$SEED47_MAIN/run_manifest.json" ]] ||
  [[ "$(file_count "$SEED47_MAIN/traj")" -ne 100 ]]; do
  if ! ps -p "$OLD_PGID" -o args= |
    grep -Fq "run_qwen3_partition.sh b"; then
    write_status "failed" "partition B process group disappeared"
    log "partition B process group $OLD_PGID disappeared before boundary"
    exit 1
  fi
  sleep 10
done

write_status "pausing_partition_b" "seed47 main complete"
log "seed47 main complete; pausing partition B process group $OLD_PGID"
command_line="$(ps -p "$OLD_PGID" -o args= || true)"
if [[ "$command_line" != *"run_qwen3_partition.sh b"* ]]; then
  write_status "failed" "partition B process identity mismatch"
  log "refusing to signal unexpected process: $command_line"
  exit 1
fi
/bin/kill -TERM -- "-$OLD_PGID"

for _ in $(seq 1 30); do
  if ! ps -p "$OLD_PGID" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ps -p "$OLD_PGID" >/dev/null 2>&1; then
  write_status "failed" "partition B did not stop after SIGTERM"
  log "partition B process group did not stop after SIGTERM"
  exit 1
fi

write_status "prefetching" "math500 seed46 main on port 18002"
log "prefetching Qwen3 math500 seed46 main on GPU0"
bash "$PREFETCH"
if [[ ! -f "$SEED46_MAIN/run_manifest.json" ]] ||
  [[ "$(file_count "$SEED46_MAIN/traj")" -ne 100 ]]; then
  write_status "failed" "seed46 main verification failed"
  log "seed46 main did not verify as 100/100 with manifest"
  exit 1
fi

write_status "resuming_partition_b" "seed46 main complete"
log "seed46 main complete; resuming partition B"
tmux new-window -d -t confirm -n qwen3runB2 \
  "bash $PARTITION_RUNNER b"
write_status "complete" "partition B resumed"
log "rebalance complete"
