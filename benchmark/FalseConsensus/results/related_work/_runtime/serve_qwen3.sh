#!/usr/bin/env bash
set -u
source /localdata/dzhaoah/miniforge3/etc/profile.d/conda.sh && conda activate gov
export LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6
export LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64
export CUDA_HOME=/usr/local/cuda-13.0.0
export PATH="$CUDA_HOME/bin:$PATH"
export HF_HOME=/localdata/dzhaoah/hf-cache VLLM_LOGGING_LEVEL=WARNING CUDA_VISIBLE_DEVICES=1
Q3_SNAP=/localdata/dzhaoah/hf-cache/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218
exec vllm serve "$Q3_SNAP" --served-model-name Qwen/Qwen3-8B --host 127.0.0.1 --port 18001 --dtype bfloat16 --enable-prefix-caching --gpu-memory-utilization 0.95 --max-model-len 34816 --max-num-seqs 8 --api-key token-abc123
