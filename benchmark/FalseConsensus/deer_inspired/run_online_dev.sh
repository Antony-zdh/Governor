#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "usage: $0 <model> <revision> <vllm-url> <output-root> [workers]" >&2
  exit 2
fi

MODEL=$1
REVISION=$2
URL=$3
OUTPUT_ROOT=$4
WORKERS=${5:-2}
CONFIG=benchmark/FalseConsensus/deer_inspired/configs/online_dev_v1.json

case "$MODEL" in
  deepseek-ai/DeepSeek-R1-Distill-Qwen-7B) MODEL_KEY=deepseek ;;
  Qwen/Qwen3-8B) MODEL_KEY=qwen3 ;;
  *) echo "formal model not authorized: $MODEL" >&2; exit 2 ;;
esac

for METHOD in deer_inspired_online_v1 deer_online_reference; do
  for BENCHMARK in math500 amc23 aime24; do
    python -m benchmark.FalseConsensus.deer_inspired.online_controller \
      --method "$METHOD" \
      --config "$CONFIG" \
      --model "$MODEL" \
      --model-revision "$REVISION" \
      --benchmark "$BENCHMARK" \
      --seed 42 \
      --url "$URL" \
      --workers "$WORKERS" \
      --server-command "${VLLM_SERVER_COMMAND:-}" \
      --output "$OUTPUT_ROOT/$METHOD/${MODEL_KEY}__${BENCHMARK}__seed_42"
  done
done
