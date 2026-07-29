#!/usr/bin/env bash
set -euo pipefail
cd /localdata/dzhaoah/Governor

PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
BANK="benchmark/FalseConsensus/results/governor_v2"
FULL="benchmark/FalseConsensus/results/related_work/test"
SM="benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
mkdir -p "$FULL/_runtime/logs"

KEY="${1:?usage: $0 <deepseek|qwen3>}"
if [[ "$KEY" == "deepseek" ]]; then
    MODEL="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    REV="916b56a44061fd5cd7d6a8fb632557ed4f724f60"
    SLUG="deepseek-ai-deepseek-r1-distill-qwen-7b"
    PORT=18001
elif [[ "$KEY" == "qwen3" ]]; then
    MODEL="Qwen/Qwen3-8B"
    REV="b968826d9c46dd6066d109eabc6255188de91218"
    SLUG="qwen-qwen3-8b"
    PORT=18002
else
    echo "unknown key"; exit 2
fi
URL="http://127.0.0.1:${PORT}/v1"
WORKERS=12
SEEDS=(45 46 47)
BENCHMARKS=(math500 amc23 aime24)
declare -A EXP
EXP[math500]=100; EXP[amc23]=8; EXP[aime24]=6

total=0; done=0; failed=0
for method in certaindex_mid tje deer; do
    for b in "${BENCHMARKS[@]}"; do
        for s in "${SEEDS[@]}"; do
            total=$((total+1))
            main_run="$BANK/confirmation__${SLUG}__${b}__seed_${s}/main"
            out="$FULL/${KEY}__${b}__seed_${s}/${method}"
            mkdir -p "$out"
            
            # Skip if manifest exists and is complete
            MANIF=""
            case "$method" in
                certaindex_mid) MANIF="$out/probe_manifest.json" ;;
                tje) MANIF="$out/trigger_manifest.json" ;;
                deer) MANIF="$out/trial_manifest.json" ;;
            esac
            if [[ -f "$MANIF" ]]; then
                echo "[$total/9] $method $b seed$s: cached"
                done=$((done+1))
                continue
            fi
            
            echo "[$total/9] $method $b seed$s: collecting"
            CMD=("$PY" -m "benchmark.FalseConsensus.related_work.${method}"
                --main-run "$main_run" --output "$out" --url "$URL"
                --model "$MODEL" --model-revision "$REV" --split-manifest "$SM"
                --workers "$WORKERS")
            if [[ "$method" == "tje" ]]; then
                CMD+=(--max-model-len 34816 --readout-cap 8192)
            fi
            
            env LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
                LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
                HF_HOME=/localdata/dzhaoah/hf-cache \
                "${CMD[@]}" > "$FULL/_runtime/logs/${KEY}_${method}_${b}_seed${s}.log" 2>&1 || {
                echo "  FAILED rc=$?"
                failed=$((failed+1))
                continue
            }
            done=$((done+1))
        done
    done
done
echo "=== $KEY test baselines: $done/$total ok, $failed failed ==="
[[ $failed -eq 0 ]]
