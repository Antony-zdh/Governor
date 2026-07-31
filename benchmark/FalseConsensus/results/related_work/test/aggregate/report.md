# Governor v2 相关工作基线实验报告（Test）

## 1. 执行结论

全量数据已就绪（2052 行，3 方法 × 684 轨迹/方法）。

完整主结果显示：准确率保留最好的是 DEER / Qwen/Qwen3-8B（宏平均 Δacc=-0.33pp）；公平 token 节省最高的是 CertaIndex mid / Qwen/Qwen3-8B（91.59%）。存在≤3pp 准确率损失的相关工作点。 这些结论只针对冻结轨迹复现，不反推原论文端到端结果。

## 2. 实验范围与复现标签

- **模型**: DeepSeek-R1-Distill-Qwen-7B (rev `916b56a`), Qwen3-8B (rev `b968826`)

- **基准**: MATH500 (400/env), AMC23 (32/env), AIME24 (24/env)

- **种子**: 45, 46, 47

- **环境数**: 18 (2 模型 × 3 基准 × 3 种子), **轨迹总数**: 684

- **阶段**: confirmation (test only)

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

- 每方法行数: {'certaindex_mid_frozen': 684, 'deer_frozen': 684, 'tje_frozen': 684}

- 测试行数: 2052


## 5. Test 模型×基准表

| 模型 | 基准 | 方法 | 准确率 | 全量准确率 | 准确率差(pp) | 95%CI(准确率差) | 全量token节省 | 95%CI(token节省) | 主token节省 | 停止率 | 探针开销(token) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen/Qwen3-8B | aime24 | CertaIndex mid | 0.00% | 83.33% | -83.33 | [-100.00, -66.67] | 92.21% | [86.71, 96.27] | 92.90% | 100.00% | 86.2 |
| Qwen/Qwen3-8B | amc23 | CertaIndex mid | 41.67% | 87.50% | -45.83 | [-66.67, -25.00] | 92.03% | [87.92, 94.55] | 92.84% | 100.00% | 53.4 |
| Qwen/Qwen3-8B | math500 | CertaIndex mid | 47.00% | 97.33% | -50.33 | [-56.67, -44.00] | 90.52% | [89.10, 91.71] | 91.45% | 100.00% | 47.2 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | aime24 | CertaIndex mid | 5.56% | 72.22% | -66.67 | [-88.89, -38.89] | 82.40% | [62.17, 92.79] | 83.83% | 100.00% | 146.7 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | amc23 | CertaIndex mid | 58.33% | 83.33% | -25.00 | [-45.83, -4.17] | 90.73% | [84.44, 94.22] | 91.45% | 100.00% | 37.1 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | math500 | CertaIndex mid | 49.00% | 94.67% | -45.67 | [-51.67, -39.33] | 83.79% | [81.23, 85.92] | 85.27% | 99.67% | 57.1 |
| Qwen/Qwen3-8B | aime24 | DEER | 83.33% | 83.33% | 0.00 | [0.00, 0.00] | 1.79% | [-1.84, 12.65] | 3.66% | 5.56% | 233.4 |
| Qwen/Qwen3-8B | amc23 | DEER | 87.50% | 87.50% | 0.00 | [0.00, 0.00] | 26.57% | [11.11, 48.95] | 33.37% | 66.67% | 448.5 |
| Qwen/Qwen3-8B | math500 | DEER | 96.33% | 97.33% | -1.00 | [-2.33, 0.00] | 34.85% | [30.06, 40.20] | 43.87% | 78.67% | 461.4 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | aime24 | DEER | 61.11% | 72.22% | -11.11 | [-27.78, 0.00] | 5.94% | [-2.64, 19.30] | 10.19% | 22.22% | 435.5 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | amc23 | DEER | 79.17% | 83.33% | -4.17 | [-20.83, 16.67] | 38.49% | [16.99, 64.19] | 44.31% | 75.00% | 301.2 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | math500 | DEER | 81.33% | 94.67% | -13.33 | [-18.00, -9.33] | 42.34% | [35.24, 50.26] | 54.58% | 82.33% | 471.6 |
| Qwen/Qwen3-8B | aime24 | TJE | 83.33% | 83.33% | 0.00 | [0.00, 0.00] | -1.66% | [-1.98, -1.38] | 0.00% | 0.00% | 207.2 |
| Qwen/Qwen3-8B | amc23 | TJE | 83.33% | 87.50% | -4.17 | [-16.67, 0.00] | 0.10% | [-1.98, 5.29] | 4.32% | 33.33% | 278.5 |
| Qwen/Qwen3-8B | math500 | TJE | 92.67% | 97.33% | -4.67 | [-7.33, -2.33] | 0.52% | [-0.84, 2.42] | 6.72% | 42.67% | 317.1 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | aime24 | TJE | 27.78% | 72.22% | -44.44 | [-83.33, 0.00] | 60.44% | [35.51, 75.73] | 82.32% | 100.00% | 2242.3 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | amc23 | TJE | 83.33% | 83.33% | 0.00 | [-16.67, 16.67] | 73.08% | [61.02, 80.71] | 77.24% | 95.83% | 215.5 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | math500 | TJE | 87.00% | 94.67% | -7.67 | [-12.00, -3.67] | 58.51% | [52.94, 63.52] | 68.94% | 84.67% | 401.9 |


## 6. Test 宏观视图（不使MATH500按样本数主导）

| 方法 | 模型 | 基准数 | 准确率 | 准确率差(pp) | 全量token节省 | 主token节省 | 停止率 |
|---|---|---|---|---|---|---|---|
| CertaIndex mid | Qwen/Qwen3-8B | 3 | 29.56% | -59.83 | 91.59% | 92.40% | 100.00% |
| CertaIndex mid | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 3 | 37.63% | -45.78 | 85.64% | 86.85% | 99.89% |
| DEER | Qwen/Qwen3-8B | 3 | 89.06% | -0.33 | 21.07% | 26.97% | 50.30% |
| DEER | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 3 | 73.87% | -9.54 | 28.92% | 36.36% | 59.85% |
| TJE | Qwen/Qwen3-8B | 3 | 86.44% | -2.94 | -0.35% | 3.68% | 25.33% |
| TJE | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 3 | 66.04% | -17.37 | 64.01% | 76.17% | 93.50% |


### 6.1 Test pooled per-seed sensitivity

| Seed | Method | n | Accuracy | Accuracy diff | All-generated saving | Stop rate |
|---:|---|---:|---:|---:|---:|---:|
| 45 | CertaIndex mid | 228 | 45.61% | -49.56 pp | 88.71% | 100.00% |
| 46 | CertaIndex mid | 228 | 46.05% | -49.12 pp | 86.63% | 99.56% |
| 47 | CertaIndex mid | 228 | 45.61% | -46.93 pp | 88.51% | 100.00% |
| 45 | DEER | 228 | 86.84% | -8.33 pp | 35.09% | 76.32% |
| 46 | DEER | 228 | 89.04% | -6.14 pp | 32.67% | 75.00% |
| 47 | DEER | 228 | 86.84% | -5.70 pp | 32.39% | 77.63% |
| 45 | TJE | 228 | 87.72% | -7.46 pp | 28.02% | 63.60% |
| 46 | TJE | 228 | 88.16% | -7.02 pp | 22.51% | 62.72% |
| 47 | TJE | 228 | 86.84% | -5.70 pp | 27.63% | 62.72% |


## 7. Accuracy-compute Pareto

| 模型 | 方法 | 宏平均准确率 | 相对 Full | 公平 token 节省 | 非支配 |
|---|---|---:|---:|---:|---|
| Qwen/Qwen3-8B | Full generation | 89.39% | +0.00pp | 0.00% | 是 |
| Qwen/Qwen3-8B | CertaIndex mid | 29.56% | -59.83pp | 91.59% | 是 |
| Qwen/Qwen3-8B | DEER | 89.06% | -0.33pp | 21.07% | 是 |
| Qwen/Qwen3-8B | TJE | 86.44% | -2.94pp | -0.35% | 否 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | Full generation | 83.41% | +0.00pp | 0.00% | 是 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | CertaIndex mid | 37.63% | -45.78pp | 85.64% | 是 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | DEER | 73.87% | -9.54pp | 28.92% | 是 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | TJE | 66.04% | -17.37pp | 64.01% | 是 |

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
  - matched-accuracy（损失≤1pp）最省的是 DEER：21.07%，Δacc=-0.33pp。
  - matched-accuracy（损失≤3pp）最省的是 DEER：21.07%，Δacc=-0.33pp。
  - matched-accuracy（损失≤5pp）最省的是 DEER：21.07%，Δacc=-0.33pp。
  - 最近的 matched-token 对是 DEER 与 TJE（节省差 21.42%）；准确率差为 +2.61pp。
- **deepseek-ai/DeepSeek-R1-Distill-Qwen-7B**：
  - matched-accuracy（损失≤1pp）：没有相关工作基线满足。
  - matched-accuracy（损失≤3pp）：没有相关工作基线满足。
  - matched-accuracy（损失≤5pp）：没有相关工作基线满足。
  - 最近的 matched-token 对是 CertaIndex mid 与 TJE（节省差 21.63%）；准确率差为 -28.41pp。
- 每个方法只有一个预注册主 operating point；因此不存在连续阈值曲线时，不能把“最近点”解释为严格的等 token 因果比较。


## 9. 公平计费说明

**两种成本视图**:

1. **论文式** `main_tokens_through_stop` - 冻结推理长度到停止（或全长如无停止）

2. **公平全量** `all_generated_tokens` = 主停止长度 + 所有探针/试错/读出输出token

探针/试错/读出 **prompt token**（重发前缀）单独报告，不计入全量生成token。


**配对分层 bootstrap**: 10000 样本, 种子 `20260727` - 先重采样种子，再在种子内重采样配对问题行。仅在 test-pooled 与方法汇总视图运行（非逐环境）。


## 10. 失败、截断与解析诊断

| 模型 | 方法 | 行数 | 辅助调用 | 无效辅助响应 | capped/right-censored | 恢复截断 | 过度思考避免 | 辅助 wall time(s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen/Qwen3-8B | CertaIndex mid | 342 | 2478 | 194 (7.829%) | 0.000% | 100.000% | 100.000% | 1343.4 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | CertaIndex mid | 342 | 3292 | 116 (3.524%) | 0.000% | 99.708% | 99.708% | 1350.6 |
| Qwen/Qwen3-8B | DEER | 342 | 1920 | 63 (3.281%) | 3.801% | 73.977% | 73.977% | 6302.5 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | DEER | 342 | 1359 | 80 (5.887%) | 1.462% | 78.655% | 78.655% | 5588.6 |
| Qwen/Qwen3-8B | TJE | 342 | 7869 | 14 (0.178%) | 3.216% | 39.766% | 39.766% | 56466.3 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | TJE | 342 | 1456 | 11 (0.755%) | 0.000% | 86.257% | 86.257% | 5754.6 |

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

python -m benchmark.FalseConsensus.related_work.aggregate_all --inputs benchmark/FalseConsensus/results/related_work/test/_replay/*/replay_rows.jsonl --output-dir benchmark/FalseConsensus/results/related_work/test/aggregate --allow-test


# PDF渲染

bash benchmark/FalseConsensus/results/related_work/_runtime/render_pdf.sh

```


## 14. Artifact inventory

- 原始逐题结果：`benchmark/FalseConsensus/results/related_work/test/<model>__<benchmark>__seed_<seed>/<method>/`

- 54 个 replay：`benchmark/FalseConsensus/results/related_work/test/_replay/`

- 聚合 JSON：`benchmark/FalseConsensus/results/related_work/test/aggregate/aggregate.json`

- 环境/pooled/宏视图 CSV：`benchmark/FalseConsensus/results/related_work/test/aggregate/*.csv`

- Markdown 报告：`benchmark/FalseConsensus/results/related_work/test/aggregate/report.md`

- PDF 报告：`benchmark/FalseConsensus/results/related_work/test/aggregate/report.pdf`

- 运行/验证日志：`benchmark/FalseConsensus/results/related_work/test/_runtime/`
