# Adaptive Reasoning Consensus Project Plan

**Working title:** *When Is Consensus Safe to Stop? Calibrating Agreement in Adaptive Reasoning*
**Alternative title:** *Transient Consensus in Long-Form Reasoning: Why Agreement-Based Early Stopping Fails*
**Repository:** 继续使用现有 Governor repo；在 `benchmark/FalseConsensus/` 下扩展分析与实验。
**Updated:** 2026-07-22

---

# 0. 项目重新定位

本项目最初研究：

> 模型在推理过程中形成一致答案时，是否可以据此提前停止？

首轮实验已经表明：

1. **Agreement 与 correctness 总体正相关**，因此 agreement 不是无效信号；
2. **长期、全轨迹一致通常非常可靠**；
3. 真正危险的是把一个短暂的局部稳定窗口误判为终局；
4. 当前 probe 本身会产生空答案、选项字母等格式伪影；
5. 现有的“连续若干次一致即停止”会系统性截断后续纠错。

因此，项目不再以泛化的“False Consensus”作为唯一中心，而聚焦：

> **如何区分 transient consensus 与 terminal consensus，并判断什么时候 agreement 足以支持安全早停？**

核心设计原则：

\[
\text{Stop} = \text{Valid Probe} \land \text{Stable Consensus} \land \text{Reliable}
\]

而不是：

\[
\text{Stop} = \text{Local Agreement}
\]

---

# 1. 当前进度与已获得结论

## 1.1 已完成实验

| Stage                                 |                状态 | 主要产出                                             |
| ------------------------------------- | ------------------: | ---------------------------------------------------- |
| Stage 1：Logging                      |             ✅ 完成 | MATH-500 全部 500 题；8,739 个 probe；500 条完整轨迹 |
| Stage 2：Agreement vs Accuracy        |             ✅ 完成 | cumulative/window calibration curve                  |
| Stage 3：初步错误分类                 |         ✅ 首轮完成 | 134 个候选案例；前 100 题 28 例初步分类              |
| Stage 4：Trajectory Analysis          |             ✅ 完成 | consensus time、recovery、initial answer             |
| Stage 5：早停离线回放                 |             ✅ 完成 | Dynasor-style early stop 模拟                        |
| Stage 6：Probe Validity Audit         |   🟡 工具完成，标注中 | 296 例已抽样（6组×~50），annotate.html 标注工具已交付；等待人工标注 annotations.csv |
| Stage 7：Stop-rule Pareto Sweep       |             ✅ 完成 | 142 配置离线回放；Conservative/Balanced/Aggressive 三个操作点；见 `results/stage7_pareto/report.md` |
| Stage 8：Improved Probe               |           ⬜ 未开始 | 比较短答案、长答案、结构化 probe（需真实模型服务器） |
| Stage 9：Mechanism Analysis (Difficulty Control) | 🟡 离线部分完成 | Analysis 1/2 + Terminality/Correctness/Safe-stop 已完成；Analysis 3/4 及 probe_validity 特征待 Stage 6 标注后补齐；见 `results/stage9_difficulty/report.md` |
| Stage 10：Governor++                  |           ⬜ 未开始 | 构建 reliability-aware controller（需 Stage 6 + Stage 9 完整结果） |
| Stage 11：Cross-model                 |           ⬜ 未开始 | 检验结论能否跨模型泛化                               |
| Stage 12：Cross-dataset               |           ⬜ 未开始 | 检验结论能否跨数据集泛化                             |

## 1.2 首轮核心结果

设置：

- Model: `DeepSeek-R1-Distill-Qwen-7B`
- Dataset: `MATH500`
- Token budget: `3072`
- Probe interval: `128`
- Probe max tokens: `10`
- Temperature: `0.6`
- Governor: logging only

主要结果：

| 指标                             |                 结果 |
| -------------------------------- | -------------------: |
| 最终准确率                       |                81.2% |
| 全轨迹非空`cumulative share=1` |  87 题，准确率 98.9% |
| 最后 5 个 probe 完全一致         | 338 题，准确率 93.5% |
| 3-probe 一致即停，触发率         |              416/500 |
| 早停准确率                       |                69.2% |
| 同批题继续到底准确率             |                85.6% |
| 准确率损失                       |        16.4 个百分点 |
| 平均节省主轨迹 token             |                1,321 |
| 停在错误答案上                   |               128 题 |
| 曾形成错误稳定共识后最终改对     |               95/145 |
| 空 probe                         |      553/8,739，6.3% |

## 1.3 已被推翻或需要修正的假设

### 原假设 H1

> Agreement 不代表 correctness。

修正为：

> Agreement 与 correctness 正相关，但 **local agreement 并不等于 terminal correctness**。

### 原假设 H2

> 第一个错误 belief 会造成持续 lock-in。

当前证据不支持。第一个 probe 错误的 375 题中，286 题最终答对。

更合理的解释是：

> 早期 probe 很可能是在推理尚未完成时被迫猜测答案，而非真实、稳定的错误 belief。

### 原假设 H3

> 共识形成越早越危险。

当前结果方向相反：

- `<512 tokens` 形成共识：87.4%
- `>2048 tokens` 形成共识：58.1%

新的待检验解释：

> 晚共识通常对应更困难、更接近模型能力边界的题；需要控制题目难度后重新分析。

---

# 2. 统一术语和定义

后续所有代码、图表和论文统一使用以下定义。

## 2.1 Agreement

在某个 probe 集合中，dominant answer 所占比例：

\[
A = \frac{\max_a \#\{i: y_i=a\}}{\#\{i: y_i\neq \emptyset\}}
\]

## 2.2 Persistent Consensus

从某个时刻开始，在较长区间内 dominant answer 持续不变，且有效 probe 足够多。

## 2.3 Transient Consensus

局部窗口形成一致，但后续 dominant answer 发生改变。

## 2.4 Persistent False Consensus

模型在较长区间或全程稳定输出同一答案，但该答案错误。

## 2.5 Premature Consensus Stop

控制器因局部一致触发停止，而停机答案错误。

## 2.6 Extraction Artifact

probe 输出不能代表任务答案，包括：

- 空串；
- 被截断答案；
- 非选择题中输出 `A/B/C/D`；
- 格式错误；
- 与当前 reasoning prefix 明显不一致的输出。

## 2.7 Overthinking

某时刻已经得到正确答案，继续推理后改成错误答案并最终输出错误结果。

## 2.8 Recovery

某时刻的 dominant answer 错误，但继续推理后最终答案正确。

---

# 3. 下一阶段总路线

```text
Stage 6: Probe Validity Audit
        ↓
Stage 7: Existing-log Stop-rule Pareto Sweep
        ↓
Stage 8: Improved Probe Comparison
        ↓
Stage 9: Difficulty-controlled Mechanism Analysis
        ↓
Stage 10: Governor++
        ↓
Stage 11: Cross-model / Cross-dataset Validation
        ↓
Paper Writing
```

最重要的顺序约束：

> **不要在验证 probe 质量之前训练或设计复杂 reliability classifier。**

---

# 4. Stage 6 — Probe Validity Audit

## 4.1 目标

回答：

> 当前 probe 输出到底有多大比例真实反映了模型在该 reasoning prefix 下已经形成的答案？

这是整个项目下一步最重要的实验。

当前 probe 使用：

```text
**Final Answer**

\[
\boxed{
```

并且只允许生成 10 tokens。

该设计可能强迫尚未完成推理的模型猜答案，也可能截断复杂答案。因此不能直接把 probe 当作内部 belief。

## 4.2 样本抽取

从现有 500 题日志中抽取以下六组，每组 50 个 probe-level 案例；允许重叠，但分析时记录来源。

1. `probe_answer == final_answer`
2. `probe_answer != final_answer`
3. probe 输出为单个字母
4. probe 输出为空
5. 连续 3 次一致后发生答案变化
6. 连续 3 次一致后保持到最后

总量目标：

- 初版：200–300 个不同 probe
- 最终：至少 500 个 probe-level annotations

## 4.3 每个案例展示内容

人工标注页面需要同时展示：

- problem；
- reference answer；
- 当前 token position；
- 当前 reasoning prefix；
- probe prompt；
- probe raw output；
- normalized probe answer；
- 前后各 2–3 个 probe；
- 最终 reasoning continuation；
- final answer；
- final correctness。

## 4.4 标注标签

每个 probe 标注一个主标签：

| Label                        | 定义                                      |
| ---------------------------- | ----------------------------------------- |
| `supported_correct`        | prefix 已经充分支持当前 probe，且答案正确 |
| `supported_wrong`          | prefix 已经形成明确但错误的答案           |
| `tentative_guess`          | prefix 尚未完成，probe 只是被迫猜测       |
| `incomplete_answer`        | 答案被 token 限制截断                     |
| `format_artifact`          | 输出形式与任务不匹配                      |
| `inconsistent_with_prefix` | probe 与 reasoning prefix 明显矛盾        |
| `ambiguous`                | 无法可靠判断                              |

额外二元字段：

- `valid_as_current_answer`
- `ready_to_stop`
- `answer_complete`
- `prefix_contains_support`
- `requires_more_reasoning`

## 4.5 标注流程

### Round 1

由两名标注者独立标注 100 个案例。

### Round 2

计算一致性：

- Cohen’s kappa；
- raw agreement；
- 对争议案例讨论并修改指南。

### Round 3

扩展至 300–500 个案例。

## 4.6 主要指标

1. Probe validity rate；
2. Validity by token position；
3. Validity by answer type；
4. Validity by consensus strength；
5. Validity by correctness；
6. Forced-guess rate；
7. Artifact rate；
8. `P(final correct | supported_wrong)`；
9. `P(final correct | tentative_guess)`。

## 4.7 关键判断标准

### 情况 A

若大部分早期错误 probe 是 `tentative_guess`：

> 论文重点应从“错误 belief”转为“forced answer extraction causes premature stopping”。

### 情况 B

若大量 probe 是 `supported_wrong`，后续又成功修正：

> 可以更强地讨论 reasoning recovery 与 non-terminal consensus。

### 情况 C

若 artifact 占比很高：

> 必须优先重构 probe，当前 Governor 结果只能作为诊断结果。

## 4.8 产出

```text
benchmark/FalseConsensus/
├── audit/
│   ├── sample_probe_audit.py
│   ├── annotation_guideline.md
│   ├── probe_audit_cases.jsonl
│   ├── annotations_annotator1.csv
│   ├── annotations_annotator2.csv
│   ├── adjudicated_annotations.csv
│   └── audit_report.md
```

---

# 5. Stage 7 — Stop-rule Pareto Sweep

## 5.1 目标

在现有 500 题 logging 轨迹上，不重跑模型，系统比较简单 early-stop 规则的上限。

核心问题：

> 是否存在明显优于“3 次一致即停”的简单规则？

不再只报告单一 stop rule，而是画完整：

\[
\text{Accuracy} \leftrightarrow \text{Compute Saving}
\]

Pareto frontier。

## 5.2 规则参数

```text
min_tokens ∈ {0, 256, 512, 768, 1024, 1536, 2048}
patience ∈ {3, 4, 5, 6, 8}
window_size ∈ {3, 5, 8}
share_threshold ∈ {0.6, 0.8, 1.0}
min_valid_probes ∈ {3, 5, 8}
max_answer_switches ∈ {0, 1, 2, unlimited}
```

Entropy rule：

```text
entropy_rule ∈ {
    none,
    current_entropy_below_threshold,
    non_increasing_last_k,
    low_entropy_for_k_steps
}
```

Validity filter：

```text
validity_filter ∈ {
    none,
    nonempty_only,
    nonempty_and_nonletter,
    answer_type_aware
}
```

## 5.3 Baselines

1. Vanilla full generation
2. Hard token cap: 512 / 1024 / 1536 / 2048 / 3072
3. 3 consecutive same answers
4. Last-5 unanimous
5. Entropy threshold
6. CertaIndex share threshold
7. Minimum-token + unanimity
8. History-aware consensus

## 5.4 每个配置报告

- overall accuracy；
- average main reasoning tokens；
- average probe tokens；
- stop coverage；
- false-stop rate；
- correct-stop rate；
- no-stop rate；
- correct-to-wrong truncation；
- wrong-to-correct recovery 被截断数；
- overthinking 被避免数；
- wall-clock estimate；
- total generated tokens。

## 5.5 Token 成本口径

| 成本                       | 含义                               |
| -------------------------- | ---------------------------------- |
| `main_tokens`            | 主推理轨迹 token                   |
| `probe_output_tokens`    | probe 输出 token                   |
| `probe_calls`            | probe 次数                         |
| `total_generated_tokens` | main + probe output                |
| `wall_clock`             | 实际运行时间                       |
| `prefill_cost_estimate`  | 如可获得，估计 prefix prefill 成本 |

论文中不能只写“节省 43% token”，应写：

> 节省 43% main reasoning tokens；计入 probe 调用后，总生成 token / wall-clock 为……

## 5.6 Pareto 图

- Figure A：x = average total generated tokens；y = accuracy。
- Figure B：x = stop coverage；y = false-stop rate。
- Figure C：x = main-token saving；y = accuracy drop。

## 5.7 选择 Governor++ 原型

从 Pareto frontier 选择 3 个工作点：

1. **Conservative**：准确率下降 ≤1%
2. **Balanced**：准确率下降 ≤3%
3. **Aggressive**：最大节省 token

---

# 6. Stage 8 — Improved Probe Comparison

## 6.1 目标

比较不同 probe 设计是否能：

- 减少空答案；
- 减少格式伪影；
- 更准确反映当前 prefix；
- 改善 agreement calibration；
- 改善 early-stop Pareto。

## 6.2 Probe 设计

### P0：Current Short Answer Probe

当前设计，10 tokens。

### P1：Longer Answer Probe

相同 prompt，但：

```text
max_probe_tokens ∈ {32, 64}
```

### P2：Answer-or-Unfinished Probe

允许模型承认当前尚未得到答案：

```text
Given the reasoning so far, output exactly one of:

<status>unfinished</status>

or

<status>answer</status>
<answer>...</answer>
```

### P3：Structured Confidence Probe

```text
<status>unfinished|tentative|confident</status>
<answer>...</answer>
```

注意：confidence 只作为额外信号，不直接假设 verbal confidence 已校准。

### P4：Prefix-based External Extraction

不让模型继续解题，只从当前 reasoning prefix 中抽取已明确出现的候选答案：

```text
Extract the latest explicitly supported answer from the reasoning prefix.
If no explicit answer is supported, return UNFINISHED.
```

可使用同模型或较小模型，但必须单独计成本。

## 6.3 第一轮实验规模

先选固定 100 题：

- easy / medium / hard 分层；
- 包含空答案、字母伪影、翻盘案例；
- 所有 probe 设计使用相同主轨迹。

这样只需重跑 probe，不需重跑主 reasoning。

## 6.4 主要比较指标

| 指标                           | 说明                            |
| ------------------------------ | ------------------------------- |
| empty rate                     | 空答案比例                      |
| truncation rate                | 截断比例                        |
| artifact rate                  | 格式伪影比例                    |
| valid-answer rate              | 人工审计后有效比例              |
| readiness precision            | 预测“可以停”时真正可停的比例  |
| calibration error              | agreement 与 correctness 的偏差 |
| downstream early-stop accuracy | 用该 probe 早停的准确率         |
| downstream token saving        | 用该 probe 早停的 token 节省    |
| probe cost                     | probe 输出与计算开销            |

## 6.5 成功标准

Improved probe 至少满足：

- artifact rate 明显下降；
- empty/truncation rate 下降；
- 在相同 token saving 下准确率更高；
- 或在相同准确率下节省更多 token。

若 P2/P3 明显优于 P0，后续主实验全部切换到新 probe。

---

# 7. Stage 9 — Mechanism Analysis with Difficulty Control

## 7.1 目标

验证以下观察究竟来自共识机制，还是题目难度的混杂：

> 共识形成越晚，最终准确率越低。

## 7.2 难度变量

至少使用：

- MATH level；
- problem category；
- vanilla correctness；
- 多 seed / 多 sample pass rate；
- full-generation length；
- whether hit token cap；
- average token entropy；
- final answer confidence；
- number of answer switches。

## 7.3 实验分析

### Analysis 1：分层统计

在相同 MATH level 内比较 consensus time 与 accuracy。

### Analysis 2：Logistic Regression

预测：

\[
P(\text{final correct})
\]

输入：

- consensus time；
- MATH level；
- answer switches；
- probe validity；
- entropy；
- token cap；
- category。

### Analysis 3：Matched Comparison

对早共识和晚共识题做 difficulty matching，再比较准确率。

### Analysis 4：Recovery Probability

估计：

\[
P(\text{recover} \mid t, A_t, \text{difficulty}, \text{switch history})
\]

## 7.4 新的核心指标

### Terminality Probability

\[
T_t = P(\text{dominant answer remains unchanged until the end} \mid \mathcal{H}_t)
\]

### Correctness Probability

\[
C_t = P(\text{current dominant answer is correct} \mid \mathcal{H}_t)
\]

### Safe-stop Probability

\[
S_t = P(\text{current answer is correct and terminal} \mid \mathcal{H}_t)
\]

其中：

\[
\mathcal{H}_t =
\{
\text{agreement history},
\text{answer switches},
\text{entropy history},
\text{token position},
\text{validity},
\text{difficulty}
\}
\]

核心结论目标：

> Agreement 只描述当前答案分布是否集中；安全停止还需要 correctness 与 terminality。

---

# 8. Stage 10 — Governor++

## 8.1 第一版：规则型 Governor++

先不训练模型，使用透明、可解释的规则。

```text
Stop only if:

1. probe answer is valid;
2. token_position >= min_tokens;
3. recent window is unanimous or above threshold;
4. dominant answer has remained stable for sufficient probes;
5. answer-switch history is low;
6. current trajectory is not classified as high-recovery-risk.
```

## 8.2 推荐初始规则

```text
valid_answer == True
AND token_position >= 1024
AND last_5_valid_probes unanimous
AND dominant_share_last_8 >= 0.75
AND answer_switches_last_8 <= 1
AND current_answer != single_option_letter_for_non_MC
```

这只是起点，最终参数由 Stage 7 Pareto sweep 决定。

## 8.3 第二版：Calibrated Governor++

使用现有 log 拟合一个轻量分类器，预测：

```text
safe_to_stop ∈ {0,1}
```

严格标签需要同时满足：

- current answer correct；
- current answer terminal；
- probe valid。

输入特征：

- token position；
- current window share；
- cumulative share；
- entropy 与 entropy slope；
- number of unique answers；
- answer switches；
- time since last switch；
- consecutive same count；
- answer type 与 answer length；
- empty/letter flags；
- current reasoning length；
- whether current answer appeared before；
- problem category / level。

优先模型：

- logistic regression；
- decision tree；
- gradient boosting。

不要一开始使用大 verifier，以免无法判断收益来自哪里。

## 8.4 数据切分

禁止在同一 500 题上同时调参和报告最终结果。

建议固定：

```text
train 60%
validation 20%
test 20%
```

所有 threshold 和模型仅在 train/validation 上选择，test 只运行一次。

## 8.5 Governor++ Baselines

- Vanilla full generation
- Fixed budget
- Raw CertaIndex
- Entropy threshold
- Patience-based consensus
- Minimum-token consensus
- Rule-based Governor++
- Calibrated Governor++

## 8.6 主要报告结果

| Method | Accuracy | Main Tokens | Total Tokens | Stop Coverage | False-stop Rate |
| ------ | -------: | ----------: | -----------: | ------------: | --------------: |

同时报告 Conservative / Balanced / Aggressive 三种工作点。

## 8.7 成功标准

### 最低成功

相对 raw 3-probe consensus：

- 准确率提高 ≥8 个百分点；
- 同时保留至少一半原 token saving。

### 较强成功

相对 full generation：

- 准确率下降 ≤1–2 个百分点；
- total inference cost 节省 ≥20%。

### Main-paper 级别目标

在多个模型与数据集上：

- Pareto-dominates raw agreement baselines；
- probe validity 与 terminality 分析具有一致机制；
- reliability-aware controller 显著改善 accuracy–compute tradeoff。

---

# 9. Stage 11 — Cross-model Validation

## 9.1 模型顺序

1. DeepSeek-R1-Distill-Qwen-7B
2. Qwen reasoning model / Qwen3-8B
3. 另一个 7B–8B reasoning model
4. 可选 1.5B / 3B 小模型用于规模分析
5. 可选 14B / 32B 用于能力分析

## 9.2 每个模型的最小实验

- MATH-500 全部 500 题；
- 统一 budget；
- 统一 probe interval；
- 使用 Stage 8 选出的最佳 probe；
- 正式结果至少 3 seeds，开发阶段可先单 seed。

## 9.3 需要比较

- full-generation accuracy；
- agreement calibration；
- transient consensus rate；
- persistent false consensus rate；
- recovery rate；
- probe artifact rate；
- best early-stop Pareto；
- Governor++ gain。

---

# 10. Stage 12 — Cross-dataset Validation

## 10.1 数据集顺序

1. MATH-500
2. AMC23
3. AIME24 / AIME25
4. GSM8K
5. 可选 GPQA-Diamond

## 10.2 Multiple-choice 特殊处理

对于选择题：

- 单个 `A/B/C/D` 是合法答案；
- 不能使用“字母过滤”；
- validity filter 必须依赖 dataset answer schema。

实现：

```text
answer_schema ∈ {
    numeric,
    symbolic_math,
    set_interval,
    multiple_choice,
    text_short_answer
}
```

---

# 11. 统计规范

## 11.1 Seeds

正式结果至少：

- 3 seeds；或
- 每题多条独立 trajectory。

## 11.2 Confidence Interval

对 accuracy、false-stop rate、recovery rate 使用 bootstrap 95% CI。

## 11.3 Significance Test

同一批题的方法比较使用 paired test：

- McNemar test：比较准确率；
- paired bootstrap：比较 token saving 与 accuracy；
- calibration metric 使用 bootstrap interval。

## 11.4 Calibration

除现有 CCE 外，补充：

- Expected Calibration Error；
- Brier score；
- reliability diagram；
- per-bin support；
- selective risk / coverage curve。

---

# 12. 代码结构

```text
Governor/
├── governor/
├── benchmark/
│   └── FalseConsensus/
│       ├── README.md
│       ├── plan.md
│       ├── log.md
│       ├── FINDINGS.md
│       ├── logging/
│       ├── audit/
│       ├── analysis/
│       ├── replay/
│       ├── probes/
│       ├── governor_plus/
│       └── results/
│           ├── stage1_logging/
│           ├── stage6_probe_audit/
│           ├── stage7_pareto/
│           ├── stage8_probe_comparison/
│           └── stage10_governor_plus/
```

建议脚本：

```text
audit/sample_probe_audit.py
audit/analyze_audit.py
replay/replay_stop_rules.py
replay/sweep_stop_rules.py
replay/pareto_analysis.py
replay/cost_accounting.py
analysis/difficulty_control.py
probes/short_answer.py
probes/long_answer.py
probes/answer_or_unfinished.py
probes/structured_probe.py
governor_plus/rule_based.py
governor_plus/build_training_data.py
governor_plus/train_calibrator.py
governor_plus/evaluate_controller.py
```

---

# 13. 接下来 14 天的具体执行计划

## Day 1：冻结现有结果

- 保存当前 commit hash；
- 固定原始 `probes.csv` 与 trajectory；
- 将所有评估修正写入 changelog；
- 明确 raw data 不再覆盖。

产出：

```text
data_manifest.json
evaluation_changelog.md
```

## Day 2：建立 Probe Audit 数据集

- 编写 `sample_probe_audit.py`；
- 按六类抽样；
- 生成 100 个首轮案例。

## Day 3：完成标注指南

- 定义七类主标签；
- 自己先标 30 个；
- 修订模糊边界；
- 输出 `annotation_guideline.md`。

## Day 4–5：双人标注与一致性

- 两名标注者各标 100 个；
- 计算 Cohen’s kappa；
- 讨论冲突；
- 输出 probe validity 初步结果。

### Checkpoint 1

必须回答：

1. 早期错误 probe 中多少是 forced guess？
2. 稳定错误 probe 中多少有 prefix 支持？
3. 字母和空串 artifact 占比多少？
4. 当前 probe 是否足以支撑“belief”叙事？

## Day 6：实现离线 Stop-rule Sweep

- 参数化 patience/window/share/min_tokens；
- 加 validity filter；
- 统一输出 cost 与 accuracy。

## Day 7：跑完整 Pareto Sweep

- 在现有 500 题上跑全部规则；
- 输出 CSV；
- 画 Pareto frontier；
- 选 3 个 operating points。

### Checkpoint 2

- 若 accuracy drop ≤2%、token saving ≥20%，优先写透明规则；
- 若做不到，再引入 calibrated classifier。

## Day 8：实现四种 Probe

- P0 short；
- P1 32/64-token；
- P2 answer-or-unfinished；
- P3 structured status。

## Day 9：在 100 题上重跑 Probe

- 复用相同 reasoning trajectory；
- 比较空率、artifact、validity；
- 记录额外 probe 成本。

## Day 10：选择最佳 Probe

- 人工审计至少 100 个新 probe；
- 比较 early-stop Pareto；
- 确定正式 probe。

### Checkpoint 3

若新 probe 明显提升：

- 后续跨模型实验全部使用新 probe；
- 旧 probe 作为 diagnostic baseline。

若没有提升：

- 保留短 probe；
- 把 probe failure 作为论文核心分析之一。

## Day 11：难度控制分析

- 加入 MATH level/category；
- 运行 logistic regression；
- 检验 consensus time 是否仍独立显著。

## Day 12：实现 Rule-based Governor++

- 使用 Pareto 与 audit 结果确定规则；
- 在 held-out test split 上评估。

## Day 13：实现简单 Calibrated Governor++

- Logistic regression / gradient boosting；
- train/val/test 划分；
- 画 risk–coverage curve。

## Day 14：整理阶段报告

必须包含：

1. Probe validity table；
2. Short vs improved probe；
3. Stop-rule Pareto；
4. Difficulty-controlled consensus-time analysis；
5. Rule-based Governor++；
6. Calibrated Governor++；
7. 下一步跨模型计划。

---

# 14. Figure 规划

1. Agreement vs Accuracy：cumulative / local window / valid probes only
2. Probe Validity Breakdown
3. Transient Consensus Example
4. Accuracy–Compute Pareto Frontier
5. Consensus Time vs Accuracy：raw / difficulty-controlled
6. Recovery Probability
7. Probe Design Comparison
8. Cross-model Generalization

---

# 15. Table 规划

1. Dataset and Logging Statistics
2. Probe Validity Audit
3. Early-stop Baselines
4. Governor++ Main Results
5. Ablation
6. Cross-model / Cross-dataset Results

Ablation 至少移除：

- validity filter；
- minimum token；
- history stability；
- entropy features；
- difficulty features。

---

# 16. 风险与 Plan B

## Risk 1：大部分所谓 false consensus 都是 probe artifact

新的论文故事：

> Existing answer-probing protocols do not faithfully measure intermediate reasoning state and can produce misleading consensus signals.

方法贡献：improved probe + probe validity benchmark + safer controller。

## Risk 2：简单规则已经几乎解决问题

这是好结果：

> Most early-stop failures are caused by identifiable validity and terminality violations; a transparent controller fixes them without a verifier.

## Risk 3：Governor++ 仍无法接近 full generation

转为 analysis paper：

> 当前 agreement-based stopping 存在不可避免的 accuracy–compute tradeoff，中期局部答案无法可靠预测终局。

## Risk 4：跨模型结果不一致

转为分析模型能力与恢复行为：

- 强模型可能 recovery 更多；
- 弱模型可能 persistent wrong 更多；
- consensus reliability 可能是 model-dependent。

## Risk 5：probe 成本抵消 token 节省

改为 adaptive probing：

- 前期低频；
- 检测到稳定趋势后提高频率；
- 或只在 entropy / 关键词触发时 probe。

---

# 17. 最终论文贡献目标

理想情况下，论文贡献写成：

1. **诊断发现：** 局部 answer agreement 与终局正确性不同，transient consensus 会导致 premature stopping；
2. **测量发现：** 当前 answer-probing protocol 存在 forced guess、truncation 和 format artifact；
3. **机制分析：** 安全停止需要同时判断 answer validity、correctness 与 terminality；
4. **方法贡献：** 提出 reliability-aware Governor，在多个模型和数据集上改善 accuracy–compute Pareto；
5. **评估贡献：** 给出 probe validity audit、recovery analysis 和统一 early-stop evaluation protocol。

---

# 18. 当前最优先任务

按优先级排序：

1. **Probe Validity Audit** — 🟡 标注工具已交付（`audit/annotate.html`，296例），人工标注进行中，`analyze_audit.py` 待 annotations.csv 后补齐
2. **现有 log 上的完整 Pareto Sweep** — ✅ 完成（`results/stage7_pareto/`）
3. **Improved Probe 对比** — ⬜ 未开始（需真实模型服务器）
4. **控制 difficulty 后重新分析 consensus time** — 🟡 离线可做部分已完成（`results/stage9_difficulty/`），Analysis 3/4 待补
5. **Rule-based Governor++**
6. **Calibrated Governor++**
7. **多模型与多数据集复现**

在前四项完成之前，不进行复杂 verifier、PRM 或大规模训练。
