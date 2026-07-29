#!/usr/bin/env bash
set -euo pipefail
cd /localdata/dzhaoah/Governor

PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
URL="http://localhost:18000/v1"
WORKERS=12
BANK="benchmark/FalseConsensus/results/governor_v2"
RUNTIME_DIR="$BANK/confirmation_runtime"
mkdir -p "$RUNTIME_DIR/logs"

MODEL="deepseek-ai/DeepSeek-R1-Distill-Llama-8B"
SLUG="deepseek-ai-deepseek-r1-distill-llama-8b"
SEED=45
BENCHMARKS=(math500 amc23 aime24)
declare -A EXPECTED_COUNT BUDGET
EXPECTED_COUNT[math500]=100
EXPECTED_COUNT[amc23]=8
EXPECTED_COUNT[aime24]=6
BUDGET[math500]=16384
BUDGET[amc23]=16384
BUDGET[aime24]=32768

STATUS_FILE="$RUNTIME_DIR/status_llama.json"
write_status() {
    local state="$1" detail="${2:-}"
    local tmp="${STATUS_FILE}.tmp.$$"
    printf '{"model":"%s","state":"%s","detail":"%s","updated_at":"%s"}\n' \
        "$MODEL" "$state" "$detail" "$(date +%Y-%m-%dT%H:%M:%S)" > "$tmp"
    mv "$tmp" "$STATUS_FILE"
}
write_status "starting" "Llama confirmation seed=$SEED"

total=0; done=0; failed=0
for b in "${BENCHMARKS[@]}"; do
    total=$((total+1))
    env_name="confirmation__${SLUG}__${b}__seed_${SEED}"
    main_out="$BANK/$env_name/main"
    dense_out="$BANK/$env_name/dense_simple32"
    adapt_out="$BANK/$env_name/adaptive_simple32"
    budget="${BUDGET[$b]}"
    dataset_path="benchmark/TokenDeprivation/data/${b}/test.jsonl"
    problem_ids="benchmark/FalseConsensus/governor_v2/generated/problem_ids/${b}__test.txt"

    echo "[$total/3] $b seed_$SEED: starting" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"

    # Stage 1: main generation
    if [[ -f "$main_out/run_manifest.json" ]] && [[ -d "$main_out/traj" ]] && \
       [[ $(ls "$main_out/traj"/problem_*.json 2>/dev/null | wc -l) -eq ${EXPECTED_COUNT[$b]} ]]; then
        echo "  main: cached" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
    else
        echo "  main: collecting" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
        env LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
            LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
            HF_HOME=/localdata/dzhaoah/hf-cache \
            $PY benchmark/FalseConsensus/governor_v2/collect_main.py \
            --dataset "$b" --model "$MODEL" --budget "$budget" \
            --temperature 0.6 --top-p 0.95 --seed "$SEED" --workers "$WORKERS" \
            --url "$URL" --problem-ids-file "$problem_ids" \
            --protocol-version governor-v2-preregistered-2026-07-27.10 \
            --phase confirmation --model-role heldout_architecture --split-labels test \
            --output "$main_out" --dataset-path "$dataset_path" \
            > "$RUNTIME_DIR/logs/${env_name}_main.log" 2>&1 || {
            echo "  main: FAILED rc=$?" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
            failed=$((failed+1))
            write_status "failed" "$b main failed"
            continue
        }
    fi

    # Stage 2: dense_simple32
    if [[ -f "$dense_out/probe_manifest.json" ]] && \
       [[ $(ls "$dense_out/probes"/problem_*.json 2>/dev/null | wc -l) -eq ${EXPECTED_COUNT[$b]} ]]; then
        echo "  dense: cached" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
    else
        echo "  dense: collecting" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
        env LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
            LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
            HF_HOME=/localdata/dzhaoah/hf-cache \
            $PY benchmark/FalseConsensus/governor_v2/dense_probe.py \
            --main-run "$main_out" --output "$dense_out" \
            --url "$URL" --interval 64 --start-token 64 --probe-tokens 32 \
            --workers "$WORKERS" --model "$MODEL" \
            > "$RUNTIME_DIR/logs/${env_name}_dense.log" 2>&1 || {
            echo "  dense: FAILED rc=$?" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
            failed=$((failed+1))
            write_status "failed" "$b dense failed"
            continue
        }
    fi

    # Stage 3: adaptive_simple32
    if [[ -f "$adapt_out/probe_manifest.json" ]] && \
       [[ $(ls "$adapt_out/probes"/problem_*.json 2>/dev/null | wc -l) -ge ${EXPECTED_COUNT[$b]} ]]; then
        echo "  adaptive: cached" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
    else
        echo "  adaptive: collecting" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
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
            echo "  adaptive: FAILED rc=$?" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
            failed=$((failed+1))
            write_status "failed" "$b adaptive failed"
            continue
        }
    fi

    done=$((done+1))
    echo "  complete" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
    write_status "running" "$b done=$done/$total failed=$failed"
done

state="complete"; [[ $failed -gt 0 ]] && state="completed_with_failures"
write_status "$state" "done=$done failed=$failed total=$total"
echo "=== llama confirmation: $done/$total ok, $failed failed ===" | tee -a "$RUNTIME_DIR/logs/llama_runner.log"
[[ $failed -eq 0 ]]
