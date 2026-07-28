#!/usr/bin/env bash
source /localdata/dzhaoah/miniforge3/etc/profile.d/conda.sh
conda activate gov
export LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6
export LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64
export CUDA_HOME=/usr/local/cuda-13.0.0
export PATH=$CUDA_HOME/bin:$PATH
export HF_HOME=/localdata/dzhaoah/hf-cache
export VLLM_LOGGING_LEVEL=WARNING
export CUDA_VISIBLE_DEVICES=0
exec vllm serve /localdata/dzhaoah/hf-cache/hub/models--deepseek-ai--DeepSeek-R1-Distill-Qwen-7B/snapshots/916b56a44061fd5cd7d6a8fb632557ed4f724f60 \
  --served-model-name deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  --host 127.0.0.1 --port 18000 --dtype bfloat16 \
  --enable-prefix-caching --gpu-memory-utilization 0.88 \
  --max-model-len 49152 --max-num-seqs 8 --api-key token-abc123
