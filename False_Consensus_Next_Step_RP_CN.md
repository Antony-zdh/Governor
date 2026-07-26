# When Is Consensus Safe to Stop?

## 下一阶段研究计划：从机制诊断到可泛化的 Reliability-Aware Governor

- **项目方向：** Adaptive Reasoning / Test-Time Scaling / Early Stopping
- **当前基础：** DeepSeek-R1-Distill-Qwen-7B、Qwen3-8B、MATH-500、AMC23、AIME24，已完成 probe 对照、规则 sweep、同题多轨迹机制分析
- **目标：** 判断当前工作是否达到主会水平，并完成下一阶段所有必要实验，使论文形成“机制发现 + 控制策略 + 泛化验证”的完整闭环。

---

# 0. 2026-07-27 修订：多环境规则开发与 adaptive probing

本节覆盖后文中“直接冻结当前 conservative/balanced 后做最终测试”的旧顺序。上一轮
结果说明现有规则能保住准确率，但 token saving 很弱；它们更适合作为 v1 baseline，
而不应在同一批 MATH500 结果上继续局部调参后直接宣称最优。

下一轮先收集可复用的 **simple@32 dense + event-adaptive probe 序列库**，再在
题目级独立 train/dev/test 上开发规则。完整实现和运行命令见
[`benchmark/FalseConsensus/governor_v2/README.md`](benchmark/FalseConsensus/governor_v2/README.md)。

## 0.1 数据切分

对三个 active benchmark 分别做题目级 **60/20/20**：

- train：宽搜索和 Pareto 初筛；
- dev：跨环境门槛、选择 conservative/balanced/token-efficient 三个互异
  Pareto 点并冻结规则；
- test：冻结后只运行一次；
- MATH500、AMC23、AIME24 都按题目级 60/20/20 切分。对应数量分别为
  300/100/100、24/8/8、18/6/6；后两者显式覆盖默认“小数据集只做
  external stress”的策略，以便在 train/dev 阶段开发针对难题的规则。

选择 60/20/20 是本项目的统计功效取舍，不是通用常数。它让 MATH500 有
300/100/100，而规则搜索所依赖的 dev 和最终 test 各保留 100 题。题目是 group：
同题的所有 model、seed、probe schedule 和 rule 结果必须跟随同一 split。MATH500
在题内随机前按 `level × subject` 分层；跨 benchmark 的重复题面也不得跨 split。

由于现有 MATH500 已被反复查看，其 v2 test 只能视为“内部锁定测试”，不能恢复为严格
untouched。最终确认仍需要新 seed，以及至少一个此前未用于规则开发的数据源。

## 0.2 什么能够被优化

必须严格区分两类变量：

| 类型 | 变量 | 用法 |
|---|---|---|
| 环境变量 | model、main seed、benchmark、题目/预先给定难度、budget | 构造多元环境、分层汇报和稳健性门槛；不能直接写入规则分支 |
| 规则维度 | probe、validity、maturity、evidence、persistence、certainty、history | 可在 train/dev 上优化；只能读取当前时刻可见的通用在线信号 |

其中 `probe` 明确包含 style、output cap、首次 probe 时刻、interval/phases，以及
event trigger、阈值、alignment、cooldown 和 periodic fallback。因此“每
64/128/256 token probe”和“在某类在线事件后 probe”都是同一个规则维度的不同值，
不是新增环境变量。difficulty 标签不能成为运行时捷径；如果需要自适应，应使用截至
当前可见的局部 entropy、语言转折或答案候选等通用信息。

本轮预注册四类 event trigger：

- `conclusion_marker`：therefore、thus、hence、consequently、conclude 等
  strict marker；
- `entropy_drop`：冻结序列上 teacher-forced top-k entropy 的局部突降；
- `reflection_transition`：wait、however、alternatively、check 等重新审视信号；
- `answer_candidate`：boxed、final answer、answer is 等答案候选信号。

还包括上述事件的 hybrid。匹配位置向后对齐到最近的 step boundary，并设
64/128-token cooldown，防止标点或短语簇产生 probe storm。entropy 是对已经生成的
完整 frozen trajectory 做 teacher-forced scoring；它只决定 probe 位置，不重采样、
不改写原序列。周期 fallback 来自已有 dense-64 bank。

每条规则均使用同一个七维嵌套 schema。latest、window-share、entropy 等只是
`evidence.family` 的不同值，不再各自拥有无法统一消融的一套扁平参数。
`history.maximum_switches` 只统计滑动窗口，例如最近 2,048 token 或最近 16 个
probe，不能累计整条序列；否则早期超过阈值后规则将永久失去停止机会。

## 0.3 多环境采集

开发环境以 `benchmark × model × seed` 为统计单元。第一版参数矩阵使用：

- development models：DeepSeek-R1-Distill-Qwen-7B、Qwen3-8B；
- development seeds：42、43、44；
- confirmation seeds：开发模型使用 45、46、47；
- held-out architecture：DeepSeek-R1-Distill-Llama-8B，仅 confirmation seed 45；
- held-out scale：DeepSeek-R1-Distill-Qwen-32B，仅 confirmation seed 45；正式
  实验在 2×A100-80GB 上使用 tensor parallel 2，不能用其结果参与规则筛选；
- benchmarks：MATH500、AMC23、AIME24 都用于题目级 train/dev/test。
  GSM8K 已从本轮 development 与 confirmation 中移除；
- 采集上限与评估 budget 分开。5% 是利用 prior/pilot 选择 cap 时的设计目标，不是
  主实验结束后的验收门槛；cap 必须预先冻结，实际截断率超过 5% 也不能据此事后修改。
  test 不参与选择。当前设置为 MATH500 16K、AMC23 16K、AIME24 32K；随后从
  同一长轨迹离线评估预注册的 3K/8K/16K/32K
  operating budgets。达到采集上限的序列作为 right-censored 单独报告。

主轨迹和 probe 必须解耦：每题只生成一次完整主文本。随后先在冻结前缀上每 64 token
采集 simple@32，再做一次 teacher-forced entropy scoring，并仅在 event candidate
中 dense bank 尚未覆盖的位置补采 simple@32。正式 dense bank 覆盖
64/128/192/...；离线规则从两个 bank 的并集中选择 fixed、phased、
agreement-adaptive 或 event-adaptive schedule。当前不补采 32-token offset bank。
同一 event position 若恰好落在 dense-64 网格上，直接复用已有 probe，不重复请求。
因此改变 probe frequency 或 adaptive trigger 都不会改变主生成随机轨迹。

宽搜索由原 16,848 条固定/聚合规则增加 864 条 adaptive-event 规则，共
17,712 条。adaptive 模板只保留 4 个 schedule：conclusion、entropy drop、
reflection+answer、hybrid；再与 validity、
maturity、evidence、persistence、certainty、history 的紧凑网格组合。筛选后仍对
统一七维做 one-at-a-time 和 \(2^7\) factorial；若 winner 使用 adaptive schedule，
`probe` 消融会整体替换触发类型、阈值、cooldown 和 fallback。

## 0.4 选择标准

不把所有题目 micro-pool 成一个平均数，而是在每个
`benchmark × model × seed` 环境先算 accuracy 和真实总 token：

1. train 上全量搜索并做 Pareto/accuracy gate 初筛；
2. dev 上检查逐模型、逐 benchmark 的最大允许准确率下降；
3. 要求至少 80% 环境有正 token saving；
4. 以环境级 saving 的第 20 百分位为主要排序量，避免规则只靠少数环境拉高均值；
5. 在“最大化 dev saving 第 20 百分位、最小化最差逐模型/逐 benchmark
   accuracy drop”三个目标上构造非支配前沿，依次冻结 conservative、balanced、
   token-efficient 三个互异 rule ID；门槛分别为 1.5/2.0pp + 80%、
   2.5/3.0pp + 80%、4.0/5.0pp + 70%；
6. select 必须验证全部 17,712 条规则、36 个 development 环境均完整且无重复；
   任一 profile 找不到互异非支配点就失败，不能重复同一个 rule ID；
7. test 只评估一次，不因 test 结果回改阈值。

## 0.5 筛选后的七维消融

对每个最终规则都必须做：

- 七个 one-at-a-time reference replacement；
- 七维 selected/reference 的完整 \(2^7=128\) factorial。

probe 和 evidence 是决策所必需的，不能字面“删除”；它们分别替换为预注册的固定
simple@32/128 schedule 和 latest evidence。其他维度使用尽可能中性的 reference。
所有 cell 共用同一批 frozen trajectory 和 probe bank，只离线改变规则，避免重新采样
造成的比较噪声。

## 0.6 8×A100 执行预算

全部预注册实验包含 4 个模型、所有 seed 和 3 个 benchmark，共 3,648 条 main
trajectory；development/confirmation 矩阵分别为 54/72 个 stage。若模型已经缓存，
机器为 8×A100-80GB + NVLink、无共享排队且启用 prefix caching，预计：

- main generation：1.2–2.0 小时；
- dense-64 simple@32 bank：2.0–3.2 小时；
- entropy scoring + event-only probe：0.5–1.0 小时；
- 启动、smoke、重试及与本地 CPU sweep 重叠后的总墙钟：**4.5–7.0 小时**。

32B 使用 2×A100-80GB tensor parallel，其余卡运行独立 7B/8B replica。上述范围以
每模型三题 smoke 校准为前提，并含约 10–15% 重试余量。若是 A100-40GB，32B 约需
4 卡且并发下降，总时间预计 6.5–9.5 小时。CGRS/TALE 等需要
重生成主轨迹的 related-work 复现不计入此预算。

---

# 1. 当前是否已经达到 Main 水平？

## 1.1 当前判断

**目前已经接近一篇有竞争力的 Findings / Borderline Main 工作，但还不能稳称为 Main-ready。**

当前工作已经具备三个明显超过普通 pilot 的部分：

1. **有跨模型、跨数据集的现象复现。** 结果不再局限于单模型、十几道题或单个 heuristic。
2. **有较干净的机制拆分。** probe wording 的收益被分解为 readout effect 与 timing effect；“晚共识更差”被分解为题间难度混杂与题内轨迹效应。
3. **有从机制到控制规则的闭环。** validity、minimum reasoning maturity、certainty 与 persistence 均有实验依据，而不只是调参列表。

但离稳定的 Main 还差四块硬证据：

- 最终规则尚未在**真正 untouched 的新 seed / 新测试集**上一次性确认；
- 关键结果大多仍是**单 seed**，1-2 个百分点差异的方差未知；
- 最终方法与 CertaIndex 类规则相近，需要证明贡献不是“把 patience 调大”；
- 还缺一个清晰的、跨模型成立的 **accuracy-compute Pareto 主结果**，以及与正式相关基线在同协议下的公平比较。

因此当前状态更准确地说是：

> **Scientific story 已经有 Main 潜力；experimental closure 还没完成。**

## 1.2 达到 Main 的最低门槛

论文至少需要同时满足：

1. **冻结三个互异 operating points**：conservative、balanced、token-efficient；
2. 在新 seed / untouched evaluation 上，两个模型均显示稳定 Pareto 改善；
3. 与原始 CertaIndex、naive consensus、fixed-budget、entropy baseline 同协议公平比较；
4. 证明四个设计成分至少有三个是可复现必要的，而不是偶然 sweep 赢家；
5. 核心机制结论在新样本上成立：
   - wording 增益主要来自 timing；
   - pooled late-consensus degradation 主要由题目难度解释；
   - recovery 显著多于 overthinking；
6. 报告真实总成本，而不仅是 main reasoning token。

---

# 2. 论文核心主张

建议最终论文不要把主贡献写成“提出了一个全新的 Governor++”。更合适的主张是：

> **Agreement is useful but insufficient for safe early stopping. Reliable control requires valid, mature, confident, and persistent consensus.**

中文表述：

> 一致性是有用信号，但不是安全停止条件。可靠的推理控制必须同时判断答案是否有效、推理是否成熟、模型是否确定，以及共识是否足够持久。

论文由三层构成：

## 2.1 机制诊断

- 局部 agreement 经常是 transient，而不是 terminal；
- recovery 远多于 overthinking，因此过早停机存在结构性风险；
- probe wording 的表面收益主要来自推迟停止，而不是更真实地读取内部状态；
- 绝对意义上的晚共识低准确率，主要是难题混杂与 token cap，而不是同题内“停得晚所以更差”。

## 2.2 设计原则

Safe stopping 需要四个维度：

| 维度 | 当前实现 | 防止的问题 |
|---|---|---|
| Validity | `schema` | 空串、截断、非选择题 A-D 等 probe artifact |
| Maturity | `fixed1024` 或 level floor | 推理尚未展开时被迫给答案 |
| Confidence | `certain` | 模型仍显式犹豫、自我修正 |
| Persistence | `p8` 或 `p5` | 短暂局部共识被误判为终局 |

## 2.3 方法验证

不是只给一个规则，而是给出一个**可解释 policy family**：

\[
\text{Stop}(t)=V_t \land M_t \land C_t \land P_t,
\]

其中：

- \(V_t\)：probe 是否有效；
- \(M_t\)：是否达到最小推理成熟度；
- \(C_t\)：是否满足 certainty 条件；
- \(P_t\)：是否达到持续一致的 patience 要求。

最终展示两个工作点：

- **Conservative:** `p8 + fixed1024 + certain + schema`
- **Balanced:** `p5 + level768/2048 + certain + schema`

---

# 3. 下一阶段实验总览

下面按优先级给出必须完成的实验。

| 优先级 | 实验 | 目的 | 是否必须 |
|---|---|---|---|
| P0 | 冻结规则后的新 seed + untouched evaluation | 获得无偏最终估计 | 必须 |
| P0 | 正式 baseline 复现与同协议对比 | 证明不是仅优于弱 baseline | 必须 |
| P0 | 多 seed 方差与统计检验 | 判断 1-2pp 差异是否真实 | 必须 |
| P1 | 四组件 factorial ablation | 证明规则设计有机制依据 | 必须 |
| P1 | 总计算成本核算 | 验证真实 efficiency | 必须 |
| P1 | 同题 K-rollout 结果复现 | 稳固机制结论 | 强烈建议 |
| P1 | 新模型泛化 | 避免只对 Qwen-family 成立 | Main 强烈建议 |
| P2 | 新数据集泛化 | 扩展到非 MATH 风格任务 | Main 建议 |
| P2 | adaptive probing | 降低 probe 调用成本 | 可作为增强 |
| P3 | calibrator | 仅在规则出现稳定残余缺口时启动 | 当前不做 |

---

# 4. Experiment A：冻结规则与真正 Untouched Evaluation

## 4.1 目的

当前 validation-2 和 matched Qwen 都参与了 21 个候选的筛选，因此它们不能再被称为最终测试。下一步必须冻结方法后，在未参与任何选择的新数据上一次性评估。

## 4.2 冻结规则

在开始新实验前，代码与参数全部冻结：

### Conservative

```text
patience = 8
min_tokens = 1024
validity = schema
certainty = on
history constraint = none
```

### Balanced

```text
patience = 5
min_tokens = 768 for MATH level 1-3
min_tokens = 2048 for MATH level 4-5
validity = schema
certainty = on
history constraint = none
```

冻结后禁止根据新测试结果修改任何参数。

## 4.3 Evaluation 数据

推荐两种方案并行：

### 方案 A：新 generation seeds

对 MATH-500 全部 500 题，运行：

```text
seeds = {43, 44, 45}
```

模型：

- DeepSeek-R1-Distill-Qwen-7B
- Qwen3-8B

每个模型、每个 seed 都完整 logging，然后离线回放：

- full generation；
- naive p3；
- CertaIndex baseline；
- Conservative；
- Balanced。

### 方案 B：新题集 untouched test

从未参与开发的数据中选择：

- MATH test 额外 500-1000 题；或
- OlympiadBench / Minerva Math 的可自动判分子集；
- 若资源有限，至少使用新的 MATH-style 500 题。

参数完全冻结，一次性运行。

## 4.4 主要指标

每个方法报告：

| Metric | 定义 |
|---|---|
| Accuracy | 停机答案最终正确率 |
| Delta Accuracy | 相对同轨迹 full generation |
| Stop Coverage | 触发 early stop 的题目比例 |
| False-stop Rate | 触发后答案错误比例 |
| Main Tokens | 主 reasoning token |
| Probe Output Tokens | probe 输出 token |
| Total Generated Tokens | main + probe output |
| Wall-clock | 实际延迟 |
| Recovery Killed | 本可继续改对但被停掉的数量 |
| Overthinking Prevented | 本来会由对变错、被早停避免的数量 |

## 4.5 成功门槛

### Conservative

- 两个模型平均 accuracy drop 不超过 1.5pp；
- 至少节省 12%-20% total generated tokens；
- 至少 2/3 seeds 均位于 full generation 左侧的 Pareto 区域。

### Balanced

- 平均 accuracy drop 不超过 3pp；
- 至少节省 25%-30% total generated tokens；
- 不允许某个模型稳定掉点超过 5pp。

---

# 5. Experiment B：正式 Baseline 对比

## 5.1 必须比较的方法

### B0：Full Generation

完整跑到 EOS 或 token cap。

### B1：Fixed Budget

```text
cap ∈ {512, 1024, 1536, 2048, 3072}
```

用于回答：同样 token 成本下，动态规则是否优于简单硬截断？

### B2：Naive Agreement

```text
p3 + no floor + nonempty
```

用于展示错误共识的原始风险。

### B3：CertaIndex-style Baseline

必须严格复现原论文/原实现的：

- probe prompt；
- patience；
- share 定义；
- certainty 或犹豫词条件；
- token interval；
- stop logic。

若原方法没有完全对应的开源实现，要明确区分：

- faithful reproduction；
- adapted baseline。

### B4：Entropy Threshold

至少 sweep：

```text
entropy_threshold ∈ {0.1, 0.2, 0.3, 0.4}
min_tokens ∈ {0, 512, 1024}
patience ∈ {1, 3, 5}
```

### B5：Self-consistency / Majority Share

最近窗口 dominant share：

```text
window ∈ {3, 5, 8}
share ∈ {0.8, 1.0}
```

### B6：Conservative Governor

`p8 + fixed1024 + certain + schema`

### B7：Balanced Governor

`p5 + level768/2048 + certain + schema`

## 5.2 公平性要求

所有方法必须使用：

- 相同主模型；
- 相同 temperature / top-p；
- 相同 probe interval；
- 相同 probe stream，除非方法本身定义了不同 probe；
- 相同 token accounting；
- 相同 answer normalization；
- 相同 seeds。

## 5.3 主图

### Figure 1：Accuracy-Compute Pareto

- x-axis：平均 total generated tokens；
- y-axis：accuracy；
- 每个模型单独一幅；
- Conservative 与 Balanced 用醒目标记；
- fixed-budget 连成一条基线曲线。

### Figure 2：Risk-Coverage Curve

- x-axis：stop coverage；
- y-axis：false-stop rate；
- 展示 aggressive stop 的风险随覆盖率如何上升。

---

# 6. Experiment C：四组件 Factorial Ablation

## 6.1 目的

避免论文被评价为：

> “只是把 CertaIndex 的 patience 从 3 调到了 8。”

必须证明 validity、maturity、certainty、persistence 各自解决不同失败模式。

## 6.2 设计

以 Conservative 为基础，做 2x2x2x2 factorial：

| 组件 | Off | On |
|---|---|---|
| Schema validity | nonempty only | schema-aware |
| Minimum maturity | 0 | fixed1024 |
| Certainty | off | on |
| Persistence | p3 | p8 |

理论上 16 个配置，全部可在现有 logging 上离线回放。

如果某些组合逻辑重复，可保留至少以下 8 个核心配置：

1. p3 only
2. p8 only
3. p3 + fixed1024
4. p8 + fixed1024
5. p8 + schema
6. p8 + certain
7. p8 + fixed1024 + schema
8. full Conservative

## 6.3 分解指标

除 accuracy/token 外，分别统计：

- `schema` 消除多少空串/字母型 false stop；
- `fixed1024` 消除多少早期 tentative consensus；
- `certain` 消除多少仍含 wait/but/hmm 的不稳定 stop；
- `p8` 消除多少后续发生 recovery 的 transient stop。

## 6.4 预期论文结论

不能只说“full rule 最好”，而要说：

> Each component targets a distinct failure mode: schema filters invalid readouts, minimum maturity suppresses forced early guesses, certainty excludes active self-correction, and persistence separates transient from terminal consensus.

---

# 7. Experiment D：Recovery 与 Overthinking 的稳健性复现

## 7.1 目的

当前 127 vs 10 的不对称是非常强的机制 finding，需要确认不是单 seed 偶然。

## 7.2 设置

在新 seeds 上，对每条 trajectory 找到首次满足：

```text
last-5 valid probe dominant share >= 0.8
```

记录：

- 当时 consensus 是否正确；
- 后续最终答案是否正确；
- 是否改变答案；
- 是否自然结束；
- 是否撞 cap。

## 7.3 四类转移

| 起始共识 | 最终答案 | 类型 |
|---|---|---|
| Wrong | Correct | Recovery |
| Correct | Wrong | Overthinking |
| Correct | Correct | Stable correct |
| Wrong | Wrong | Persistent wrong |

## 7.4 报告方式

- 每个模型、每个 seed 的四类数量；
- Recovery / Overthinking ratio；
- bootstrap 95% CI；
- 按 token position、难度、是否 cap 分层。

## 7.5 成功门槛

若两个模型、3 seeds 中 recovery 始终明显多于 overthinking，可把它作为核心机制结论。

---

# 8. Experiment E：Within-Between Consensus Time 复现

## 8.1 目的

稳固以下结论：

> pooled 数据中“晚共识更差”主要是题间难度混杂；同题内晚共识并不会降低最终正确率，并且更可能正确、更 terminal。

## 8.2 扩展设置

当前：80 题 x 8 rollouts。下一阶段建议：

- MATH：100 题 x 8 rollouts；
- AIME：30 题 x 8 rollouts；
- 新 seed 或新模型重复一次；
- budget：MATH 8192，AIME 16384 或更高。

## 8.3 模型

继续使用 mixed-effects model：

\[
Y_{ij}=\beta_0+\beta_w CT^{within}_{ij}+\beta_b CT^{between}_j+u_j+\epsilon_{ij}.
\]

结果变量分别为：

- final correctness；
- consensus correctness；
- terminality；
- recovery probability。

## 8.4 必做敏感性分析

- consensus threshold：0.6 / 0.8 / 1.0；
- window：3 / 5 / 8；
- 排除 token-cap trajectories；
- 只看 natural finish；
- 按 MATH level 分层；
- 用 raw token 与 log2 token 两种 CT。

## 8.5 表述边界

若 final correctness 的 within effect 仍不显著：

> There is no evidence that later within-problem consensus harms final correctness.

不要写：

> Later consensus improves final correctness.

但若 consensus correctness 与 terminality 持续显著为正，可以强调：

> Within the same problem, later consensus is more likely to be correct and terminal.

---

# 9. Experiment F：真实 Compute Accounting

## 9.1 目的

避免仅以 main reasoning token 宣称效率提升。

## 9.2 记录项

每次运行记录：

```text
main_decode_tokens
probe_decode_tokens
number_of_probe_calls
prompt_prefill_tokens
wall_clock_seconds
GPU_seconds
peak_memory
```

如果 vLLM prefix caching 开启，额外记录：

- cache hit rate；
- 每次 probe 的平均 latency；
- 主生成与 probe 的 scheduler 干扰。

## 9.3 三种成本口径

1. **Main-token saving**：与已有报告保持连续；
2. **Total generated-token saving**：main + probe decode；
3. **Wall-clock / GPU-time saving**：最终主结论。

## 9.4 Adaptive Probing（本轮必做）

除 phased/agreement-adaptive schedule 外，加入 conclusion marker、entropy drop、
reflection transition、answer candidate 及 hybrid event schedule。比较对象包括：

- fixed 64/128/256；
- strict conclusion-marker probing；
- 单一中等阈值的 entropy-drop probing；
- reflection+answer probing；
- hybrid event probing。

所有 event rule 带 cooldown 和 dense-bank periodic fallback。报告同时给 probe
调用数、probe decode token、prompt prefill、entropy-scoring GPU time 与总墙钟，
并把 adaptive winner 的整个 `probe` 维度纳入统一消融。

---

# 10. Experiment G：冻结后的跨架构与跨规模泛化

## 10.1 目的

开发模型都与 Qwen 架构关系较近，因此把架构和规模泛化作为严格 held-out
confirmation，而不是把新模型加入规则搜索扩大选择空间。

## 10.2 模型选择

已冻结两个互补模型：

- `deepseek-ai/DeepSeek-R1-Distill-Llama-8B`：验证不同 backbone architecture；
- `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B`：验证同 distillation family
  下的规模泛化。

二者都不能进入 sweep、Pareto 初筛或三个 operating point 的选择；必须先在两个
development model 的 train/dev 上冻结完整规则与 hash manifest。

## 10.3 最小实验

冻结后统一跑：

- MATH500 的 test split；
- AMC23/AIME24 test split；
- seed 45；
- 相同的 frozen main + dense/event-adaptive simple@32 架构；
- conservative、balanced、token-efficient 及预注册的七维消融，不重新挑阈值。

## 10.4 成功标准

不要求 held-out 模型拥有各自最优参数；恰恰要验证同一冻结规则是否仍满足逐模型
accuracy gate、是否在大多数环境保持正 token saving，以及七维贡献方向是否一致。

---

# 11. Experiment H：跨数据集泛化

## 11.1 优先顺序

1. **GPQA-Diamond**：多选科学推理，验证 schema 需任务感知；
2. **AIME24/25**：继续作为能力边界压力测试。

## 11.2 GSM8K

本轮取消，不进入 development、confirmation、规则筛选或主结果。现有物化数据和
split 文件只作为历史 artifact 保留，不触发 GPU 作业。

## 11.3 GPQA-Diamond

多选任务中 `A/B/C/D` 是合法答案，因此 `schema` 不能简单过滤字母。

实现 task-aware schema：

```text
schema_numeric
schema_symbolic_math
schema_multiple_choice
schema_text
```

这能把“schema-aware validity”提升为可泛化设计原则，而不是 MATH 特定 hack。

## 11.4 AIME

- budget 至少 16384；
- 单独报告 natural finish 与 cap；
- 不把 cap 轨迹与完整轨迹混为一谈；
- 测试 Conservative 是否几乎不触发，以及这是否合理。

---

# 12. CertaIndex 相似性如何处理

## 12.1 不要回避相似性

最终规则与 CertaIndex 相似是事实。论文中应主动说明：

> Our goal is not to replace consensus with a fundamentally different signal, but to identify when consensus is safe and which safeguards are necessary.

## 12.2 贡献区别

不要把 novelty 放在“连续一致”本身，而放在：

1. **readout-vs-timing 的因果拆分**；
2. **within-between 难度混杂分析**；
3. **recovery-overthinking 不对称**；
4. **validity / maturity / confidence / persistence 四因素框架**；
5. **在统一协议下给出风险-计算 Pareto，而不是单点结果**。

## 12.3 命名建议

避免强行起一个完全新算法名。可以使用：

- **Reliability-Aware Consensus Governor**
- **Safe Consensus Policy**
- **Validated Persistent Consensus (VPC)**

其中 VPC 可以表示：

> Valid + mature + certain + persistent consensus。

但论文主标题仍应偏分析，而不是方法包装。

---

# 13. Calibrator 的启动 Gate

当前继续维持 **No-Go**。

只有同时满足以下条件才训练 calibrator：

1. 新 seeds 上规则 Pareto 出现稳定残余缺口；
2. 至少一个简单规则无法同时满足 accuracy 与 compute 目标；
3. 有明确的非线性交互证据，例如相同 patience 在不同 entropy/switch history 下风险显著不同；
4. safe-stop 标签数量足够，并有独立 test。

若启动，优先：

- logistic regression；
- shallow decision tree；
- gradient boosting。

不应直接使用大 verifier，以免论文从机制工作变成不可解释的额外模型堆叠。

---

# 14. 统计分析规范

## 14.1 多 seed 汇总

报告：

```text
mean ± standard deviation
95% bootstrap confidence interval
```

## 14.2 Paired Accuracy Test

同一题同一 seed 的方法比较：

- McNemar test；
- paired bootstrap accuracy difference。

## 14.3 Token/Latency Test

- paired bootstrap；
- 报告 median 与 mean；
- latency 分布通常偏斜，补充 IQR。

## 14.4 多候选选择偏差

最终 untouched test 只能在规则冻结后运行一次。不能看完后继续修改规则。

## 14.5 Effect Size

除 p-value 外，必须报告：

- accuracy difference（pp）；
- relative token saving；
- false-stop difference；
- recovery killed difference。

---

# 15. 最终论文 Figure / Table 规划

## Figures

### Figure 1：Why Naive Consensus Fails

多个模型/数据集上，early-stop accuracy 与 continue-to-end accuracy 的成对比较。

### Figure 2：Probe Wording Decomposition

2x2 timing/readout factorial，显示 timing 主效应远大于 wording readout 主效应。

### Figure 3：Within-Between Consensus Time

左：pooled absolute CT；右：within-problem centered CT；展示难度混杂。

### Figure 4：Recovery vs Overthinking

四类状态转移图，突出 recovery 远多于 overthinking。

### Figure 5：Accuracy-Compute Pareto

full、fixed cap、naive、CertaIndex、Conservative、Balanced。

### Figure 6：Ablation by Failure Mode

每个组件消除哪类 false stop。

### Figure 7：Cross-model Generalization

不同模型上的 accuracy drop、token saving、false-stop。

## Tables

### Table 1：实验设置与数据统计

### Table 2：核心机制结果

### Table 3：正式 baseline 对比

### Table 4：四组件 ablation

### Table 5：多 seed / untouched test 主结果

### Table 6：跨模型、跨数据集结果

---

# 16. 两周执行计划

## Day 1

- 冻结 Conservative / Balanced；
- 固定 commit、配置与数据 manifest；
- 写 evaluation protocol。

## Day 2-4

- DeepSeek 新 seed 1-3；
- 完整 logging；
- 运行 baseline 回放。

## Day 5-7

- Qwen 新 seed 1-3；
- 运行完全相同协议；
- 输出多 seed 主表。

## Day 8

- 完成 16-cell factorial ablation；
- 按失败类型分解收益。

## Day 9

- 加入真实 wall-clock / GPU-time accounting；
- 重画 accuracy-compute Pareto。

## Day 10

- 复现 recovery / overthinking；
- 输出每 seed 的 ratio 与 CI。

## Day 11

- 复现 within-between 模型；
- 完成 natural-finish / no-cap sensitivity。

## Day 12-13

- 跑第三模型或新 untouched dataset；
- 若资源不足，优先第三模型 MATH500 单 seed。

## Day 14

- 冻结全部主结果；
- 写论文 Results / Analysis 初稿；
- 决定是否满足 Main submission gate。

---

# 17. Main Submission Gate

完成上述实验后，用下面标准做一次 go/no-go 判断。

## Go for Main

满足至少 5 条：

- Conservative 在两个模型、多个 seed 上 accuracy drop ≤1.5pp；
- Conservative total compute saving ≥15%；
- Balanced 在两个模型上保持稳定 Pareto；
- timing-vs-readout 结论跨 seed 稳定；
- recovery 显著多于 overthinking；
- within-between 结论通过敏感性分析；
- 与 CertaIndex faithful baseline 相比有稳定 Pareto 优势；
- 第三模型或新数据集复现设计原则；
- 四组件 ablation 显示每个组件对应独立失败模式。

## Borderline Main / Strong Findings

- 机制结论很稳；
- Conservative 仅在一个模型明显有效；
- 方法相对 CertaIndex 增益不稳定；
- 跨模型参数迁移较弱。

此时可以把论文定位为 analysis-first，投 ACL/EMNLP Findings 或相近 venue。

## No-Go

- 新 seed 上规则收益消失；
- 总 compute accounting 后没有真实节省；
- CertaIndex 在公平协议下完全支配当前规则；
- 核心机制结果无法复现。

---

# 18. 最终结论

当前项目已经具备 Main 论文所需的核心故事，但尚缺最终实验闭环。下一阶段不应继续无限扩展 heuristic，也不应马上训练 calibrator。最关键的是：

1. 冻结 Conservative 与 Balanced；
2. 做新 seed 与真正 untouched evaluation；
3. 在同协议下公平比较 CertaIndex 等正式 baseline；
4. 用 factorial ablation 证明四个设计原则各自解决不同失败模式；
5. 报告总计算成本；
6. 用第三模型或新数据集验证泛化。

若这些实验成立，论文可以明确主张：

> Consensus-based stopping is not inherently unreliable; it becomes safe only when the observed agreement is valid, sufficiently mature, confident, and persistent.

这会比“我们找到一个 p8 规则”更接近主会水平，也更难被 reviewer 简单归类为参数调优。
