# Governor v2 相关工作基线实验报告

## 1. 执行结论

全量数据已就绪（8208 行，3 方法 × 2736 轨迹/方法）。

完整主结果显示：准确率保留最好的是 DEER / Qwen/Qwen3-8B（宏平均 Δacc=+0.78pp）；公平 token 节省最高的是 CertaIndex mid / Qwen/Qwen3-8B（90.10%）。存在≤3pp 准确率损失的相关工作点。 这些结论只针对冻结轨迹复现，不反推原论文端到端结果。

## 2. 实验范围与复现标签

- **模型**: DeepSeek-R1-Distill-Qwen-7B (rev `916b56a`), Qwen3-8B (rev `b968826`)

- **基准**: MATH500 (400/env), AMC23 (32/env), AIME24 (24/env)

- **种子**: 42, 43, 44

- **环境数**: 18 (2 模型 × 3 基准 × 3 种子), **轨迹总数**: 2736

- **阶段**: development (train+dev), 无测试数据

- **协议版本**: `governor-v2-preregistered-2026-07-27.10`

- **拆分种子**: `20260726`


## 3. 方法/协议表

| 方法 | 模块 | 来源(pin) | 复现类别 |
|---|---|---|---|
| CertaIndex faithful mid | `certaindex_mid.py` | `dynasor/core/cot.py` @ `dbe76ad` | 忠实prompt+停止规则; 冻结轨迹时间 |
| TJE | `tje.py` | https://aclanthology.org/2026.findings-eacl.263/ (Fig.2+§2.2) | 冻结轨迹TJE复现 |
| DEER | `deer.py` | https://github.com/iie-ycx/DEER @ `c9dd19f` | 冻结轨迹DEER复现 |


## 4. 覆盖率

- 方法数: 3

- 环境数: 54

- 每方法行数: {'certaindex_mid_frozen': 2736, 'deer_frozen': 2736, 'tje_frozen': 2736}

- 测试行数: 0


## 5. Dev 模型×基准表

| 模型 | 基准 | 方法 | 准确率 | 全量准确率 | 准确率差(pp) | 95%CI(准确率差) | 全量token节省 | 95%CI(token节省) | 主token节省 | 停止率 | 探针开销(token) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen/Qwen3-8B | aime24 | CertaIndex mid | 0.00% | 83.33% | -83.33 | [-100.00, -66.67] | 90.49% | [81.49, 96.70] | 91.30% | 100.00% | 106.8 |
| Qwen/Qwen3-8B | amc23 | CertaIndex mid | 0.00% | 83.33% | -83.33 | [-95.83, -66.67] | 89.94% | [81.97, 95.68] | 90.65% | 100.00% | 66.8 |
| Qwen/Qwen3-8B | math500 | CertaIndex mid | 46.00% | 89.67% | -43.67 | [-50.00, -37.00] | 89.88% | [87.82, 91.52] | 91.06% | 99.33% | 62.0 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | aime24 | CertaIndex mid | 11.11% | 61.11% | -50.00 | [-77.78, -22.22] | 64.01% | [43.72, 82.88] | 66.80% | 100.00% | 357.7 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | amc23 | CertaIndex mid | 12.50% | 87.50% | -75.00 | [-91.67, -54.17] | 83.87% | [72.36, 91.89] | 85.01% | 100.00% | 85.5 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | math500 | CertaIndex mid | 48.00% | 90.67% | -42.67 | [-48.67, -36.67] | 82.16% | [78.42, 85.28] | 84.01% | 96.00% | 69.2 |
| Qwen/Qwen3-8B | aime24 | DEER | 83.33% | 83.33% | 0.00 | [0.00, 0.00] | 5.10% | [-0.52, 14.46] | 7.85% | 22.22% | 365.4 |
| Qwen/Qwen3-8B | amc23 | DEER | 83.33% | 83.33% | 0.00 | [0.00, 0.00] | 10.37% | [1.91, 21.89] | 14.38% | 29.17% | 376.1 |
| Qwen/Qwen3-8B | math500 | DEER | 92.00% | 89.67% | 2.33 | [-0.33, 5.00] | 33.42% | [26.18, 41.03] | 41.87% | 72.67% | 445.3 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | aime24 | DEER | 61.11% | 61.11% | 0.00 | [0.00, 0.00] | 4.18% | [0.54, 11.96] | 6.19% | 38.89% | 257.1 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | amc23 | DEER | 83.33% | 87.50% | -4.17 | [-16.67, 0.00] | 16.39% | [5.71, 31.78] | 21.41% | 50.00% | 378.3 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | math500 | DEER | 80.33% | 90.67% | -10.33 | [-14.33, -6.33] | 39.92% | [31.85, 47.67] | 49.43% | 79.33% | 356.0 |
| Qwen/Qwen3-8B | aime24 | TJE | 83.33% | 83.33% | 0.00 | [0.00, 0.00] | -1.83% | [-2.23, -1.47] | 0.00% | 0.00% | 242.8 |
| Qwen/Qwen3-8B | amc23 | TJE | 83.33% | 83.33% | 0.00 | [-16.67, 16.67] | 4.36% | [-1.97, 14.89] | 7.45% | 20.83% | 289.5 |
| Qwen/Qwen3-8B | math500 | TJE | 88.33% | 89.67% | -1.33 | [-4.33, 1.33] | 3.57% | [0.23, 7.20] | 10.02% | 46.67% | 339.7 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | aime24 | TJE | 33.33% | 61.11% | -27.78 | [-50.00, -5.56] | 73.48% | [57.75, 84.65] | 89.42% | 100.00% | 2042.7 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | amc23 | TJE | 66.67% | 87.50% | -20.83 | [-45.83, 4.17] | 65.05% | [43.69, 77.40] | 79.11% | 100.00% | 1057.8 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | math500 | TJE | 82.00% | 90.67% | -8.67 | [-12.67, -5.00] | 56.47% | [50.21, 61.82] | 66.82% | 80.33% | 387.3 |


## 6. Dev 宏观视图（不使MATH500按样本数主导）

| 方法 | 模型 | 基准数 | 准确率 | 准确率差(pp) | 全量token节省 | 主token节省 | 停止率 |
|---|---|---|---|---|---|---|---|
| CertaIndex mid | Qwen/Qwen3-8B | 3 | 15.33% | -70.11 | 90.10% | 91.00% | 99.78% |
| CertaIndex mid | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 3 | 23.87% | -55.89 | 76.68% | 78.60% | 98.67% |
| DEER | Qwen/Qwen3-8B | 3 | 86.22% | 0.78 | 16.29% | 21.37% | 41.35% |
| DEER | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 3 | 74.93% | -4.83 | 20.16% | 25.68% | 56.07% |
| TJE | Qwen/Qwen3-8B | 3 | 85.00% | -0.44 | 2.03% | 5.82% | 22.50% |
| TJE | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 3 | 60.67% | -19.09 | 65.00% | 78.45% | 93.44% |


## 7. Accuracy-compute Pareto

| 模型 | 方法 | 宏平均准确率 | 相对 Full | 公平 token 节省 | 非支配 |
|---|---|---:|---:|---:|---|
| Qwen/Qwen3-8B | Full generation | 85.44% | +0.00pp | 0.00% | 否 |
| Qwen/Qwen3-8B | CertaIndex mid | 15.33% | -70.11pp | 90.10% | 是 |
| Qwen/Qwen3-8B | DEER | 86.22% | +0.78pp | 16.29% | 是 |
| Qwen/Qwen3-8B | TJE | 85.00% | -0.44pp | 2.03% | 否 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | Full generation | 79.76% | +0.00pp | 0.00% | 是 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | CertaIndex mid | 23.87% | -55.89pp | 76.68% | 是 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | DEER | 74.93% | -4.83pp | 20.16% | 是 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | TJE | 60.67% | -19.09pp | 65.00% | 是 |

“非支配”仅在同一模型的 Full + 三个相关工作主点内部计算；准确率越高、token 节省越高越好。


### 可用 Governor 探索点（非严格 matched 参考）

| 历史探索点 | 准确率 | 相对 Full | token 节省 |
|---|---:|---:|---:|
| Full | 80.67% | +0.00pp | 0.00% |
| Governor Conservative | 80.73% | +0.06pp | -4.41% |
| Governor Balanced-MATH | 80.67% | +0.00pp | 0.88% |
| Dynasor on simple@32 (adapted) | 69.73% | -10.94pp | 35.78% |
| Naive agreement | 64.40% | -16.27pp | 48.91% |

- 来源文件：`benchmark/FalseConsensus/report/report_final_eval_multiseed_2026-07-26.md`
- 来源 SHA-256：`9823062064fa479cffe018c6013659d8affd34ba54f8b5c9f10ed18ba6513556`

该表是历史三-seed MATH500 探索结果，模型/seed/任务构成与本报告的 18 个 development 环境不完全匹配；只用于定性定位，不能和上表作严格横向显著性比较。


## 8. Matched-accuracy / matched-token 解读

- **Qwen/Qwen3-8B**：
  - matched-accuracy（损失≤1pp）最省的是 DEER：16.29%，Δacc=+0.78pp。
  - matched-accuracy（损失≤3pp）最省的是 DEER：16.29%，Δacc=+0.78pp。
  - matched-accuracy（损失≤5pp）最省的是 DEER：16.29%，Δacc=+0.78pp。
  - 最近的 matched-token 对是 DEER 与 TJE（节省差 14.26%）；准确率差为 +1.22pp。
- **deepseek-ai/DeepSeek-R1-Distill-Qwen-7B**：
  - matched-accuracy（损失≤1pp）：没有相关工作基线满足。
  - matched-accuracy（损失≤3pp）：没有相关工作基线满足。
  - matched-accuracy（损失≤5pp）最省的是 DEER：20.16%，Δacc=-4.83pp。
  - 最近的 matched-token 对是 CertaIndex mid 与 TJE（节省差 11.68%）；准确率差为 -36.80pp。
- 每个方法只有一个预注册主 operating point；因此不存在连续阈值曲线时，不能把“最近点”解释为严格的等 token 因果比较。


## 9. 公平计费说明

**两种成本视图**:

1. **论文式** `main_tokens_through_stop` - 冻结推理长度到停止（或全长如无停止）

2. **公平全量** `all_generated_tokens` = 主停止长度 + 所有探针/试错/读出输出token

探针/试错/读出 **prompt token**（重发前缀）单独报告，不计入全量生成token。


**配对分层 bootstrap**: 10000 样本, 种子 `20260727` - 先重采样种子，再在种子内重采样配对问题行。仅在 dev-pooled + train+dev 视图运行（非逐环境）。


## 10. 失败、截断与解析诊断

| 模型 | 方法 | 行数 | 辅助调用 | 无效辅助响应 | capped/right-censored | 恢复截断 | 过度思考避免 | 辅助 wall time(s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen/Qwen3-8B | CertaIndex mid | 1368 | 11157 | 1164 (10.433%) | 0.000% | 99.342% | 99.342% | 3060.8 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | CertaIndex mid | 1368 | 16036 | 865 (5.394%) | 0.000% | 97.661% | 97.661% | 4060.1 |
| Qwen/Qwen3-8B | DEER | 1368 | 8072 | 277 (3.432%) | 4.825% | 70.175% | 70.175% | 16093.5 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | DEER | 1368 | 5945 | 258 (4.340%) | 3.874% | 75.512% | 75.512% | 13301.5 |
| Qwen/Qwen3-8B | TJE | 1368 | 32854 | 49 (0.149%) | 4.386% | 43.567% | 43.567% | 24448.6 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | TJE | 1368 | 5818 | 58 (0.997%) | 0.073% | 84.137% | 84.137% | 20685.0 |

`invalid_aux_responses` 是已完整记录的方法级失败（交付空答案并计错），不是丢行；8192-token TJE 与 4096-token DEER readout 触顶作为 capped/right-censored 诊断保留。请求错误、context overflow、缺行仍是硬失败。


## 11. 局限性

- TJE/DEER 为冻结轨迹复现，非端到端忠实运行（冻结轨迹 TJE/DEER 复现标签）

- TJE 的 `structured_outputs.choice` 约束改变了标签分布（vs 无约束），影响触发率

- AMC/AIME 样本量小（32/24），置信区间较宽

- 模型可能声称高置信但在固定读出 cap 内无法完成 boxed 答案；该结果按方法失败计错，不补用未来完整答案

- 历史 Governor 探索点与当前 18 环境网格不完全匹配，只可定性参照


## 12. 精确修订/哈希

- deepseek: model=`deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` rev=`916b56a44061fd5cd7d6a8fb632557ed4f724f60` endpoint=`http://127.0.0.1:18000/v1`

- qwen3: model=`Qwen/Qwen3-8B` rev=`b968826d9c46dd6066d109eabc6255188de91218` endpoint=`http://127.0.0.1:18001/v1`

- split manifest: `benchmark/FalseConsensus/governor_v2/generated/split_manifest.json`

- 每个 collector manifest 记录 source commit、prompt/config hash、输入 trajectory bank hash 与 split hash


## 13. 复现命令

```bash

# 验证冻结银行

python -m benchmark.FalseConsensus.related_work.preflight


# 全量收集（每模型）

bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh deepseek

bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh qwen3


# 后处理（replay + aggregate + report）

python -m benchmark.FalseConsensus.related_work.postprocess


# PDF渲染

bash benchmark/FalseConsensus/results/related_work/_runtime/render_pdf.sh

```


## 14. Artifact inventory

- 原始逐题结果：`benchmark/FalseConsensus/results/related_work/full/<model>__<benchmark>__seed_<seed>/<method>/`

- 54 个 replay：`benchmark/FalseConsensus/results/related_work/full/_replay/`

- 聚合 JSON：`benchmark/FalseConsensus/results/related_work/aggregate/aggregate.json`

- 环境/dev/train+dev/宏视图 CSV：`benchmark/FalseConsensus/results/related_work/aggregate/*.csv`

- Markdown 报告：`benchmark/FalseConsensus/results/related_work/aggregate/report.md`

- PDF 报告：`benchmark/FalseConsensus/results/related_work/aggregate/report.pdf`

- 运行/验证日志：`benchmark/FalseConsensus/results/related_work/full/_runtime/`
