# Teammate prompt：Governor v2 held-out 32B confirmation

在 4×RTX 5090（每卡 32GB）、系统内存至少 128GB、可用磁盘至少 200GB 的 Vast
实例上，只执行 Governor v2 的 held-out-scale confirmation：
`deepseek-ai/DeepSeek-R1-Distill-Qwen-32B`，seed 45。配置唯一来源是
`benchmark/FalseConsensus/governor_v2/heldout_32b_config.json` 与
`protocol.json`。

必须遵守以下边界：

1. 先运行 `preflight.py`，验证 protocol/split hash，再用 3 道题做真实 vLLM smoke。
2. 以 BF16、tensor parallel 4、`max-model-len=49152` 启动服务。正式结果禁止量化和
   CPU offload。
3. 必须等 development 阶段产生 `frozen_rules.json` 后才能开始。32B 的轨迹、test
   或 external-stress 结果绝不能进入 sweep、select、阈值选择或 cap 修改。
4. 共运行 434 条主轨迹：MATH500 test 100、GSM8K test 264、AMC23 external 40、
   AIME24 external 30；seed 固定为 45。
5. 默认从 `confirmation_matrix_base64.jsonl` 运行，并始终传
   `--model deepseek-ai/DeepSeek-R1-Distill-Qwen-32B`。只有冻结规则或其预注册消融
   包含 interval=32 时，才改用 `confirmation_matrix_with32.jsonl`。
6. 顺序为 main → base probe → 必要时 offset probe → frozen-rule evaluate。所有
   runner 必须可恢复；不得删除半成品或覆盖设置不同的目录。
7. 持续核对题数、cap rate、probe 完整性、token accounting、GPU 信息、commit 与
   manifest hash。完成后同步全部原始 JSON、manifest、日志和评估表，并提交简洁的
   handoff 总结。

服务命令：

```bash
vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --host 0.0.0.0 --port 18000 --dtype bfloat16 \
  --tensor-parallel-size 4 --max-model-len 49152 \
  --gpu-memory-utilization 0.90
```

正式 collection（根据冻结规则二选一）：

```bash
python benchmark/FalseConsensus/governor_v2/run_matrix.py \
  --matrix benchmark/FalseConsensus/governor_v2/generated/confirmation_matrix_base64.jsonl \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-32B --execute
```

或：

```bash
python benchmark/FalseConsensus/governor_v2/run_matrix.py \
  --matrix benchmark/FalseConsensus/governor_v2/generated/confirmation_matrix_with32.jsonl \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-32B --execute
```

预计耗时：下载与 smoke 约 1–3 小时；base64 collection 约 12–24 小时；若需要完整
32-grid，约 20–40 小时；离线评估约 0.5–2 小时。实际值主要由平均思维长度、
vLLM prefix-cache 命中率和 provider 的多卡互联决定。建议分别预留 24 小时或 48
小时，不要按理论峰值吞吐租极短实例。
