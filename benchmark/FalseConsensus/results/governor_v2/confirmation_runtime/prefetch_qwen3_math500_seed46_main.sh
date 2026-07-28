#!/usr/bin/env bash
# Precompute the Qwen3 math500 seed-46 confirmation main bank on GPU0's server.
# The regular partition-A runner will treat this exact output as cached.
set -euo pipefail

REPO=/localdata/dzhaoah/Governor
PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
MODEL="Qwen/Qwen3-8B"
URL=http://localhost:18002/v1
BANK="$REPO/benchmark/FalseConsensus/results/governor_v2"
RUNTIME_DIR="$BANK/confirmation_runtime"
OUTPUT="$BANK/confirmation__qwen-qwen3-8b__math500__seed_46/main"
LOG="$RUNTIME_DIR/logs/confirmation__qwen-qwen3-8b__math500__seed_46_main.log"
STATUS="$RUNTIME_DIR/status_qwen3_prefetch_seed46.json"

cd "$REPO"
mkdir -p "$RUNTIME_DIR/logs"

file_count() {
  if [[ ! -d "$OUTPUT/traj" ]]; then
    echo 0
    return
  fi
  find "$OUTPUT/traj" -maxdepth 1 -type f -name 'problem_*.json' | wc -l
}

write_status() {
  local state="$1"
  local temporary="${STATUS}.tmp.$$"
  printf \
    '{"model":"%s","dataset":"math500","seed":46,"state":"%s","files":%s,"updated_at":"%s"}\n' \
    "$MODEL" "$state" "$(file_count)" "$(date +%Y-%m-%dT%H:%M:%S)" \
    >"$temporary"
  mv "$temporary" "$STATUS"
}

if [[ -f "$OUTPUT/run_manifest.json" ]] &&
  [[ "$(file_count)" -eq 100 ]]; then
  write_status "cached"
  exit 0
fi

write_status "collecting"
env \
  LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
  LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
  HF_HOME=/localdata/dzhaoah/hf-cache \
  "$PY" benchmark/FalseConsensus/governor_v2/collect_main.py \
  --dataset math500 \
  --model "$MODEL" \
  --budget 16384 \
  --temperature 0.6 \
  --top-p 0.95 \
  --seed 46 \
  --workers 12 \
  --url "$URL" \
  --problem-ids-file \
  "$REPO/benchmark/FalseConsensus/governor_v2/generated/problem_ids/math500__test.txt" \
  --protocol-version governor-v2-preregistered-2026-07-27.10 \
  --phase confirmation \
  --model-role development \
  --split-labels test \
  --output "$OUTPUT" \
  --dataset-path \
  "$REPO/benchmark/TokenDeprivation/data/math500/test.jsonl" \
  >"$LOG" 2>&1
write_status "complete"
