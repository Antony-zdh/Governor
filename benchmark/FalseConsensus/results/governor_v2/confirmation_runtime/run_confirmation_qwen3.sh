#!/usr/bin/env bash
# run_confirmation.sh -- Governor-v2 confirmation collection for one model.
# Usage: run_confirmation.sh <deepseek|qwen3>
# Requires a vLLM server on localhost:18000 with TP=2.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$SCRIPT_DIR"
for _ in 1 2 3 4 5; do REPO="$(dirname "$REPO")"; done
if [[ ! -d "$REPO/benchmark" ]]; then
    REPO="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel)"
fi

cd "$REPO"
PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
URL="http://localhost:18001/v1"
WORKERS=12
BANK="$REPO/benchmark/FalseConsensus/results/governor_v2"
SPLIT="$REPO/benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
RUNTIME_DIR="$BANK/confirmation_runtime"
mkdir -p "$RUNTIME_DIR/logs"

KEY="qwen3"
if [[ "$KEY" == "deepseek" ]]; then
    MODEL="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    SLUG="deepseek-ai-deepseek-r1-distill-qwen-7b"
elif [[ "$KEY" == "qwen3" ]]; then
    MODEL="Qwen/Qwen3-8B"
    SLUG="qwen-qwen3-8b"
else
    echo "Usage: $0 <deepseek|qwen3>" >&2; exit 2
fi

BENCHMARKS=(math500 amc23 aime24)
SEEDS=(45 46 47)
declare -A EXPECTED_COUNT
EXPECTED_COUNT[math500]=100
EXPECTED_COUNT[amc23]=8
EXPECTED_COUNT[aime24]=6
BUDGETS=(16384 16384 32768)

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$RUNTIME_DIR/logs/${KEY}_runner.log"; }

STATUS_FILE="$RUNTIME_DIR/status_${KEY}.json"
write_status() {
    local state="$1" detail="${2:-}"
    local tmp="${STATUS_FILE}.tmp.$$"
    printf '{"model_key":"%s","model":"%s","state":"%s","detail":"%s","updated_at":"%s"}\n' \
        "$KEY" "$MODEL" "$state" "$detail" "$(date +%Y-%m-%dT%H:%M:%S)" > "$tmp"
    mv "$tmp" "$STATUS_FILE"
}

write_status "starting" "confirmation collection for $MODEL"

total=0; done=0; failed=0
for bi in 0 1 2; do
    b="${BENCHMARKS[$bi]}"
    budget="${BUDGETS[$bi]}"
    dataset_path="$REPO/benchmark/TokenDeprivation/data/${b}/test.jsonl"
    problem_ids="$REPO/benchmark/FalseConsensus/governor_v2/generated/problem_ids/${b}__test.txt"
    for s in "${SEEDS[@]}"; do
        total=$((total+1))
        env_name="confirmation__${SLUG}__${b}__seed_${s}"
        main_out="$BANK/$env_name/main"
        dense_out="$BANK/$env_name/dense_simple32"
        adapt_out="$BANK/$env_name/adaptive_simple32"

        log "[$total/9] $b seed_$s: starting"

        # Stage 1: main generation
        if [[ -f "$main_out/run_manifest.json" ]] && [[ -d "$main_out/traj" ]] && \
           [[ $(ls "$main_out/traj"/problem_*.json 2>/dev/null | wc -l) -eq ${EXPECTED_COUNT[$b]} ]]; then
            log "  main: cached"
        else
            log "  main: collecting"
            env LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
                LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
                HF_HOME=/localdata/dzhaoah/hf-cache \
                $PY benchmark/FalseConsensus/governor_v2/collect_main.py \
                --dataset "$b" --model "$MODEL" --budget "$budget" \
                --temperature 0.6 --top-p 0.95 --seed "$s" --workers "$WORKERS" \
                --url "$URL" --problem-ids-file "$problem_ids" \
                --protocol-version governor-v2-preregistered-2026-07-27.10 \
                --phase confirmation --model-role development --split-labels test \
                --output "$main_out" --dataset-path "$dataset_path" \
                > "$RUNTIME_DIR/logs/${env_name}_main.log" 2>&1 || {
                log "  main: FAILED rc=$?"
                failed=$((failed+1))
                write_status "failed" "$b seed_$s main failed"
                continue
            }
        fi

        # Stage 2: dense_simple32
        if [[ -f "$dense_out/probe_manifest.json" ]] && \
           [[ $(ls "$dense_out/probes"/problem_*.json 2>/dev/null | wc -l) -eq ${EXPECTED_COUNT[$b]} ]]; then
            log "  dense: cached"
        else
            log "  dense: collecting"
            env LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
                LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
                HF_HOME=/localdata/dzhaoah/hf-cache \
                $PY benchmark/FalseConsensus/governor_v2/dense_probe.py \
                --main-run "$main_out" --output "$dense_out" \
                --url "$URL" --interval 64 --start-token 64 --probe-tokens 32 \
                --workers "$WORKERS" --model "$MODEL" \
                > "$RUNTIME_DIR/logs/${env_name}_dense.log" 2>&1 || {
                log "  dense: FAILED rc=$?"
                failed=$((failed+1))
                write_status "failed" "$b seed_$s dense failed"
                continue
            }
        fi

        # Stage 3: adaptive_simple32
        if [[ -f "$adapt_out/probe_manifest.json" ]] && \
           [[ $(ls "$adapt_out/probes"/problem_*.json 2>/dev/null | wc -l) -ge ${EXPECTED_COUNT[$b]} ]]; then
            log "  adaptive: cached"
        else
            log "  adaptive: collecting"
            env LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
                LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
                HF_HOME=/localdata/dzhaoah/hf-cache \
                $PY benchmark/FalseConsensus/governor_v2/adaptive_probe.py \
                --main-run "$main_out" --dense-probe-bank "$dense_out" \
                --output "$adapt_out" --url "$URL" \
                --start-token 256 --probe-tokens 32 --workers "$WORKERS" --model "$MODEL" \
                --alignment-lookahead-tokens 32 --entropy-top-k 20 \
                --entropy-smooth-window 16 --entropy-reference-window 64 \
                --entropy-candidate-min-drop 0.1 --candidate-min-gap 32 \
                --max-candidate-probes 128 \
                > "$RUNTIME_DIR/logs/${env_name}_adaptive.log" 2>&1 || {
                log "  adaptive: FAILED rc=$?"
                failed=$((failed+1))
                write_status "failed" "$b seed_$s adaptive failed"
                continue
            }
        fi

        done=$((done+1))
        log "  complete"
        write_status "running" "$b seed_$s done=$done/$total failed=$failed"
    done
done

state="complete"; [[ $failed -gt 0 ]] && state="completed_with_failures"
write_status "$state" "done=$done failed=$failed total=$total"
log "=== $KEY confirmation: $done/$total ok, $failed failed ==="
[[ $failed -eq 0 ]]
