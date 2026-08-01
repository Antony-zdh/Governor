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
| Stage 6：Probe Validity Audit         | 🟡 Round 1 完成（100/296） | 单人标注 100 例（无 kappa，见 log.md）；整体 validity rate 仅 39.0%；single_letter 类 0% 有效；validity 随 local consensus share 强烈上升（share=1.0 时 81.3% vs share<0.5 时 6.5%）；见 `audit/audit_report.md` |
| Stage 7：Stop-rule Pareto Sweep       |             ✅ 完成 | 142 配置离线回放；Conservative/Balanced/Aggressive 三个操作点；见 `results/stage7_pareto/report.md` |
| Stage 8：Improved Probe               |             ✅ 完成 | 100 题子集×5 probe 设计，8685 次调用；`compare_probes.py` 全部 §6.4 指标已出（见 `results/stage8_probe_compare/comparison_report.md`）；额外验证：把 Stage 7 两个可用操作点原样套用 P1-P4 信号（`probe_compare/test_stage7_rules.py`），发现更长/更结构化的 probe 不能直接提升这两条规则——token 成本涨幅盖过覆盖率收益，P2/P3/P4 因空答案率过高导致规则几乎不触发；结论：规则与 probe 设计需联合优化，不能简单替换 |
| Stage 9：Mechanism Analysis (Difficulty Control) | 🟡 离线部分完成 | Analysis 1/2 + Terminality/Correctness/Safe-stop 已完成；Analysis 3/4 及 probe_validity 特征待 Stage 6 标注后补齐；见 `results/stage9_difficulty/report.md` |
| Stage 10：Governor++                  |           ⬜ 未开始 | 构建 reliability-aware controller（需 Stage 6 + Stage 9 完整结果） |
| Stage 11：Cross-model                 |     🟡 单模型单 seed 完成 | Qwen3-8B / MATH500 500题，overall accuracy 78.2%（vs DeepSeek-7B 81.2%）；见 §9.4、`results/stage11_cross_model/` |
| Stage 12：Cross-dataset               |     🟡 单模型单 seed 完成 | DeepSeek-7B：AMC23 60.0%、AIME24 26.7%；见 §10.3、`results/stage12_cross_dataset/` |

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

## 6.6 Probe 忠实度 vs 保守度：paired re-probe 2×2 实验（下一阶段 roadmap 第 1 步）

### 6.6.1 动机与要回答的问题

Probe 后缀消融（`results/probe_suffix_ablation/`）发现：把 probe 后缀从裸的
`**Final Answer** \boxed{`（`simple`）换成 Certaindex 式"顿悟"前缀
`... Oh, I suddenly got the answer to the whole problem, **Final Answer** \boxed{`
（`certaindex`），**整体准确率几乎不变**（81.2% → 79.6%），但同一条"3-probe
一致即停"规则的表现天差地别：

| | simple | certaindex |
|---|---|---|
| 触发停机 | 416/500 | 311/500 |
| 停机答案准确率 | 69.2% | 88.7% |
| 同批题跑到底准确率 | 85.6% | 90.0% |
| 早停准确率损失 | **16.4pp** | **1.3pp** |
| 错误停机 | 128 题 | 35 题 |
| 平均省 token | 1,321 | 683 |

certaindex 触发**更少、更晚、更准**。这有一个硬 confound，必须拆开才能指导
Governor++ 设计：提升到底来自
- **(a) 更真实地读出当前状态**（probe 答案更忠实反映模型此刻的真实 belief，
  于是 3-probe 一致更有意义），还是
- **(b) 只是更保守**（更晚才凑够一致，恰好停在已收敛的简单题上，是 selection
  效应）？

若是 (a)，probe 措辞是一个独立于聚合/阈值的一等杠杆，应进入 Governor++ 核心；
若是 (b)，它本质是 min_tokens/patience 的变体，折进停机规则即可。

### 6.6.2 核心洞察

"延迟早停"和"真实读出"**不是两个独立的对立选项**——在 (a) 成立时它们是同一件
事的因果两端：一个忠实的 probe 本就应该停得更晚，因为真实 belief 确实更晚才稳定。
所以真正要问的是：**这个延迟是踩在了真正的收敛点上（忠实），还是只是一个变钝的
高门槛、恰好和"题简单"相关（保守）？**

### 6.6.3 实验设计：单轨迹基 2×2 析因

把 **timing（何时停）** 和 **readout（读出谁的答案）** 当两个正交因子，
**四格全部锁在同一条 simple 轨迹上**（关键，见 6.6.4）：

| | 读 simple 答案 | 读 certaindex 答案 |
|---|---|---|
| **停在 simple 规则位置** | ① 现状 simple ≈ 69.2% | ② **读出效应** |
| **停在 certaindex 规则位置** | ③ **timing/保守效应** | ④ certaindex（88.7% 的类比值） |

- 对角线①④是已知锚点；两个非对角格②③把 69.2→88.7 的提升**完全分解为
  读出主效应 + timing 主效应 + 交互项**。
- 格② = 在 simple 的（早）停机点上只换成 certaindex 的读出 → 隔离读出。
- 格③ = 在 certaindex 的（晚）停机点上仍读 simple 的答案 → 隔离 timing/保守。

### 6.6.4 方法与数据（关键约束）

**决定：复用现有 500 条主轨迹，不重跑主 reasoning。** 底座用
`results/stage1_logging`（DeepSeek-R1-Distill-Qwen-7B，MATH500 全 500 题，
budget 3072，8,739 个 checkpoint）。理由：probe 不影响主轨迹（见下 1），我们要改
的全是 probe 侧的东西（措辞、box 预算、is_certain、validity），一次 **re-probe**
即可，重跑主轨迹只会让 vanilla 81.2% / naive 416/500 等所有已记录锚点漂移、失去
连续性。真正需要重新生成主轨迹的是 Stage 12-长 budget（3k/6k/12k）和多 seed，
与本实验无关。

**必须密集 re-probe，且四格同一轨迹基。**

1. **probe 不影响主轨迹**：`logging_run.py` 中 probe 是独立的
   `complete(prompt+text+suffix)`，主生成从 `text` 继续、不含 probe。因此
   simple run 与 certaindex run 的主轨迹差异**纯粹是 run-to-run 采样噪声**，
   不是处理效应 —— 若把某一格建在 certaindex 自己的轨迹上，会把该噪声混入，
   破坏正交。故**全部四格建在 simple 的 500 条轨迹上**。
2. **密集 re-probe（硬要求）**：在 simple 轨迹的**每一个** checkpoint 都补 probe
   （不是只在 simple 停机点补一次）。只有拿到完整的答案流，才能把"3-连一致、
   非空、certain"规则套上去、求出各 probe 在这条 simple 轨迹上的停机位置
   （格③④的 timing）。checkpoint prefix 重构复用 Stage 8
   `run_probe_variants.py` 的 token 切片：
   `ids = tokenizer.encode(traj["full_text"], add_special_tokens=False)`；
   `prefix = tokenizer.decode(ids[:token_position])`。
3. **probe 输入必须逐字复刻 `logging_run.py`，否则复现不了 simple 的答案**：
   Stage 8 的 `build_prompt` 用的是 `prefix + suffix`，**漏了问题 prompt** ——
   而原始 probe 是 `apply_chat_template(problem) + text + suffix`（`logging_run.py`
   L158/L184）。本实验的 probe 输入 = `apply_chat_template(problem) + prefix +
   suffix`，**必须带上 chat prompt**。suffix 取 `PROBE_SUFFIXES[style]`
   （`logging_run.py` 里的 simple / certaindex 原文），probe seed 固定 `42`
   （与原始一致，主生成才是 `seed+problem_id`）。
4. **解析与 is_certain 逐字对齐**：`answer = strip_string(obtain_answer(probe_text))`；
   `is_certain = not any(w in probe_text.lower() for w in UNCERTAIN_WORDS)`，
   `UNCERTAIN_WORDS = ["wait","hold","but","okay","no","hmm"]`；答案等价性
   用 `dynasor` 的 `math_equal`（`analyze.py` 的 `eq`）。四格用同一把尺才可比。
5. **re-probe 网格 = 措辞 × box 预算**：
   `probe_suffix ∈ {simple, certaindex}` × `probe_tokens ∈ {10, 32}`。
   - `10`：逐字复刻 Stage 1（无 stop 序列），是**锚点**；
   - `32`：修 incomplete（长答案如向量/区间/方程装不下 10 token → 空/截断，
     Stage 1 空 probe 率 6.3%）。**但不能天真调大**：现状每 probe 恒用满 10 token
     （`avg_probe_output_tokens/avg_probe_calls = 174.78/17.478 = 10.0`，说明生成
     不在闭合处停），直接调到 64 → probe 成本 ~1120 token/题、吃光 Pareto 省量。
     故 `32` 档加 **stop 序列 `\]`**（`\boxed{...}` 后的显示数学闭合），短答案
     几秒即停、比 flat-10 更省，长答案才用到 32。`avg_probe_output_tokens`
     照常记录进 Pareto 的 compute 轴。
6. **验证锚点（必跑）**：`simple@10` 的 re-probe 结果，应在抽样的若干题上
   **复现 Stage 1 `probes.csv` 的 probe 答案**（seed/temp 固定，允许极少数因
   vLLM batching 非确定性不一致，目标一致率 ≳95%）。这是整条重构（chat prompt +
   token 切片 + 解析）是否忠实的黄金校验 —— 先过这关再跑全量。
7. 成本：全部 probe-only（≤32 token），不重跑主 reasoning，Stage 8 同规模
   ~5–15 分钟 GPU。

### 6.6.5 主分析 + 辅助分析

主分析（`analyze_2x2.py`）：
- 四格准确率表 + 读出主效应、timing 主效应、交互项；
- **commit 率**（P(probe 给出确定非空答案)，量保守度）与**条件忠实度**
  （见下）分开报告，避免把"少答"误当"读得准"。

判据与解读：
- 格② ≫ 69.2%：在同样早的时点、同一状态上 certaindex 就读出更准 → **纯读出
  增益，且不必停更晚也能拿到**（对省 compute 最优）；
- 格② ≈ 69.2%：读出在固定时点没帮助 → 增益来自 timing。**但这不否定忠实**：
  simple 的停机点是 premature 的，真实状态本就没定，忠实读出也应不准；忠实的
  价值可能正体现为"拒绝在此停"。要再分"忠实追踪收敛"还是"钝的高门槛"，用下面
  两个辅助分析。

辅助分析（同一份 paired 数据，零额外 GPU）：
- **continuation-match**：定义"真值" `a_continue(p,c)` = 让同一 prefix 继续跑到底
  的答案（greedy/temp0 取确定意图，或 K 条 rollout 取多数，即 §7.4 的在线版）；
  忠实度 = P(probe 答案 == `a_continue`)。比较 simple 与 certaindex 的忠实度。
- **105 个额外停机点分析**：把"simple 会停但 certaindex 不停"的
  ~(416−311)=105 个检查点单独拎出，看其 `a_continue`：若多为 premature
  （probe 答案 ≠ 真实走向且最终会变）→ certaindex 是在正确拒绝假共识（忠实）；
  若多为本来就对 → certaindex 只是丢掉了好节省（保守）。

### 6.6.6 可选扩展：2×2×2（隔离 run 噪声）

再做一次**对称 re-probe**（在 certaindex 轨迹上补 simple probe），把设计升级为
`轨迹 × timing × readout`，专门量化"真实 69.2→88.7 里有多少只是两次 run 主轨迹
不同（与 probe 无关）"。属 robustness check，非核心问题必需，第二优先。

### 6.6.7 产出物与成功判据

- 脚本 `probe_compare/reprobe_paired.py`：改编自 `run_probe_variants.py`，
  参数 `--probe-suffix {simple|certaindex}` × `--probe-tokens {10|32}`
  （32 档带 `--stop "\]"`），底座 `--stage1-dir results/stage1_logging`，全 500 题；
  probe 输入含 chat prompt（§6.6.4-3）、is_certain/解析对齐（§6.6.4-4）。
  **先跑 `simple@10` 过验证锚点（§6.6.4-6），再跑其余三格**
  （certaindex@10、simple@32、certaindex@32）。
- 脚本 `probe_compare/analyze_2x2.py`（离线）：四格 + 读出/timing 主效应 + 交互项
  + commit 率/条件忠实度 + continuation-match + 105 点分析。
- 产出：`results/probe_paired_2x2/{reprobe_paired.csv, report.md, fig_2x2.png}`；
  同一份数据直接给第 2 步 Pareto sweep 当（更好 probe 的）底座。
- 决策：读出主效应显著（格② 明显高于 69.2%）→ probe 措辞进入 Governor++ 一等
  设计空间（roadmap 第 4 步），并作为第 2 步 Pareto sweep 的候选 probe；
  若几乎全是 timing 效应 → 归并为停机规则的 min_tokens/patience 参数。

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

## 7.5 within-problem K-rollout 实验：晚共识不可靠的因果验证（补 Analysis 3/4，roadmap 第 3 步）

### 7.5.1 动机

Stage 4 观察到"共识形成越晚，最终准确率越低"（>2048 tok 55–58% vs <512 tok
78–87%）。Stage 9 Analysis 1（离线、按 MATH level 分层）已表明这里有**相当一部分
是难度混杂**，但两个 confound 没排干净：(1) **budget 截断** —— Stage 1/9 用的是
3072 旧数据，晚共识题更易撞上限、final 答案被迫截断压低准确率；(2) **难度控制只
到 level 粒度**、且 AIME 没有 level。本实验把这两个 confound 彻底排除，正式补上
Stage 9 deferred 的 Analysis 3（难度匹配对比）和 Analysis 4（recovery 概率）。

### 7.5.2 设计：同题重复 K 次 + 拉满 budget

- **同题 K 次 rollout**：把难度**按构造锁死** —— 同一道题的 K 条 rollout 难度完全
  相同，于是"晚共识不可靠"若在题内依然成立，就是真实的**轨迹级**现象，而非难度
  伪影。这比"跨题分层"强，且**绕开了"如何分层难度"的难题**。
- **max budget**（如 12k，MATH 应使 finish_naturally 近 100%）去掉截断 confound；
  跑完先验证 finish 率、AIME 若 12k 仍截断则单独标出。
- **难度指标 = 经验 pass rate**（K 里答对比例），独立于任何单条轨迹的收敛动态。
  **绝不能用轨迹派生量（token 长度 / entropy / 换答案次数）当难度** —— 它们就是
  共识动态本身，会把要测的效应吸收掉（conditioning on a collider）。
- **规模（并行支线，GPU 贵、非 Governor++ 关键路径）**：MATH 按 pass-rate 跨难度
  抽 ~50 题 + AIME 全 30 题，每题 **K≥8**、budget 12k。K 要够大才能在题内拉开
  consensus_time 分布；N 要够才能让随机效应估得稳、结论泛化。

### 7.5.3 分析（主 = within–between 分解）

**主分析** —— mixed-effects logistic + group-mean centering（Mundlak）：

```
correct ~ ct_within + ct_problemmean + (1 | problem_id)
```
`ct` = consensus_time；`ct_problemmean` = 每题 K 条的均值（难度代理，系数 =
between/难度效应）；`ct_within` = ct 减题内均值（**难度被锁死的 within 效应**）；
随机截距吸收题基线难度。读法：`ct_within` 显著为负 → 晚共识固定难度下仍不可靠
（真轨迹级现象）；≈0 而 `ct_problemmean` 负 → 其实全是难度；两系数之比量化
"naive 晚共识效应里轨迹级 vs 难度各占多少"。

**支撑分析**：
1. 两条校准曲线叠加：pooled（复刻 Stage 4，带 confound）vs within（题内 demean 后
   再 bin）。pooled 陡、within 平 → 难度；都陡 → 真效应。
2. 难度轴：pass rate vs 平均 consensus_time（量化 confound 强度）；按 pass-rate
   五分位分层看各层 ct→acc（主分析的可视化交叉验证）。
3. **两种 "correct" 分开报**：consensus-answer 正确率（共识点停机就交卷对不对，
   = Governor 直接关心的 `P(correct | 共识形成于 T)`）；final 正确率（反映 recovery，
   = Analysis 4）。
4. overthinking 量化：早点已形成**正确**共识、跑到底反而变错的 rollout 数（max
   budget 会放大，正是早停的价值）。
5. never-converged / 截断：从未形成共识的 rollout（尤其 AIME）单独报正确率；报
   max budget 下 finish_naturally 率以验证 budget confound 已去除。

**收尾模型（直接指导 Governor++）**：
```
correct ~ consensus_time + 在线可估难度代理(早期 entropy / 早期换答案率 / 题长)
```
问：扣掉**在线能拿到的**难度代理后，consensus_time 还有无增量预测力？pass rate
离线不可用；若 consensus_time 在控制在线代理后仍显著 → Governor 该用它，否则用
在线难度代理即可。

### 7.5.4 结论 → Governor++ 映射

| 主分析（within 效应）| 对 Governor++ 的含义 |
|---|---|
| within 强、负 | consensus-time / stable-run 是独立可靠性信号，gate 在它上面有理（支持 Stage 7 min_tokens/patience）|
| within≈0、between 强 | 是难度；Governor 该在线估难度来 gate，单看 consensus-time 无用 |
| 两者都在 | 两个都进 gate |

统计提醒：within-problem 是观测关联、非被操纵因果（没法强迫某 rollout 早收敛），
但足以回答"Governor 该不该不信晚共识"，不过度声称因果。

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

## 8.2a 排期：规则型 Governor++ ≈ roadmap 第 2 步，不是"等第 2 步"

规则型 Governor++（roadmap 第 4 步）和 accuracy–compute Pareto sweep（第 2 步）
**几乎是同一个交付物**，不该排成先后等待：

- **组件"过滤无效 probe"现在就能定** —— 来自 Stage 6（single_letter 0% valid、
  空 probe），不依赖后续。
- **min_tokens / 稳定期 / 换答案次数就是第 2 步 sweep 的参数轴** —— 第 2 步扫出的
  获胜配置**本身就是规则型 Governor++**。第 4 步 = 给它套 Stage 6 validity filter
  + 打包成可跑 controller + held-out/Qwen 验证。
- **v0 现在即可拼**：Stage 7 的 Conservative 配置（min_tok=1024 + patience=8 +
  certain → overall 81.0% ≈ vanilla 81.2%）+ Stage 6 validity filter，就是一个
  能用的 baseline；第 1/2 步是为了做**更好的 v1**（顶破 15–21% 省 token 天花板）。
- **第 3 步（§7.5）是并行输入**：告诉你 gate 该放 consensus-time 还是难度。

## 8.3 第二版：Calibrated Governor++

### 8.3.0 何时从规则升级到 calibrator（决策判据）

纪律（Risk 2）：**先证明规则不够，再训。** 训练一个轻量 calibrator 当且仅当以下
三条**同时**满足：

1. **缺口存在**：第一版最优规则撞了 Pareto 天花板（如 Stage 7 那个断崖——保准确率
   只能省 15–21% token），且有理由相信更聪明的信号组合能更好。若规则已补回大部分
   （Stage 7 提示"准确率恢复"基本已解决）→ 别训。
2. **交互/连续映射重要**：safe-stop 决策依赖信号的**非线性组合**，轴对齐阈值网格
   抓不住。判断法：第 2 步 Pareto 前沿若被"多信号组合"配置主导、单信号规则明显更差
   → 交互重要。**最可能的触发场景 = 难度自适应地板**：顶破天花板的关键是"简单题
   早停多省、难题晚停保安全"的按题自适应 `min_tokens = f(在线难度代理)`，这正是
   calibrator 擅长的连续多特征映射（第 3 步 §7.5 若判定难度是关键信号则更成立）。
3. **有训练标签**：safe-stop 标签 = Stage 9 的 `S_t = P(correct 且 terminal)`，
   已具备（见 §8.3 特征/标签）。

**爬梯子，别一步到位**：规则 → 2 档自适应规则（在线难度代理阈值分两档地板）→
calibrator。只有爬到上一级仍有缺口，才上下一级。

**让"要不要训"成为干净的检验**：calibrator 必须**轻量 + 与规则同一套特征**
（logistic/GBM），使它是规则的严格推广（规则 = 轴对齐特例）。于是：
- calibrator ≈ 最优规则 → 交互不重要 → **发规则**（更简单、更可解释，§17
  transparent controller 卖点更强）；
- calibrator ≫ 规则（**held-out + Qwen 上都成立**）→ **发 calibrator**；
- 只在 train 上赢、held-out/Qwen 掉 → 过拟合，别发。



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

## 9.4 结果（2026-07-24，Qwen3-8B / MATH500 全 500 题，单 seed）

`results/stage11_cross_model/qwen3_8b_math500/`。overall accuracy
**78.2%**（vs Stage 1 DeepSeek-7B 同数据集 81.2%），finished naturally
35.0%。window share=1 372 题、window-answer accuracy 89.0%、false
consensus 41 题（11.0%）。Governor 早停模拟：would-stop 340/500，
stopped-answer accuracy 83.5%（早停子集内的 final accuracy 89.7%，
两者分母不同，不要混用）。整体上"跨模型"这一维度上，false consensus
现象和 recovery 现象在 Qwen3-8B 上依然存在，量级与 DeepSeek-7B 接近，
初步支持诊断发现不是单一模型的伪影。仍是单 seed、单模型，还没做
9.1 里列的第 3/4/5 个模型。

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

## 10.3 结果（2026-07-24，DeepSeek-7B，单 seed）

`results/stage12_cross_dataset/`。AMC23（40题）overall accuracy
**60.0%**，finished naturally 37.5%；window share=1 25题、
window-answer accuracy 92.0%、false consensus 2题（8.0%）；Governor
早停模拟 would-stop 31/40，stopped-answer accuracy 67.7%（子集内 final
accuracy 74.2%）。AIME24（30题，最难数据集）overall accuracy
**26.7%**，finished naturally 0.0%（全部超预算截断，说明 budget 对
高难题不够，或题目本身超出模型能力）；cumulative share=1 从未出现
（CR(cumulative)=nan）；window share=1 仅 9题、accuracy 77.8%、false
consensus 2题（22.2%，比例明显高于 MATH500/AMC23，样本量太小需谨慎）；
Governor 早停模拟 would-stop 15/30，stopped-answer accuracy 26.7%（子集
内 final accuracy 53.3%）。样本量小（30-40题），这两个数据集的数字
方差很大，暂不适合下强结论，只作为跨数据集方向的初步信号。GSM8K/
GPQA-Diamond（10.1 里的 4/5）还没跑。

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
3. **Improved Probe 对比** — 🟡 结构化 probe 设计已验证不可行（`results/stage8_probe_compare/`），另做了一版 probe 后缀措辞 ablation（"certaindex" 风格，`results/probe_suffix_ablation/`，DeepSeek-7B/MATH500，overall accuracy 79.6% vs Stage 1 simple probe 81.2%，影响温和）；6.2 的 P0-P4 完整对比仍未做
4. **控制 difficulty 后重新分析 consensus time** — 🟡 离线可做部分已完成（`results/stage9_difficulty/`），Analysis 3/4 待补
5. **Rule-based Governor++**
6. **Calibrated Governor++**
7. **多模型与多数据集复现** — 🟡 Stage 11（Qwen3-8B/MATH500，overall accuracy 78.2%）+ Stage 12（AMC23 60.0%/AIME24 26.7%，DeepSeek-7B）单 seed 结果已跑完并合入 main（`799e827`），见 §9.4/§10.3；9.1/10.1 里排的其余模型/数据集（第 3+ 个模型、GSM8K、GPQA-Diamond）和多 seed 还没做

在前四项完成之前，不进行复杂 verifier、PRM 或大规模训练。

---

# 19. 下一阶段 roadmap（teammate 五步）

teammate 给出的下一步五步，及讨论后的排期/细化：

1. **Paired probe：忠实读出 vs 保守 timing** — 🎯 **实验已设计完（见 §6.6）**，是整条
   链的枢纽（其结果决定 probe 措辞该进 Governor++ 核心还是并入停机规则）。做法：
   在 simple 的 500 条轨迹上密集 re-probe certaindex，做单轨迹基 2×2 析因
   （timing × readout）+ continuation-match。**先做这一步。**
2. **Accuracy–compute Pareto sweep** — 扫 min_tokens / patience / window / threshold /
   history stability，比较准确率、总 token、触发率、错误停机率。注意这是**扩展
   Stage 7（已有 142 配置，见 §5）**，应在第 1 步选出的 probe 上跑，并加**按难度
   分层**的 breakdown。
3. **晚共识不可靠的因果验证** — 🎯 **实验+分析已设计完（见 §7.5）**。定稿方案不是
   "跨题分层"而是 **within-problem K-rollout**（同题跑 K≥8 次 + max budget 12k，
   难度按构造锁死），主分析用 within–between 分解（mixed-effects + Mundlak），正式
   补 Stage 9 deferred 的 Analysis 3/4。**与 1/2 独立，降级为 GPU 并行支线**（MATH
   ~50 题跨难度 + AIME 30，非 Governor++ 关键路径）。
4. **Rule-based Governor++（= Stage 10 v1，§8.1）** — 过滤无效 probe（Stage 6/3）+
   限制最早停止时间（Stage 9/4）+ 更长稳定期（Stage 4/5）+ 历史换答案次数
   （Stage 4 recovery）。依赖第 1、2 步结论。
5. **轻量 calibrator（= Stage 10 v2，§8.3）** — **gating 在第 4 步之后**：先看规则版
   能否补回大部分损失，不够再训（Risk 2）。特征用 Stage 9 逻辑回归里最强的
   hit_token_cap / level / entropy / answer switches + Stage 6 validity，保持
   logistic/GBM 轻量。

讨论中补充的三条（未定）：
- **跨模型 holdout**：1–4 步都在 DeepSeek-7B 上做，把 **Qwen3-8B 留作最终验证集**
  （Stage 11 显示其假共识率 11% > DeepSeek 6.5%，阈值不能直接搬），别在它上调参。
- **先定 headline 成功指标**：如"恢复 naive 3-probe 规则损失准确率的 ≥X%，同时
  保留其 token 节省的 ≥Y%"（见 §8.7），否则 Pareto 扫完不知道选哪个点。
- **多 seed**：至今全单 seed；最终 Governor++ 配置需多 seed 出方差，1–2pp 改善才
  说得清是否噪声。

## 2026-08-02 更新：v2 sweep 完成，论文第二版核心已改

**已完成**：
- 统一 (W,s) 规则空间（3,520）+ 新三档 gate（total drop/saving/psf），protocol_v2/select_v2。
- DEER 联合 sweep（trial-answer-submit）。核心结论：consensus 0/3520 过 gate，DEER 三档全过。
- 修复 answers_equal 的 grader import bug（弱 grader → robust），重跑 dev+test。
- 泛化：test r=0.98（联合 gate 空 for consensus，DEER 联合过）、32B r=0.95、Llama r=0.87。
- 论文全节按 CORE_PAPER_FLOW 改写并干净编译。

**待办**：
1. 把 scratchpad 的 v2 结果（v2_sweep_r/v2_sweep_test/deer_sweep）迁入 results/ 正式库、加 report.md、提交。
2. DEER 在 32B/Llama 的 confidence bank 需 GPU 补采，才能补全 DEER 侧四轴泛化。
3. tab:baselines（faithful CertaIndex/TJE/DEER 复现）沿用旧 related_work 数字，如需与 robust grader 一致可复核。
4. 视觉验收：本机无 poppler，未逐页渲染 PDF；需装 poppler 或在别处渲染核对版面。
5. 03_false_consensus 附录与 08_boundary_confidence（探索性）未深改，可后续对齐 (W,s) 术语。

### 2026-08-02（续）
- v2 结果已落库 `results/governor_v2_ws_sweep/`，旧 sweep 已归档 backup_v1_sweep_20260802/。
- 待用户确认后做一次集中 commit（含 paper/ 修改、新脚本、新 bank、归档）。
