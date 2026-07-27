# CertaIndex baseline：development 本地回放

## 结论与口径

本次对 18 个完整 development 环境、2736 条 model-seed-problem 轨迹进行了 CPU-only 回放；没有模型调用，也没有读取 test。规则忠实采用公开 Dynasor `effort_level('mid')` 的停止条件：每 64 个主生成 token 检查一次，最近 3 个答案均非空、均无显式犹豫词，且按项目数学等价判定属于同一答案类时停止。

**重要限制：这是 prompt-adapted baseline，不是端到端 faithful reproduction。** 原实现使用 CertaIndex 顿悟式 suffix 和 20-token probe；本次使用已采集的 `simple@32`。因此方法 ID 明确写为 `certaindex_mid_stop_logic_on_simple32`。

Token saving 以 full generation 的主输出 token 为分母；方法成本包含停止前所有主输出 token 与 probe 输出 token。probe prompt token 单列，不混入 generated-token saving。准确率差定义为 CertaIndex − full，正数表示提高。区间为按 seed、再按题目重采样的成对 hierarchical bootstrap（10,000 次）。

## 主对比口径：dev 跨 seed 汇总

| Model | Benchmark | N | Full acc. | CertaIndex acc. | Δacc. (95% CI) | Token saving (95% CI) | Stop rate | Avg probe calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | aime24 | 18 | 83.33% | 5.56% | -77.78pp [-94.44, -55.56] | +85.76% [+77.37, +92.56] | 100.00% | 26.9 |
| Qwen3-8B | amc23 | 24 | 83.33% | 8.33% | -75.00pp [-91.67, -54.17] | +90.95% [+86.38, +94.15] | 100.00% | 12.3 |
| Qwen3-8B | math500 | 300 | 89.33% | 44.00% | -45.33pp [-51.67, -38.67] | +89.99% [+88.45, +91.38] | 99.67% | 7.3 |
| DeepSeek-R1-Distill-Qwen-7B | aime24 | 18 | 61.11% | 22.22% | -38.89pp [-61.11, -16.67] | +55.97% [+32.86, +81.25] | 100.00% | 81.3 |
| DeepSeek-R1-Distill-Qwen-7B | amc23 | 24 | 87.50% | 29.17% | -58.33pp [-79.17, -37.50] | +74.61% [+55.32, +86.29] | 100.00% | 27.7 |
| DeepSeek-R1-Distill-Qwen-7B | math500 | 300 | 91.67% | 55.67% | -36.00pp [-42.00, -30.00] | +80.94% [+77.59, +83.94] | 97.67% | 10.0 |

## 诊断口径：train+dev 跨 seed 汇总

| Model | Benchmark | N | Full acc. | CertaIndex acc. | Δacc. | Token saving | Stop rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | aime24 | 72 | 72.22% | 8.33% | -63.89pp | +83.19% | 100.00% |
| Qwen3-8B | amc23 | 96 | 84.38% | 27.08% | -57.29pp | +90.81% | 100.00% |
| Qwen3-8B | math500 | 1200 | 90.75% | 45.92% | -44.83pp | +89.71% | 99.50% |
| DeepSeek-R1-Distill-Qwen-7B | aime24 | 72 | 47.22% | 22.22% | -25.00pp | +73.90% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | amc23 | 96 | 84.38% | 35.42% | -48.96pp | +76.57% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | math500 | 1200 | 89.83% | 51.17% | -38.67pp | +80.94% | 98.25% |

在 `simple@32` 上，CertaIndex `mid` 停止逻辑几乎总会触发，因此换来很大的 token saving，但准确率明显下降。这个结果只能说明停止逻辑直接迁移到本项目 simple probe 时过于激进；它不能替代 CertaIndex 原 prompt/cap 的 faithful GPU 复现。

## 可复现性

- `details.jsonl`：逐轨迹的停止点、交付正确性与 token accounting。
- `metrics.csv`：逐 split/model/benchmark/seed 环境及跨 seed 汇总。
- `manifest.json`：方法定义、输入文件 SHA-256、覆盖率和运行参数。
