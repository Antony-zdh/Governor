# DEER-inspired Online Dev 结果

Seed 42 的 exploratory Dev 评估；两个 BF16 模型、三个 benchmark，所有推理、probe 与 verification branch 均在线执行。

## 结论

按 benchmark 等权宏平均，DEER-inspired 达到 **79.11% accuracy / 43.69% fair token saving**。相较在线 DEER，准确率提高 +0.94%，token saving 提高 +15.37%。

| 方法 | Macro accuracy | 相对 Full | Fair token saving |
|---|---:|---:|---:|
| DEER-inspired | 79.11% | -0.36% | 43.69% |
| Online DEER | 78.17% | -1.31% | 28.32% |
| 差值 | +0.94% | - | +15.37% |

Fair token saving 计入 main generation、probe、verification 与 readout 的输出 token；不包含输入 prompt/prefill 成本。

## 方法

- **DEER-inspired**：1024 main tokens 后在 `Wait` 处 probe；前 10 次 dense，此后保持至少 512-token 间隔。置信度 >0.995 直接提交；>0.97 进入最多 64-token 的 retained verification branch，Stage-2 >0.99 且答案一致时提交。
- **Online DEER**：从首个 `Wait` 起最多 probe 10 次；置信度 >0.95 后 greedy readout。两种方法共享 online engine、prompt、采样与 seed policy。

## 分模型结果

| 模型 | 方法 | Macro accuracy | 相对 Full | Fair saving |
|---|---|---:|---:|---:|
| DeepSeek-7B | DEER-inspired | 72.67% | -3.50% | 41.78% |
| DeepSeek-7B | Online DEER | 78.78% | +2.61% | 36.89% |
| Qwen3-8B | DEER-inspired | 85.56% | +2.78% | 45.59% |
| Qwen3-8B | Online DEER | 77.56% | -5.22% | 19.74% |

Qwen3 上 DEER-inspired 同时提高 accuracy 与 saving；DeepSeek 上获得较小的 saving 增益，但 accuracy 下降，说明当前阈值仍存在模型依赖。

## 不确定性与配对结果

- Benchmark-stratified paired bootstrap（10,000 次）：accuracy 差值 +0.97%，95% CI [-10.50%, +12.56%]；尚不能确认 accuracy 优势。
- Token-saving 差值 +15.32%，95% CI [+7.33%, +22.93%]；区间稳定为正。
- 逐题 pooled 配对：相对 Online DEER，accuracy +6.14%，平均少生成 685 tokens/题。
- 相对 existing full 的近似 counterfactual：accuracy +0.88%，平均少生成 2536 tokens/题；因在线多请求改变采样路径，此项不是严格配对。
- Pooled 汇总受 MATH500 数量主导：DEER-inspired 为 89.47% / 38.09%，Online DEER 为 83.33% / 39.81%；因此主文优先使用 benchmark 等权宏平均。

## 行为与完整性

- 审计状态 `complete`：456/456 条结果齐全，零 infrastructure error，token accounting 可重算。
- 126/228 题 fast commit；35 次 verification branch 中 30 次提交；2 题 capped。
- 共观察 3117 个 `Wait`；dense/sparse probes 为 742/283，512-gap 跳过 1327 次。

## 限制

- 仅一个 seed；AMC23（8 题）与 AIME24（6 题）样本很小，accuracy CI 较宽。
- 本轮未读取 Test/confirmation，也未回溯修改 Governor Pareto sweep。
- 结论可支持“显著改善 Online DEER 的 token trade-off”，但跨模型稳定性仍需 Test 与更多 seed 验证。

详细的逐环境指标、逐题记录与 bootstrap 数据分别见 `environment_metrics.csv`、`per_problem.csv` 和 `bootstrap.json`。