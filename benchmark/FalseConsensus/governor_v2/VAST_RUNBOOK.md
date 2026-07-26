# Governor v2：8×A100-80GB 执行清单

## 0. 不可变边界

- 开发阶段：DeepSeek-R1-Distill-Qwen-7B、Qwen3-8B；MATH500、AMC23、AIME24
  的 train+dev；seeds 42/43/44。GSM8K 不进入本轮矩阵。
- 确认阶段：三个 benchmark 的 test；开发模型用
  seeds 45/46/47；Llama-8B 和 Distill-Qwen-32B 只用 seed 45。
- Llama-8B/32B 和 test 不得进入 sweep/select。
- 当前正式硬件是 8×A100-80GB；32B 使用其中 2 卡、tensor parallel 2。RTX 5090
  方案仅作为旧的 fallback 记录，不能用量化或 CPU offload 结果冒充正式 BF16 对照。
- 本轮包括 32B held-out scale confirmation；它只能在三个 development
  operating points 完成冻结后运行。

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
候选规则默认不入库，因此 Git 同步后先执行：

```bash
python benchmark/FalseConsensus/governor_v2/prepare_rules.py expand
python benchmark/FalseConsensus/governor_v2/preflight.py
```

## 2. 每个模型先做真实服务 smoke test

建议工作盘至少保留 500GB、系统内存至少 128GB。服务端口固定为 `18000`，模型名必须
与 protocol 完全一致。8B/7B 用单卡；32B 用两张 A100-80GB：

```bash
vllm serve "$MODEL_ID" --host 0.0.0.0 --port 18000 \
  --dtype bfloat16 --max-model-len "$MAX_MODEL_LEN" \
  --gpu-memory-utilization 0.90

vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --host 0.0.0.0 --port 18000 --dtype bfloat16 \
  --tensor-parallel-size 2 --max-model-len 49152 \
  --gpu-memory-utilization 0.90
```

`MAX_MODEL_LEN` 必须从 protocol 的模型项读取：Qwen3-8B 为 40,960，其余为
49,152。Qwen3 的 40,960 已为 32,768 输出保留 8,192 prompt 空间，本轮不启用
YaRN 或其他额外 RoPE scaling。

目标是每个模型的下载、启动和 smoke 合计控制在 15–30 分钟。先检查
`/v1/models`，再从相应 matrix 复制一条 main 命令，临时加
`--start 0 --end 3` 并改到独立 smoke 输出目录；随后对这 3 条依次跑 dense probe
和 adaptive probe。entropy smoke 必须确认 completions endpoint 支持
`echo=True` 的 prompt logprobs。
验收条件：

- 三条均产生合法 JSON，模型模板无报错；
- `main_token_count_recorded` 与 re-encoded token 数没有系统性大偏差；
- probe position、答案抽取、token accounting 均非空；
- 16K/32K `max_tokens` 请求不因 context 或显存配置立即失败。

smoke 不通过时不得批量启动。

## 3. 正式执行顺序

1. 按 `generated/development_matrix.jsonl` 跑两个开发模型的 main → interval-64
   base probe → adaptive event bank。建议 GPU 0–3 放四个 DeepSeek-7B replicas、
   GPU 4–7 放四个 Qwen3-8B replicas，同时执行；命令可重入。

   ```bash
   python benchmark/FalseConsensus/governor_v2/run_matrix.py \
     --matrix benchmark/FalseConsensus/governor_v2/generated/development_matrix.jsonl \
     --model "$MODEL_ID" --execute
   ```
2. 检查 18 个 development 环境目录的轨迹数是否分别等于 problem-id 文件行数，并检查 dense 与
   adaptive 两类 probe manifest 完整；adaptive 中落在 64-grid 的位置应标记
   `reused_from=dense_simple32`。
3. 把 development 结果同步回本地。CPU 工作不占 Vast：本地将 17,712 条规则分成
   8 个 shard 跑 `replay_rules.py sweep`，再 `select` 生成 `frozen_rules.json`。
   `select` 必须得到 conservative、balanced、token-efficient 三个互异的非支配
   rule ID；否则停止并报告，不得放宽门槛或查看 test。
4. 记录 frozen manifest SHA-256 并同步回 Vast。到此之前不要启动 confirmation。
5. 在规则冻结后运行完整 `confirmation_matrix_base64.jsonl`。32B 占用两张
   A100-80GB，其余 6 卡运行 DeepSeek-7B、Qwen3-8B 和 Llama-8B replicas。
6. 把 confirmation 结果同步回本地，再运行 `replay_rules.py evaluate`。该命令
   只接受 frozen manifest，并校验 protocol
   与 split hash；失败时先定位不一致，不能重选规则。

## 4. 进度、恢复与结果核对

每完成一个环境，至少记录：

- main 题数、自然结束数、cap 数和 realized cap rate；
- base/adaptive probe 文件数、总 probe 数、每类 trigger 数与复用数；
- 失败/重试题号；
- 模型、seed、capture cap、协议版本及 git commit。

不要删除半成品目录。相同设置可直接重跑补齐；若 manifest 报设置不一致，使用新的明确
目录名，保留旧结果用于审计。主轨迹结束后先同步一份远端备份，再开始 probe。

最终必须同时保留：

- `run_manifest.json` / `probe_manifest.json`；
- 每题 main、dense probe 与 adaptive probe JSON；
- split manifest、candidate rules、sweep shards；
- frozen rules 与 confirmation metrics；
- 服务启动命令、GPU 信息、代码 commit 和异常日志。

## 5. 8 小时调度目标

- 0–0.4h：环境检查、缓存模型启动和每模型 3-question smoke。
- 0.4–3.5h：4 个 DeepSeek-7B replica 与 4 个 Qwen3-8B replica 并行完成
  development main → dense → adaptive。
- development 完成即进行 CPU sweep/select；目标 0.3–0.8h，并冻结 manifest。
- 3.8–7.0h：重排 GPU，2 卡运行 32B，其余 6 卡运行三个小模型的 confirmation。
- 7.0–8.0h：补失败任务、校验 manifest、同步结果与离线 evaluate。
- 不以跳过题目、减少 seed 或查看 test 后重选规则来满足 timebox。
