# DEER-inspired Governor：Fast Path 与 Branch-and-Commit 设计备忘录

日期：2026-07-28

状态：独立研究提案，尚未纳入主实验协议

## 1. 范围与兼容性声明

本文记录一个独立的 DEER-inspired Governor 策略。它是论文的潜在增量贡献，不替代、覆盖或追溯修改现有 Governor Pareto sweep：

- 原 Pareto sweep 的候选规则、筛选标准、Train/Dev 结果和已选策略保持不变；
- DEER-inspired 策略使用独立配置、结果目录和报告；
- 最终比较时，把它作为原 Pareto Governor 策略之外的一个新增方法点；
- 只有完成独立 Train/Dev 评估后，才决定是否进入 Test confirmation。

因此，本文中的阈值与回放结果不能反向用于修改原 Pareto sweep。

## 2. 动机

DEER 在推理中的 `Wait` 位置生成一个短 trial answer，并根据该答案 token 的生成概率计算 confidence。当 confidence 超过阈值后，DEER 丢弃 trial answer，切换到 answer phase，再生成一次正式 readout。

这带来两个问题：

1. confidence 衡量的是 trial answer，但最终交付的是另一条 readout；二者不一致时，原 DEER 仍交付 readout。
2. 如果 trial answer 已经正确且格式完整，正式 readout 可能只增加生成成本；如果二者不一致，则第一次 confidence 本身不足以支持无条件停止。

现有 Dev 数据包含 684 条轨迹，其中 486 条在 DEER 的 `confidence > 0.95` 下触发。严格数学等价判分显示：

- trial answer 与 readout 的一致率为 85.39%；
- 触发样本中的 trial answer 准确率为 88.89%；
- readout 准确率为 88.48%；
- trial 正确而 readout 错误 29 条，readout 正确而 trial 错误 27 条；
- 每次触发后的正式 readout 平均额外生成 470.5 tokens，中位数为 323 tokens。

这说明正式 readout 整体上没有产生明显净准确率收益，但在部分模型和 benchmark 上仍有纠错作用，不能简单地对所有高置信 trial answer 直接提交。

## 3. Confidence 的含义与校准

DEER confidence 不是校准后的答案正确概率。当前忠实复现计算的是 trial answer token 概率的聚合：

- DeepSeek：去掉首 token 后，对 `exp(logprob)` 取算术平均；
- Qwen3：取几何平均，并要求 trial 以 `</think>` 结束；
- 原始 commit threshold：`confidence > 0.95`。

现有 Dev 高置信触发样本的经验准确率为：

| Confidence 区间 | 样本数 | Trial answer 准确率 | Readout 准确率 | 两答案一致率 |
|---|---:|---:|---:|---:|
| `(0.95, 0.97]` | 39 | 56.41% | 74.36% | 56.41% |
| `(0.97, 0.99]` | 71 | 81.69% | 81.69% | 74.65% |
| `(0.99, 0.995]` | 36 | 88.89% | 77.78% | 75.00% |
| `(0.995, 1]` | 340 | 94.12% | 92.65% | 92.06% |

因此：

- `0.95` 不应解释成“答案有 95% 概率正确”；
- `0.97` 可以作为进入验证分支的候选门槛，但不能直接提交；
- `0.99` 适合作为第二阶段 commit 的初始候选门槛，前提是两阶段答案数学等价且格式有效；
- `0.995` 适合作为 fast path 的初始候选门槛。

阈值最终只能根据 Train 选择，Dev 用于策略选择，Test 保持不可见。

### 3.1 Train+Dev 的 Wait 密度与拒绝诊断

对两个模型、三个 benchmark、三个 seed 的 2,736 条 Train+Dev frozen trajectories
重算 case-insensitive whole-word `Wait`：

- 2,650 条（96.86%）至少包含一个 `Wait`；
- 共 63,213 个，平均 23.10 个/序列，中位数 9，P90 为 64；
- 原 DEER 实际执行 12,024 次 probe，其中 10,031 次（83.42%）未过 `>0.95`；
- AIME24 平均 72.44 个 `Wait`，实际 probe 拒绝率 96.57%。

因此当前问题不是 trigger coverage 不足，而是 `Wait` 在困难题上过密。简单并入更多
conclusion markers 会增加 probe 税，缺少直接证据支持。1024 min-token 加“前 10 次
dense、之后 512-token gap、无 hard maximum”的调度在保留长序列后期机会的同时，
限制局部密集 probe。

## 4. 建议的状态机

### 4.1 第一阶段：Trial Probe

当前 deployment-style Dev 实验只在 case-insensitive whole-word `Wait` 上运行
DEER-style trial probe，不加入 conclusion/entropy marker。调度冻结为：

- committed-main tokens 少于 1024 时记录 `Wait` 但不 probe；
- 1024 后前 10 次实际 probe 保持 dense；
- 第 10 次后不设总次数上限，但相邻实际 probe 至少间隔 512 个
  committed-main tokens；
- 1024 前跳过的 `Wait` 不计入前 10 次，稀疏阶段距离不足的 `Wait` 不排队。

probe 得到：

```text
(answer_a, confidence_a, validity_a)
```

按以下顺序决策：

1. 如果 `validity_a = false`：丢弃 probe，继续主推理。
2. 如果 `confidence_a > 0.995`：进入 fast path，直接提交 `answer_a`。
3. 如果 `confidence_a > tau_branch`：保存候选答案，进入 verification branch。
4. 否则：丢弃 probe，追加 `Wait` 并继续主推理。

官方 DEER 的 Qwen3 baseline 使用 `avg2`，并要求 20-token trial 的最后一个 token
为 `</think>`，否则 confidence 强制为零。该 gate 用“模型主动结束思考”作为额外
信号。现有 Train+Dev probe 的数学等价判分说明它不是无害的格式条件：

| Qwen3 trial 事件 | 数量 | Trial-answer 正确率 |
|---|---:|---:|
| 缺少 `</think>`，非空可解析 | 5,549 | 26.58% |
| 缺少 `</think>`，answer-token confidence `>0.97` | 1,755 | 46.72% |
| 缺少 `</think>`，answer-token confidence `>0.995` | 671 | 54.40% |
| 生成 `</think>`，官方 confidence `>0.97` | 881 | 96.82% |
| 生成 `</think>`，官方 confidence `>0.995` | 676 | 98.52% |

加入 1024 min-token 后差距仍存在：缺少 `</think>` 的 `>0.97`/`>0.995` trial
正确率为 45.93%/47.12%，生成 `</think>` 时为 93.83%/97.15%。这些是逐 probe
事件统计，不是逐题首触发率，但足以否定“直接删除 gate”。

因此，`deer_online_reference` 和新的 `deer_inspired_online_v1` 都保留 Qwen
`avg2 + </think>` gate。Stage-1 缺少 gate 时不能 fast 或进入 branch；Stage-2
缺少 gate 时即使答案等价且 `c2>0.99` 也不能 commit。DeepSeek 继续使用
`avg1` 和 boxed-close stop，不增加 Qwen 专用条件。

早期设计曾考虑比较 `tau_branch ∈ {0.95, 0.97}`。根据现有 confidence 分布，
当前 deployment-style Dev 实验已冻结 `tau_branch=0.97`，不在 Dev 上进行阈值
sweep；`.95` 只保留为历史设计候选。

### 4.2 第二阶段：Branch-and-Commit

当前采用 retained, candidate-conditioned outcome verification：向验证分支显示
候选，但把它标记为不可信，只快速检查其是否满足题目要求，而不是重新审查完整推理。
verification reasoning 总是合并进主序列；Stage-2 trial answer 仍是可丢弃旁路，
在 commit 前不得写入主序列。流程为：

```text
clean_prefix
  + "Candidate answer: \boxed{answer_a}"
  + "I will quickly verify within 64 tokens whether this answer satisfies every "
    "requirement of the problem."
  + bounded verification reasoning
  + second DEER-style trial probe
```

第二次 probe 得到：

```text
(answer_b, confidence_b, validity_b)
```

仅当以下条件全部成立时 commit：

```text
validity_b
AND confidence_b > 0.99
AND mathematically_equivalent(answer_a, answer_b)
```

否则：

1. 保留 candidate cue 和 verification reasoning，将其合并进主上下文；
2. 只丢弃 Stage-2 answer inducer 和 trial output；
3. 不回到 `clean_prefix`，也不自动追加 `Wait`；
4. 清空候选答案；
5. 从保留的 verification context 继续推理。

这种设计允许 verifier 直接核对 outcome，代价是存在候选答案锚定风险。因此 commit
不能由自然语言 `verified` 触发，仍必须要求第二次答案有效、`c2>0.99` 且与第一次数学
等价。若 verifier 修正了答案，`answer_b != answer_a`，则 branch 不 commit，也不直接
交付修正结果；但验证过程本身保留，使后续主推理能够利用其检查或修正。Stage-2
probe 始终是旁路，失败输出绝不合并。

当前 deployment 配置将 verification reasoning 从 128 降为 64 tokens，并要求两次
实际 branch 至少相隔 512 个 committed-main tokens。cooldown 内
`.97<c1<=.995` 的候选被丢弃并继续主推理；`c1>.995` 的 valid fast path 仍可立即
commit。该限制控制昂贵 branch 的重复频率，但不设置 branch 总次数上限。

### 4.3 不使用自然语言 `"verified"` 作为充分条件

自然文本可能出现 `"not verified"`、引用或非结论性用法，因此不能仅通过字符串检测提交答案。若实验需要显式验证标记，应使用结构化格式，例如：

```text
VERIFIED: \boxed{answer}
REVISED: \boxed{answer}
```

即使使用结构化标记，仍必须保留 confidence、答案有效性和数学等价三项检查。

## 5. 门槛触发频率

以下统计基于当前 2 模型 × 3 benchmark × 3 seed 的 2736 条 train+dev 轨迹。`>0.95` 表示原 DEER 第一次停止位置的 confidence；更高阈值统计同一个已观测位置是否也超过相应门槛。

| Split | N | `c > .95` | `c > .97` | `c > .99` | Raw fast candidate `c > .995` |
|---|---:|---:|---:|---:|---:|
| Train | 2052 | 73.44% | 65.89% | 56.53% | 51.36% |
| Dev | 684 | 71.05% | 65.35% | 54.97% | 49.71% |
| Train+Dev | 2736 | 72.84% | 65.75% | 56.14% | 50.95% |

加入 `c > 0.995` fast path 后，真正进入 verification branch 的频率为：

| Split | `tau_branch=.95` | `tau_branch=.97` | Branch 次数相对减少 |
|---|---:|---:|---:|
| Train | 22.08% | 14.52% | 34.22% |
| Dev | 21.35% | 15.64% | 26.71% |
| Train+Dev | 21.89% | 14.80% | 32.39% |

因此，选择 `tau_branch=0.97` 后：

- 约 50.95% 的轨迹是 raw fast candidate；
- 约 14.80% 进入较昂贵的 verification branch；
- 约 34.25% 在当前观测位置继续推理；
- 相比 `tau_branch=0.95`，branch 调用数减少约三分之一。

Fast path 还必须通过非空、可解析的答案有效性检查。Train+Dev 的 1394
个 raw fast candidates 中，1378 个可以实际 fast commit，即全部轨迹的
50.37%；其余 16 个必须回退到原 DEER readout。Dev 中相应数字为
335/684（48.98%），而不是 raw confidence 计数的 340/684（49.71%）。

### 5.1 Dev 的模型分布

| 模型 | N | `c > .95` | `c > .97` | Fast `c > .995` | Branch `.95` | Branch `.97` |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | 342 | 66.96% | 61.99% | 47.08% | 19.88% | 14.91% |
| DeepSeek-R1-Distill-Qwen-7B | 342 | 75.15% | 68.71% | 52.34% | 22.81% | 16.37% |

### 5.2 Dev 的 benchmark 分布

| Benchmark | N | `c > .95` | `c > .97` | Fast `c > .995` | Branch `.95` | Branch `.97` |
|---|---:|---:|---:|---:|---:|---:|
| MATH500 | 600 | 76.00% | 70.17% | 53.50% | 22.50% | 16.67% |
| AMC23 | 48 | 39.58% | 35.42% | 20.83% | 18.75% | 14.58% |
| AIME24 | 36 | 30.56% | 25.00% | 25.00% | 5.56% | 0.00% |

AMC23/AIME24 样本较小，不能根据这些比例单独选择阈值。它们主要说明：难题上的高置信机会明显少于 MATH500，最终必须报告逐 benchmark 结果，而不能只看总体均值。

### 5.3 右删失限制

当前 DEER collector 在第一次 `confidence > 0.95` 后立即停止 probing 并生成 readout。若第一次 confidence 位于 `(0.95, 0.97]`，数据中不存在它之后的 probe。

因此，本文报告的 `>0.97` 是“在原 DEER 第一次停止位置已经超过 0.97”的保守可观测频率，不是把在线门槛真正改成 0.97 后的最终触发率。在线 `0.97` 策略可能在稍后的 trigger 达到门槛，真实触发率可能略高。准确比较 `0.95` 与 `0.97` 需要新的 GPU probing。

## 6. Fast Path 的离线回放证据

离线可回放策略：

```text
if confidence_a > 0.995 and parsed_answer_is_valid:
    deliver trial answer directly
else:
    preserve original DEER readout behavior
```

Dev 宏平均结果：

| 模型 | 方法 | 准确率 | 公平生成 token 节省 |
|---|---|---:|---:|
| Qwen3-8B | 原 DEER | 86.22% | 16.29% |
| Qwen3-8B | `>.995` fast path | 85.89% | 18.69% |
| DeepSeek-7B | 原 DEER | 74.93% | 20.16% |
| DeepSeek-7B | `>.995` fast path | 76.37% | 22.17% |

Train 宏平均结果：

| 模型 | 方法 | 准确率 | 公平生成 token 节省 |
|---|---|---:|---:|
| Qwen3-8B | 原 DEER | 79.10% | 17.17% |
| Qwen3-8B | `>.995` fast path | 79.75% | 20.21% |
| DeepSeek-7B | 原 DEER | 67.55% | 23.61% |
| DeepSeek-7B | `>.995` fast path | 68.96% | 25.51% |

Dev 的 335 次有效 fast commit 中，相对原 readout：

- 16 条由错误变为正确；
- 6 条由正确变为错误；
- Qwen3-8B 的三个 benchmark 宏平均准确率下降 0.33pp；
- DeepSeek-7B 的三个 benchmark 宏平均准确率上升 1.44pp。

该诊断表明 fast path 有希望额外节省约 2.0–2.4 个百分点的生成 token，
且 Train 上两个模型均未出现准确率下降。Qwen3-8B Dev 上仍有小幅
accuracy/token trade-off，因此不能称为对每个模型都严格支配原 DEER。
它不是最终 Test 结论，也不能代替在线实验。

## 7. 成本解释

`tau_branch=0.97` 下约 14.80% 的 train+dev 轨迹进入 verification branch。当前固定
64 verification tokens + 20 second-probe tokens，按该历史触发率摊到全部轨迹约
12.4 个额外生成 token。此前考虑过的 128-token 版本约为 21.9 个：

- 64 verification tokens + 20 second-probe tokens：摊到全部轨迹约 12.4 个额外生成 token；
- 128 verification tokens + 20 second-probe tokens：摊到全部轨迹约 21.9 个额外生成 token。

这只是生成 token 上界的粗略期望，不包含：

- 重发 prefix 的 prompt/prefill 计算；
- KV cache 分支与恢复成本；
- verification 失败后继续主推理的 token；
- early commit 所避免的未来主推理 token。

所以 token saving 必须通过在线实验测量，不能由触发率直接推断。报告中应继续分开呈现：

1. 主序列生成 token；
2. 所有辅助分支生成 token；
3. prompt/prefill token；
4. wall-clock latency。

## 8. 独立实验与未来消融

当前 online Dev 实验组只包含：

1. 忠实的 `deer_online_reference`；
2. 冻结参数的 `deer_inspired_online_v1`。

为争取在单张 RTX 5090 上于北京时间 2026-07-29 00:00 前完成，本轮 formal
collection 固定为唯一 development seed `42`。每个方法覆盖：

```text
2 models × (100 MATH500 + 8 AMC23 + 6 AIME24) = 228 problems
```

两个方法合计 456 条逐题结果。seed 43/44 不进入本轮 formal collection、汇总或
方法选择，Test/confirmation seeds 45/46/47 仍不可读取。本文前面的三-seed
Train+Dev 表格只是冻结轨迹上的设计证据，不代表本轮在线实验规模。单-seed 结果
不能估计 seed variance；统计使用按 benchmark 分层、方法间逐题配对的 bootstrap，
并将 AMC23/AIME24 小样本结论明确标记为 exploratory。

当前固定：

- `tau_branch=.97`；
- `tau_fast=.995`；
- `tau_commit=.99`；
- verification budget=64；
- verification branch min-gap=512 committed-main tokens；
- `confirmation_depth=2`；
- 第二次答案必须与第一次数学等价；
- probe answer 必须通过格式有效性检查；
- verification branch 失败后保留 cue+verification reasoning，只丢弃 Stage-2；
- 1024 min-token，前 10 次 dense，之后 512-token sparse gap。

以下只作为未来独立消融，不在本轮 Dev 运行中追加或据结果临时启用：

- branch threshold：`.95` vs `.97`；
- verification budget：64 vs 128 tokens；
- verification context：当前展示候选并做 outcome verification；未来可与不展示候选
  的独立验证做消融；
- branch trigger：固定 `Wait` vs Governor adaptive trigger；
- fast path：开启 vs 关闭。

## 9. 规则维度

该策略新增或复用的可优化规则维度为：

- `stage1_trigger`
- `confidence_aggregation`
- `branch_threshold`
- `fast_commit_threshold`
- `verification_context`
- `verification_budget` / `verification_delay`
- `commit_threshold`
- `answer_agreement`
- `confirmation_depth`
- `failure_cooldown`
- `max_verification_attempts`

模型、benchmark、seed、难度标签不是规则维度，只用于评估泛化性和分层报告。

## 10. 实验隔离要求

后续实现应遵守以下隔离约束：

- 新配置不得写入现有 Pareto sweep config；
- 新结果不得写入现有 Pareto candidate/result 目录；
- 不重新标记原 Pareto 候选的 Train 筛选状态；
- 原 Governor Pareto 策略作为固定基线参与比较；
- 建议使用独立命名空间，例如：

```text
benchmark/FalseConsensus/deer_inspired/
benchmark/FalseConsensus/results/deer_inspired/
```

在完成独立实验前，本策略应明确标记为 `DEER-inspired proposal`，而不是当前 Governor 主策略。
