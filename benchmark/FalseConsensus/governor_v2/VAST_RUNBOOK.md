# Governor v2：Vast RTX 5090 执行清单

## 0. 不可变边界

- 开发阶段：DeepSeek-R1-Distill-Qwen-7B、Qwen3-8B；MATH500/GSM8K
  的 train+dev；seeds 42/43/44。
- 确认阶段：test 与 AMC23/AIME24 external stress；开发模型用
  seeds 45/46/47；Llama-8B 和 Distill-Qwen-32B 只用 seed 45。
- Llama-8B/32B、test、external stress 不得进入 sweep/select。
- 32B BF16 权重约 65GB，另需 32K KV cache 与 vLLM 开销，正式运行使用
  4×RTX 5090（tensor parallel 4）。若只租一张卡，先完成全部开发阶段及
  Llama-8B 确认，32B 留到四卡实例；不能用量化或 CPU offload 结果冒充正式
  BF16 对照。
- 当前执行明确暂缓 32B，由 teammate 按 `HELDOUT_32B_PROMPT.md` 和
  `heldout_32b_config.json` 后续完成；本轮不要启动它。

## 1. 开机后的硬件与代码门禁

```bash
nvidia-smi -L
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
df -h .
git status --short
python -m pip install -e .
python -c "import vllm; print(vllm.__version__)"
python -m unittest benchmark.FalseConsensus.governor_v2.tests.test_governor_v2 -v
```

确认 `generated/split_manifest.json`、`problem_ids/` 和两阶段 matrix 已同步。重新生成时，
必须验证 split manifest 的 SHA-256 与本机一致，不能在收集部分结果后重切分。
GSM8K 的已物化文件随代码同步，以保证 source hash 不变；29MB 候选规则默认不入库，
因此 Git 同步后先执行：

```bash
python benchmark/FalseConsensus/governor_v2/prepare_rules.py expand
python benchmark/FalseConsensus/governor_v2/preflight.py
```

## 2. 每个模型先做真实服务 smoke test

建议实例磁盘至少 200GB、系统内存至少 128GB。服务端口固定为 `18000`，模型名必须
与 protocol 完全一致。8B/7B 用单卡；32B 用四卡：

```bash
vllm serve "$MODEL_ID" --host 0.0.0.0 --port 18000 \
  --dtype bfloat16 --max-model-len 49152 \
  --gpu-memory-utilization 0.90

vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --host 0.0.0.0 --port 18000 --dtype bfloat16 \
  --tensor-parallel-size 4 --max-model-len 49152 \
  --gpu-memory-utilization 0.90
```

先检查 `/v1/models`，再从相应 matrix 复制一条 main 命令，临时加
`--start 0 --end 3` 并改到独立 smoke 输出目录；随后对这 3 条跑 dense probe。
验收条件：

- 三条均产生合法 JSON，模型模板无报错；
- `main_token_count_recorded` 与 re-encoded token 数没有系统性大偏差；
- probe position、答案抽取、token accounting 均非空；
- 16K/32K `max_tokens` 请求不因 context 或显存配置立即失败。

smoke 不通过时不得批量启动。

## 3. 正式执行顺序

1. 按 `generated/development_matrix.jsonl` 依赖顺序跑 main → base probe →
   offset probe。命令可重入，已有同配置结果会跳过。

   ```bash
   python benchmark/FalseConsensus/governor_v2/run_matrix.py \
     --matrix benchmark/FalseConsensus/governor_v2/generated/development_matrix.jsonl \
     --model "$MODEL_ID" --execute
   ```
2. 检查 12 个环境目录的轨迹数是否分别等于 problem-id 文件行数，并检查所有
   probe manifest 完整。
3. 将 22,464 条规则分成 8 个 CPU shard 跑 `replay_rules.py sweep`，随后
   `select` 生成 `frozen_rules.json`。
4. 记录 frozen manifest SHA-256。到此之前不要启动 confirmation。
5. 若冻结规则/消融含 interval=32，使用 `confirmation_matrix_with32.jsonl`；
   否则使用 `confirmation_matrix_base64.jsonl`。
6. 跑 `replay_rules.py evaluate`。该命令只接受 frozen manifest，并校验 protocol
   与 split hash；失败时先定位不一致，不能重选规则。

## 4. 进度、恢复与结果核对

每完成一个环境，至少记录：

- main 题数、自然结束数、cap 数和 realized cap rate；
- base/offset probe 文件数、总 probe 数；
- 失败/重试题号；
- 模型、seed、capture cap、协议版本及 git commit。

不要删除半成品目录。相同设置可直接重跑补齐；若 manifest 报设置不一致，使用新的明确
目录名，保留旧结果用于审计。主轨迹结束后先同步一份远端备份，再开始 probe。

最终必须同时保留：

- `run_manifest.json` / `probe_manifest.json`；
- 每题 main 与 probe JSON；
- split manifest、candidate rules、sweep shards；
- frozen rules 与 confirmation metrics；
- 服务启动命令、GPU 信息、代码 commit 和异常日志。
