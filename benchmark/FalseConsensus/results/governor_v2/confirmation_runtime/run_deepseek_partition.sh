#!/usr/bin/env bash
# Resume the remaining DeepSeek confirmation jobs as two exhaustive, disjoint
# partitions. Existing complete math500 environments remain cached and are
# covered by the final strict 18-environment audit.
set -euo pipefail

PARTITION="${1:?usage: $0 <a|b|c>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
cd "$REPO"

case "$PARTITION" in
  a)
    URL="http://localhost:18003/v1"
    JOBS=("amc23:45" "amc23:46" "amc23:47" "aime24:47")
    ;;
  b)
    URL="http://localhost:18000/v1"
    JOBS=("aime24:45" "aime24:46")
    ;;
  c)
    # Opportunistic tail prefetch on GPU0 after partition b completes. This
    # output is disjoint from partition a's active AMC jobs; partition a will
    # later verify and reuse the complete AIME47 cache.
    URL="http://localhost:18000/v1"
    JOBS=("aime24:47")
    ;;
  *)
    echo "usage: $0 <a|b|c>" >&2
    exit 2
    ;;
esac

PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
WORKERS=12
MODEL="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
SLUG="deepseek-ai-deepseek-r1-distill-qwen-7b"
BANK="$REPO/benchmark/FalseConsensus/results/governor_v2"
RUNTIME_DIR="$BANK/confirmation_runtime"
mkdir -p "$RUNTIME_DIR/logs"

declare -A EXPECTED_COUNT=([amc23]=8 [aime24]=6)
declare -A BUDGET=([amc23]=16384 [aime24]=32768)

log() {
  echo "[$(date +%H:%M:%S)] $*" |
    tee -a "$RUNTIME_DIR/logs/deepseek_${PARTITION}_runner.log"
}

write_status() {
  local state="$1"
  local detail="${2:-}"
  local status_file="$RUNTIME_DIR/status_deepseek_${PARTITION}.json"
  local temporary="${status_file}.tmp.$$"
  printf \
    '{"model_key":"deepseek_%s","model":"%s","state":"%s","detail":"%s","updated_at":"%s"}\n' \
    "$PARTITION" "$MODEL" "$state" "$detail" \
    "$(date +%Y-%m-%dT%H:%M:%S)" >"$temporary"
  mv "$temporary" "$status_file"
}

file_count() {
  local directory="$1"
  if [[ ! -d "$directory" ]]; then
    echo 0
    return
  fi
  find "$directory" -maxdepth 1 -type f -name 'problem_*.json' | wc -l
}

write_status "starting" "partition=$PARTITION jobs=${#JOBS[@]}"
done_count=0
failed=0
job_index=0

for job in "${JOBS[@]}"; do
  job_index=$((job_index + 1))
  dataset="${job%%:*}"
  seed="${job##*:}"
  expected="${EXPECTED_COUNT[$dataset]}"
  budget="${BUDGET[$dataset]}"
  env_name="confirmation__${SLUG}__${dataset}__seed_${seed}"
  main_out="$BANK/$env_name/main"
  dense_out="$BANK/$env_name/dense_simple32"
  adaptive_out="$BANK/$env_name/adaptive_simple32"
  dataset_path="$REPO/benchmark/TokenDeprivation/data/${dataset}/test.jsonl"
  problem_ids="$REPO/benchmark/FalseConsensus/governor_v2/generated/problem_ids/${dataset}__test.txt"

  log "[$job_index/${#JOBS[@]}] $dataset seed_$seed: starting"

  if [[ -f "$main_out/run_manifest.json" ]] &&
    [[ "$(file_count "$main_out/traj")" -eq "$expected" ]]; then
    log "  main: cached"
  else
    log "  main: collecting"
    if ! env \
      LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
      LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
      HF_HOME=/localdata/dzhaoah/hf-cache \
      "$PY" benchmark/FalseConsensus/governor_v2/collect_main.py \
      --dataset "$dataset" \
      --model "$MODEL" \
      --budget "$budget" \
      --temperature 0.6 \
      --top-p 0.95 \
      --seed "$seed" \
      --workers "$WORKERS" \
      --url "$URL" \
      --problem-ids-file "$problem_ids" \
      --protocol-version governor-v2-preregistered-2026-07-27.10 \
      --phase confirmation \
      --model-role development \
      --split-labels test \
      --output "$main_out" \
      --dataset-path "$dataset_path" \
      >"$RUNTIME_DIR/logs/${env_name}_main.log" 2>&1; then
      log "  main: FAILED"
      failed=$((failed + 1))
      write_status "failed" "$dataset seed_$seed main failed"
      continue
    fi
  fi

  if [[ -f "$dense_out/probe_manifest.json" ]] &&
    [[ "$(file_count "$dense_out/probes")" -eq "$expected" ]]; then
    log "  dense: cached"
  else
    log "  dense: collecting"
    if ! env \
      LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
      LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
      HF_HOME=/localdata/dzhaoah/hf-cache \
      "$PY" benchmark/FalseConsensus/governor_v2/dense_probe.py \
      --main-run "$main_out" \
      --output "$dense_out" \
      --url "$URL" \
      --interval 64 \
      --start-token 64 \
      --probe-tokens 32 \
      --workers "$WORKERS" \
      --model "$MODEL" \
      >"$RUNTIME_DIR/logs/${env_name}_dense.log" 2>&1; then
      log "  dense: FAILED"
      failed=$((failed + 1))
      write_status "failed" "$dataset seed_$seed dense failed"
      continue
    fi
  fi

  if [[ -f "$adaptive_out/probe_manifest.json" ]] &&
    [[ "$(file_count "$adaptive_out/probes")" -eq "$expected" ]]; then
    log "  adaptive: cached"
  else
    log "  adaptive: collecting"
    if ! env \
      LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
      LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
      HF_HOME=/localdata/dzhaoah/hf-cache \
      "$PY" benchmark/FalseConsensus/governor_v2/adaptive_probe.py \
      --main-run "$main_out" \
      --dense-probe-bank "$dense_out" \
      --output "$adaptive_out" \
      --url "$URL" \
      --start-token 256 \
      --probe-tokens 32 \
      --workers "$WORKERS" \
      --model "$MODEL" \
      --alignment-lookahead-tokens 32 \
      --entropy-top-k 20 \
      --entropy-smooth-window 16 \
      --entropy-reference-window 64 \
      --entropy-candidate-min-drop 0.1 \
      --candidate-min-gap 32 \
      --max-candidate-probes 128 \
      >"$RUNTIME_DIR/logs/${env_name}_adaptive.log" 2>&1; then
      log "  adaptive: FAILED"
      failed=$((failed + 1))
      write_status "failed" "$dataset seed_$seed adaptive failed"
      continue
    fi
  fi

  done_count=$((done_count + 1))
  log "  complete"
  write_status \
    "running" \
    "partition=$PARTITION done=$done_count/${#JOBS[@]} failed=$failed"
done

state="complete"
if [[ "$failed" -gt 0 ]]; then
  state="completed_with_failures"
fi
write_status \
  "$state" \
  "partition=$PARTITION done=$done_count failed=$failed total=${#JOBS[@]}"
log \
  "=== deepseek partition $PARTITION: $done_count/${#JOBS[@]} ok, $failed failed ==="
[[ "$failed" -eq 0 ]]
