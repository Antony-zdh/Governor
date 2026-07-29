# Finding-Experiment 质询日志

用途：逐项记录对 `Governor_Finding_Experiment_Map.pdf` 的质询、证据核查、颜色判定和修改队列。这里的颜色针对论文 claim 的证据状态，而不是评价研究方向本身。

- **红色**：现有表述不可靠、量词过强、证据被误用，或被现有消融反驳。
- **蓝色**：claim 尚未被当前实验直接验证；附上升级所需的最小实验。
- **绿色**：claim 在明确限定的模型、benchmark、split、seed 和计费口径内有直接可靠证据；附上论文证据指针。

在完成对应修改前，每一组保留 `待实施` 状态；修改论文与 PDF 后再补 commit、页码、section/table/figure 指针。

## Batch 001 - A1/A2/A3（2026-07-29）

状态：**18-environment 重算与证据 PDF 已实施；ACL 正文措辞待逐 claim 落实**

### Q1. A1 为什么使用单模型、单 seed、单 benchmark 的局限性数据？

**核查结论**

A1 当前数据（DeepSeek-7B × MATH500 × seed 42 × cap 3072）是最早的可逐题审计 pilot，适合固定定义、展示原始 probe 行和复现机制，但不应作为跨模型/跨任务主结论的首要证据。把它放在附录第一项是 provenance 设计，不代表它是最强 generalization evidence；当前 PDF 没有把这一区别讲清楚。

已有更强证据分三层，但协议并不完全相同，不能直接无标记混池：

| 证据层 | 覆盖 | 直接结果 | 限制 |
|---|---|---|---|
| Stage 1/11/12 matched protocol | DeepSeek/Qwen × MATH500，DeepSeek × AMC23/AIME24；共 1,070 trajectories、20,974 probes；seed 42 | window-unanimous false consensus 分别为 6.5%、11.0%、8.0%、22.2%；对应 naive stop drop 为 16.4、6.2、6.5、26.6 pp | 多模型/多 benchmark，但仍单 seed、cap 3072、probe cap 10 |
| Final-eval multi-seed | DeepSeek × MATH500 × seeds 43/44/45；1,500 trajectories、26,289 probes | first-consensus recovery 233，overthinking 32；原始比 7.28:1；w=3/5/8 均有回放 | 多 seed，但单模型/单 benchmark；probe cap 32 |
| Governor v2 bank | 2 models × 3 benchmarks × 3 seeds；2,736 trajectories；dense simple@32 | 已有 17,712-rule sweep 和 direction-of-effect；原始 bank 足以离线复算 A1-A3 型诊断 | cap 16K/32K、interval 64，与 Stage 1 协议不同；当前尚无统一 A1-A3 diagnostic artifact |

**颜色判定**

- A1 中“500 条轨迹、8,739 probes、自然结束率、该设置下的 FC 比例”等描述性数据：**绿色（仅限该设置）**。
- 若用 A1 单独支撑“false consensus 跨模型/seed/benchmark 普遍存在”：**蓝色（证据范围不足）**。
- 论文若省略范围而把 6.5%/16.4 pp 写成一般规律：**红色（量词与证据范围不匹配）**。

**修改队列**

1. 将 A1 政名为“Foundational single-run audit”，明确它是 protocol/provenance anchor，而不是 generalization 主证据。
2. 在 A1 后增加一张 matched-protocol cross-model/cross-benchmark 表。
3. 新增 Governor v2 统一离线 diagnostic：在 18 environments 上复算 w=3/5/8 的 false consensus、first-consensus recovery/overthinking 和 cap-stratified 结果；无需 GPU。
4. 论文的 broad F1 claim 优先指向上述多环境表和 multi-seed mechanism table，A1 只作为可审计案例指针。

**证据文件**

- [Stage 1-5 report](../benchmark/FalseConsensus/report/report.md)
- [Stage 11-12 report](../benchmark/FalseConsensus/report/report_stage11_12.md)
- [Final-eval multi-seed report](../benchmark/FalseConsensus/report/report_final_eval_multiseed_2026-07-26.md)
- [Governor v2 development bank](../benchmark/FalseConsensus/results/governor_v2/)

### Q2. A2 是否有同样的实验局限？为什么只展示 window size 5？

**核查结论**

是。A2 当前 calibration 图仍是 DeepSeek-7B × MATH500 × seed 42，且固定 last-5 window。选择 w=5 的原始理由是：它是早期 Governor 分析的 canonical online window，并允许“至少 3 个非空 probe”后计算 share；但 window size 本身就是规则维度，只展示 w=5 容易让读者误以为失准与 window 无关。

已有 multi-seed w=3/5/8 回放能证明 window choice 显著改变 accuracy-saving trade-off。以下固定 `share=1.0`，数据来自 DeepSeek × MATH500 × seeds 43/44/45：

| Window | Accuracy | Δacc vs Full | Net saving | Stop coverage | False-stop rate | Recovery killed |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 63.60% | -17.07 pp | 50.10% | 92.20% | 36.51% | 285 |
| 5 | 76.47% | -4.20 pp | 25.13% | 77.73% | 20.15% | 87 |
| 8 | 79.60% | -1.07 pp | 4.44% | 59.60% | 12.48% | 31 |

该表是“first-stop behavior”，不是 A2 当前“trajectory-end calibration”图的同一统计量。因此它足以证明 window 是关键敏感维度，但若要声称 calibration misfit 对 window 稳健，仍应从现有 probe banks 复算 w=3/5/8 的 calibration/FC 曲线。

**颜色判定**

- A2 中 w=5、n=36、accuracy 47.2% 等精确数字：**绿色（仅限该设置与该 window）**。
- “window share 普遍未校准”若只引用这一张 w=5 单 seed 图：**蓝色（缺 window/model/seed sensitivity）**。
- “window size 不影响结论”或任何 window-invariant 表述：**红色（现有 w=3/5/8 stop replay 已显示强依赖）**。

**修改队列**

1. A2 图注显式写明 `w=5, min_nonempty=3, seed=42, cap=3072`。
2. 增加上面的 w=3/5/8 multi-seed sensitivity 表或图。
3. 用 Governor v2 dense banks 离线复算 18 environments × w=3/5/8 的 calibration、window-unanimous FC rate 和 stop trade-off；无需 GPU。
4. 论文把“miscalibrated”限定为 tested windows/settings，除非新复算显示跨环境稳定。

**证据文件**

- [Stage 1 analysis implementation](../benchmark/FalseConsensus/analyze.py)
- [Final-eval aggregate](../benchmark/FalseConsensus/results/final_eval/aggregate/model_seed_aggregate.csv)
- [Final-eval evaluator](../benchmark/FalseConsensus/final_eval/evaluate_run.py)

### Q3. A3 的 “first probe wrong” 指什么？它是否能支撑 recovery？

**核查结论**

`first probe wrong` 指字面意义上的**第一次 probe completion 的答案**，即 `answers[0]` / `probe1_answer`，通常位于 128 main tokens；不是第一次形成共识时的 dominant answer。代码随后比较该答案与 final answer。因此“375 个 first-probe wrong 中 76.3% 最终正确”只说明 128-token early readout 很不成熟，不能单独证明 consensus stopping 会截断 recovery。

A3 中另一个统计才是 consensus-recovery 证据：代码查找**第一次出现的 3 个连续、非空、数学等价 probe answers**；若该共识答案与 final answer 不同，就计入 145，最终正确者为 95。需要注意：

- 它是“第一次 3-probe unanimous event”，不是轨迹中“任意一次”共识；
- 它不要求 `is_certain`，因此与 naive early-stop rule 并非完全相同；
- `95/145` 是这些 first-consensus-different trajectories 最终正确的比例。

更强且定义更清晰的证据来自 seeds 43/44/45：首次 last-5 window（至少 3 个有效答案、share ≥0.8）达到共识时，1,335 条 reached trajectories 中有 233 次 wrong-consensus -> correct-final recovery、32 次 correct-consensus -> wrong-final overthinking，原始计数比 7.28:1。

**颜色判定**

- “第一次 probe 错误的 375 题中 76.3% 最终正确”：**绿色（early-readout 描述性事实）**。
- 若把该数字直接当作“consensus recovery”的主要证据：**红色（证据对象误配）**。
- Stage 1 的 145/95 first-consensus result：**绿色（单设置内）**。
- multi-seed 的 233 recovery vs 32 overthinking：**绿色（当前最强的直接 consensus-recovery 证据）**。
- 跨模型、跨 benchmark、跨 seed 的统一 first-consensus recovery rate：**蓝色（Governor v2 bank 尚未形成固定 diagnostic artifact）**。

**修改队列**

1. 将 A3 的 `First probe 错误` 政名为 `Probe-1 error (early-readout control; not consensus)`。
2. 将 `中间三次共识` 改为 `first 3-probe unanimous event`，避免“曾经任意形成”的误解。
3. 把 multi-seed `233 vs 32` 放到 A3 主表，替代 first-probe statistic 作为 recovery 主证据。
4. 论文中凡以 76.3% 支撑 consensus recovery 的位置标红并替换证据指针；76.3% 只保留为“very early answers are immature”的辅助观察。

**证据文件**

- [Stage 1 analysis code](../benchmark/FalseConsensus/analyze.py)
- [Stage 1 report](../benchmark/FalseConsensus/report/report.md)
- [Multi-seed mechanism table](../benchmark/FalseConsensus/results/final_eval/aggregate/mechanism_per_seed.csv)
- [Final-eval multi-seed report](../benchmark/FalseConsensus/report/report_final_eval_multiseed_2026-07-26.md)

## Batch 001 汇总结论

本组三个质询成立。A1-A3 的问题不是原始数字计算错误，而是**证据层级没有按强弱排序、window sensitivity 未展示、以及 first probe 与 first consensus 容易混淆**。当前应保留 pilot 的可审计数字，但将 broad claims 的主证据升级为 multi-seed first-consensus mechanism，并补做已有 Governor v2 banks 的统一 CPU diagnostic。

### 多元重算实施记录（2026-07-29）

已用同一 Governor v2 协议重算 18 个 development environments：2 models × 3 benchmarks × 3 seeds，共 2,736 trajectories、229,693 dense simple@32 probes，interval 64。所有主结论同时报告 problem-pooled 与 environment-macro；后者对 18 个环境等权，避免 MATH500 题量主导。可复现入口为 [analysis script](../benchmark/FalseConsensus/governor_v2/analyze_multivariate_a1_a3.py)，固定结果为 [report](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/report.md) 和 [summary JSON](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/summary.json)。

| 质询 | 多元重算关键结果 | 原结论是否变化 | 更新后的证据判定 |
|---|---|---|---|
| A1 | Natural completion 94.7% pooled / 91.3% macro；final accuracy 88.6% / 78.9%；whole-trajectory unanimous accuracy 97.5% / 98.1%；六个 model × benchmark cells 都观察到 last-5 false consensus（4.0%-48.5%） | broad false-consensus 方向不变；证据范围显著增强。旧 500 题数字不再作为一般性主证据 | **绿色**：限定于 Governor v2 development bank 的跨模型、benchmark、seed 结论 |
| A2 | cumulative CCE 为 0.204 pooled / 0.241 macro；w=3/5/8 macro CCE 为 0.201/0.203/0.200，last-window false consensus 为 16.4%/16.0%/15.3%。strict stop 的 macro Δacc 为 -46.60/-29.99/-17.29 pp，net saving 为 82.3%/66.1%/51.4%；w=3 有 1,478 次错误提交 | miscalibration 方向不变且跨 window 稳定；“window 不重要”被更强地否定。增大 window 改善风险，但 persistence 单独不足 | **绿色**：tested windows 下的 miscalibration 与 sensitivity；不得外推为所有 window |
| A3 | w=5 first-consensus：1,137 recovery vs 39 overthinking（29.15:1）；六个 model × benchmark cells 同向，有限比值至少 24.4:1。first consensus 与 final 不同的 1,411 条中 1,139 条最终正确；Probe-1 wrong 后 86.0% pooled / 78.0% macro 最终正确 | recovery 结论不变且明显增强；Probe-1 仍只能作为 early-readout control。绝对 token 的 late-consensus 下降存在，但相对轨迹位置不单调 | **绿色**：first-consensus recovery；**红色/降格**：把 Probe-1 当 consensus；**蓝色/描述性**：把 late-consensus 当稳健或因果规律 |

**图表更新**

- A2 原单 seed、last-5 图已替换为 18 environments 的 w=3/5/8 pooled/macro calibration 图，并新增 strict-stop window sensitivity 图。
- A3 原绝对 token 单图已替换为双面板：绝对 token 位置与完整轨迹相对位置。后者直接显示“越晚越差”并非归一化后稳健的单调关系。
- A1-A3 在 finding map appendix 中已改为新的 matched-protocol 表和固定 artifact 指针；Stage 1 pilot 仅保留为 provenance，不再承担 broad claim。

## Batch 002 - A4-A15 全 Appendix 证据升级（2026-07-29）

状态：**统一重算、图表与 finding map 已实施；ACL 正文措辞待逐 claim 落实**

### 质询

在 A1-A3 多元重算之后，对所有剩余支撑 claim 重复同一审计：如果 repo 中存在覆盖更多 model × benchmark × seed × split 的固定 artifact，则替换或并列补入 Appendix；如果协议、计费或聚合口径不同，则不得混池；如果更广证据揭示反例或数据质量问题，必须降低 claim 可靠性。

### 统一重算入口

- [Evidence audit script](../benchmark/FalseConsensus/analyze_appendix_evidence.py)
- [Structured summary](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/summary.json)
- [Audit report](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/report.md)
- [Confirmation environment rows](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/confirmation_environment_audit.csv)
- [Related-work benchmark rows](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/related_work_benchmark_macro.csv)
- [Online DEER environment rows](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/deer_online_environment_metrics.csv)

该脚本只读取既有 artifact，不生成模型输出、不重新选择规则、不触碰未聚合 test labels。数学答案比较继续使用项目的 robust grader。

### 分项结论

| Appendix | 更广证据与重算结果 | Claim 是否变化 | 更新后的可靠性 |
|---|---|---|---|
| A4 taxonomy | repo 中仍没有 Task A/Task B 返回的 `annotations_P*.csv`；只有早期单标注员 audit CSV，不能替代双人任务 | 不变；28 例 AI-assisted 初标仍只能 preliminary | **低** |
| A5 sweep | 新增完整 4-model Test：23 env/rule、407,376 rows；Test min/p1/p5/p25/median drop 为 0.111/0.333/0.667/2.000/9.222 pp；17,712/17,712 rules 的 worst-case drop 仍为正 | “方向系统性”增强；`1.85 pp` 仍只是 Dev point estimate，不能当普适 floor | **高（方向）/中（精确 floor）** |
| A6 families | 未发现保留了同格式 Test family-frontier 的 fixed artifact；Dev family 结论不扩张 | 不变；只能否定当前 Dev grid 中的 adaptive-event family | **中高（当前 grid）** |
| A7 direction | named rules 的 ratio 14.59-35.17，再加入独立 strict w=3/5/8 的 33.44/29.15/19.70 | recovery harm 跨规则、window 同向，机制结论增强 | **高** |
| A8 cross-split | 同模型 Dev/Test 仍为 pass 0/272/joint 0、r=0.963；完整 4-model Test 单独 pass 204 | joint gate 为空不变；204 必须标为 test-only，不能称泛化成功 | **高** |
| A9 confirmation scope | 23/23 env、906 trajectories、81,720 dense 与 33,283 adaptive probes 完整；Qwen-32B 仅 1/114 截断，但 Llama-8B 98/108 截断 | 规模外推略增强；架构外推被严重削弱 | **Qwen-32B 中 / Llama 低** |
| A10 related work | 固化 18 个 model-method-benchmark Dev rows（每 cell 三 seeds）和逐 benchmark ranges；加入 matched named Governor macro。Related-work Test rows=0 | CertaIndex 三 benchmark 均严重掉点；TJE/DEER 的模型与 benchmark 异质性更清楚 | **本 harness 比较中高；跨论文外推低** |
| A11 fast/readout | Fast path 新增 Train：Qwen `+0.65/+3.04 pp`、DS `+1.41/+1.90 pp`；Dev 486 readout pairs 中 72 次不一致（14.81%），trial/readout acc 88.68%/88.48%，平均 470.5 tokens | Fast path 的组件方向增强；raw readout 数字从手抄派生升级为固定脚本 | **中高（Train/Dev 配对）** |
| A12 online 3-seed | 36/36 run directories、1,368/1,368 method-problem rows；protocol version/config hash 在 36 runs 中唯一一致 | 数值不变；“seed 43/44 缺统一 audit”缺口消除 | **中高（Dev bank）** |
| A13 aggregation/branch | Environment-macro saving advantage +12.11 pp，但 problem-pooled -1.48 pp；117 first branches 的净纠错为 0；117/117 verification 为 64-token length stop；direct Stage-1 saving +0.764 pp、accuracy 不变 | 聚合依赖不变；verification 正面 claim 被更高可靠度反证 | **高可靠反证** |
| A14 protocol | 将 36-run online audit 与完整四模型 coverage 接入协议指针；计费与 confidence 定义不变 | 不变 | **高（定义事实）** |
| A15 gaps | 删除“online 后两 seed 缺统一 audit”和“branch 缺固定脚本”；新增 Llama 90.7% cap 截断、related-work Test=0 | 缺口更精确；优先级改为 held-out boundary test 与 Llama cap 修复 | **不适用（gap ledger）** |

### 关键判定

1. **F2 的核心 negative direction 更稳健，但 architecture claim 反而要收窄。** 不能用 4-model 汇总掩盖 Llama-8B 的 90.7% right-censoring。
2. **F4 的 broad ranking 不应只报模型宏平均。** Appendix 必须同时给逐 benchmark range；DEER 在 Qwen 上近中性，但 DeepSeek 的 MATH cell 可掉 10.33 pp。
3. **F5 的数据完整性已明显改善，方法归因却没有改变。** Fast path 有 Train/Dev 配对正证据；verification branch 有 3-seed fixed raw audit 的反证，不能作为贡献。
4. **没有新数据就不升级。** A4 人工 taxonomy、related-work Test、boundary-controller Test、probe-cost factorial 和 `C_cali` 仍保持缺口，不以邻近实验代替。

### 图表更新

- A5 改为 Dev 与完整 4-model Test 的 17,712-rule percentile 对照。
- A7 加入 w=3/5/8 strict replay，显示方向不依赖单个 named rule。
- A8 改为 joint-gate 与 Dev/Test percentile 双面板，并显式区分 test-only 204。
- A10 新增 related-work 与 matched named Governor 的模型宏散点。
- A11 左图扩展为 Train/Dev fast-path；A12 三-seed online 面板保留。

## Batch 003 - A4-A6 质询（2026-07-29）

### 质询

1. A4 尚未得到人工标注结果，不应把 AI-assisted pilot 表写成正式 taxonomy 结果。
2. A5 第一张表混合了协议门槛、规则级分布、cell 级方向统计和单规则案例；“分位数”
   没有说明随机变量与样本单位。
3. A6 没有解释四个 family 的算法含义，也没有说明 Pareto sweep 的目标、过滤门槛、
   排序方式及最终是否真的选出策略。

### 核查结论

#### A4

质询成立。repo 中没有 Task A/Task B 返回的 `annotations_P*.csv`，所以目前只有
134 例待标数据和标注工具，没有可报告的人工 taxonomy 结果。28 例 AI-assisted
初标只用于设计类别，不能支撑比例。F1.6-F1.7 从“低可靠 preliminary evidence”
改为**未验证**；A4 改成状态页，等待双人标注、agreement 和仲裁。

#### A5

质询成立。原表中的 `min/p1/p5/p25/median` 具体是以下分布的分位数：

\[
\{D_{\mathrm{model}}(r):r\in 17{,}712\ \text{rules}\},
\]

其中 \(D_{\mathrm{model}}(r)\) 对每个 `(split, model)` 先宏平均 benchmark × seed
accuracy drop，再在 train/dev 的所有 `(split, model)` 中取最大值。它不是 problem、
environment cell、probe 或 saving 的分位数。

已将 A5 拆成：

1. 三个规则级选择量 \(D_{\mathrm{model}},D_{\mathrm{bench}},\mathrm{PSF}\) 的定义；
2. conservative gate 及 0/17,712 的结果；
3. 17,712 个规则级 worst-case drop 的 Development/Test 分位数表；
4. cell 方向统计和 least-bad rule 作为独立文字补充。

同时纠正“on Dev”的含混说法：development selector 的风险约束实际联合使用 train+dev，
而 `dev_q20_saving_fraction` 才只使用 18 个 Dev environments。四模型 Test 分位数只作
confirmation diagnostic，不进入 selection。

#### A6

质询成立。四个 family 已补充定义：

- `latest_persistence`：最新答案连续保持相同；
- `window_share`：近期窗口 dominant share 达阈值；
- `entropy_budget_fraction`：达到预算成熟度且答案 entropy 足够低；
- `adaptive_event_probe`：由结论词、entropy drop、反思转折或答案候选等事件触发 probe，
  再使用 latest/window/entropy evidence。

Pareto 的三个目标也已明确：最大化 18 个 Dev environments 的 total-token saving
第 20 百分位 \(S_{20}\)，同时最小化 train+dev worst-case per-model 和 per-benchmark
accuracy drop。17,712 条规则形成 93 个非支配点；预注册流程本应在三组 operating-point
gate 内各选一个互异点，但 conservative gate 无合格规则，因此没有正式冻结三个策略。
A6 的四行只能称 family diagnostic points，不能称 Pareto-selected strategies。

另记录一个应在论文中透明说明的实现事实：选择器不是“train 单独筛选、Dev 独立选择”；
它使用 train+dev 共同构造两个风险轴和 PSF，再用 Dev \(S_{20}\) 排序。Test 未进入选择，
但正文不得描述成严格的顺序 train-to-dev selection。

### 本轮证据判定

| Appendix | 判定 | 可靠性/状态 |
|---|---|---|
| A4 | 尚无结果，删除正式比例语气 | **未验证** |
| A5 | negative direction 成立；精确分位数口径已澄清 | **高（当前搜索空间）** |
| A6 | family 与 Pareto 算法事实可审计；adaptive 结论限于当前 grid | **高（实现事实）/中高（经验结论）** |

## Batch 004 - A7-A9 质询（2026-07-29）

### 质询

1. A7 的 `FC/SW`、`FW/SC` 缩写不可读；不同来源的 rule/diagnostic 混在同一张无分组
   表里，且没有解释每个 rule 的停止条件。
2. A8 应展示全部策略点，并画出 Pareto frontier，而不是只给 gate 柱图和分位数线。
3. A9 需要解释 32B/Llama 覆盖为何不完整，以及 Llama 为何出现 90.7% cap。

### 核查结论

#### A7

质询成立，并额外发现一处定义误标。旧表应改为完整词义：

- Harm：完整生成正确、反事实早停错误；
- Rescue：完整生成错误、反事实早停正确；
- harm/rescue ratio：两类配对题目的原始计数比。

四个 named rules 的配置已从 `final_eval/protocol.json` 逐项还原：naive 是无成熟度、
3 连续非空一致；conservative 是 1,024-token floor、8 连续 schema-valid/certain；
balanced-general 是 1,536-token floor、5 连续 task-aware-valid/certain；
balanced-math 是 768/2,048 level-aware floor、5 连续 schema-valid/certain。
Qwen/DeepSeek 两行只是 naive 的模型拆分，不是额外规则。

更重要的是，旧表把 `33.44/29.15/19.70` 写成了 `strict w=3/5/8`，但源代码实际是
`first_consensus(window=w, threshold=.8)`：最近窗口至少 3 个有效答案、dominant share
≥0.8，而且可以在窗口未填满时触发。真正要求连续 \(w\) 个非空答案全一致的 strict
replay 为：

| w | Stopped | Harm | Rescue | Ratio |
|---:|---:|---:|---:|---:|
| 3 | 2,707 | 1,204 | 36 | 33.44 |
| 5 | 2,620 | 730 | 42 | 17.38 |
| 8 | 2,456 | 415 | 44 | 9.43 |

A7 已拆成 rule-definition、named-rule outcome 和两类 consensus diagnostic 三块，
并重画双面板图，避免继续混称。

#### A8

质询成立。原图只展示 gate pass 数和 drop 分位数，看不到 17,712 条规则的
accuracy-saving geometry。新增纯 CPU 离线 replay/aggregation：

- Dev 与 Test 都只用相同的两个 development models；
- 横轴为 worst per-model accuracy drop；
- 纵轴为 18 个对应 environments 的 total-token saving 第 20 百分位；
- 每个点是一条规则，黑线为二维非支配 frontier；
- 1.5 pp 与零净节省分别画参考线。

重建脚本为
`benchmark/FalseConsensus/governor_v2/analysis/build_a8_strategy_points.py`，固定逐规则
坐标写入 `results/appendix_evidence_upgrade/a8_strategy_points.csv`。该图是二维展示；
完整 gate 仍另含 per-benchmark drop 与 PSF，不能从二维线直接推导 gate pass。
同两模型重算得到 Dev/Test drop Pearson `r=0.962`、Dev pass 0、Test-only pass 272、
joint pass 0；二维 Dev/Test frontier 分别含 57/68 个点。272 条 Test passers 回看
Dev 的 drop 为 4.98-5.65 pp（median 5.09）。Dev 最低 drop 点为
`Dev 1.85 -> Test 0.11 pp`；Test 最低点为 `Test -0.33 -> Dev 4.87 pp`。

#### A9

32B **并不缺题**。协议从一开始就把 held-out scale 设为 seed 45 单 seed：
三 benchmark 的 114/114 trajectories、dense/adaptive probes 均完整，只有 1 条
length-stop（0.9%）。其限制是统计覆盖只有单 seed，而不是工程采集失败。

Llama 则是无效运行，而不只是“模型较弱、cap 偏小”：

- 原计划三 benchmark × seed 45，实际缺 AIME24，仅保留 MATH500/AMC23 的 108 条；
- 98/108 为 `finish_reason=length`，但输出从开头已经是重复标点、括号、`and` 等乱码；
- 95/108 没有可抽取 final answer，最终仅 1/108 正确；
- 采集提交称 AIME 的 32K generation non-terminating，因而省略。

现有 artifact 没有保留足够的 server log、checkpoint hash 或 tokenizer smoke，无法在
checkpoint、tokenizer/chat template、vLLM serving/解码之间唯一归因。但可以确定：
提高 cap 不会修复从首 token 就开始的退化生成。必须先验证权重-tokenizer-template
链路并通过固定题 smoke，再 pilot cap 和补齐三 benchmark。

这个发现会向前影响 A5/A8/F2.6/F2.11：混入 Llama 的四模型 Test frontier 与
`204 test-only passers` 不再作为证据；cross-split 主证据收缩到有效且匹配的两个模型，
Qwen-32B 单独作为 scale diagnostic，architecture 泛化标为**未验证**。

### 本轮证据判定

| Appendix | 判定 | 可靠性/状态 |
|---|---|---|
| A7 | 方向结论成立；旧 strict 标签错误，已拆分并复算 | **高（修正定义后）** |
| A8 | 同两模型逐规则点阵与 frontier 可重建；不混无效 Llama | **高（matched cross-split）** |
| A9-Qwen32B | 预注册单-seed范围完整 | **中（scale evidence）** |
| A9-Llama | 生成链路失效、缺 AIME；不可用于结果 | **无效/未验证** |

## Batch 005 - A10-A12 质询（2026-07-29）

### 质询

1. A10 的 CertaIndex、DEER、TJE 是否都使用 faithful probes；是否保留了完整原始数据。
2. A11 无异议。
3. A12 把逐 seed 与多 seed macro 混在同一个 `Seed` 列，标签换行过多，应展平。

### 核查结论

#### A10

三项 baseline 均实际运行了独立的 method-specific GPU probing，并非复用
Governor `simple@32` 输出。覆盖均为 2,736 条逐题记录、18 个 method-environments，
总计 8,208 method-problem rows；原始逐题 JSON、54 个 collection manifests、
54 个 replay artifacts 和聚合表均存在。辅助调用总数为：

| Method | Raw problem rows | Method-specific auxiliary calls |
|---|---:|---:|
| CertaIndex mid | 2,736 | 27,193 |
| DEER | 2,736 | 14,017 |
| TJE | 2,736 | 38,672 |

但 “method-specific GPU probe” 与 “fully faithful end-to-end reproduction” 必须区分：

- **CertaIndex mid**：原作 probe suffix、interval=64、cap=20、patience=3、
  uncertainty filter 与数学等价 stop rule 均一致；只把 live chunk 调度换成相同 token
  位置的 frozen prefix。可称 **probe-level faithful / frozen-timing reproduction**。
- **DEER**：按上游 `c9dd19f` 复现 `Wait` trigger、10 次上限、20-token trial、
  0.95 threshold、DeepSeek avg1 / Qwen avg2、Qwen `</think>` gate 与 formal readout。
  Probe/readout 逻辑忠实，但 main trajectory 预先冻结，所以不是完整 online controller。
- **TJE**：使用论文 Figure 2 的 system instruction、十级标签、`Wait + </think>`
  trigger 与 `Almost certain` threshold；但主轨迹没有在 TJE system prompt 及低置信
  `Wait` 续写下重新生成，而且 confidence label 使用 constrained choice。它只能叫
  **frozen adaptation**，三者中保真度最低。

因此 A10 的数值可以作为同轨迹真实 re-probing 比较，但不得把三个点统一描述为
原论文端到端 faithful reproduction。A10 已加入逐方法 fidelity 与原始覆盖表。

#### A11

本轮无异议，不修改证据判定。

#### A12

原始数值不变。A12 已拆成：

1. 仅含 seed 42/43/44 的逐 seed 表；
2. 仅含 Inspired / Online DEER 的三-seed macro summary 表。

这样 macro 不再伪装成 `Seed` 值，也消除了窄列中的多行标签。

### 本轮证据判定

| Appendix | 判定 | 可靠性/状态 |
|---|---|---|
| A10-CertaIndex | method-specific probing 完整；probe 规则忠实、timing 冻结 | **高（probe-level）** |
| A10-DEER | official trial/confidence/readout replay 完整；main path 冻结 | **中高（probe-level）** |
| A10-TJE | 原文 prompt/trigger 有据，但轨迹与 constrained decoding 均有 adaptation | **中（frozen adaptation）** |
| A11 | 无异议 | **保持原判定** |
| A12 | 仅展平展示，数据与结论不变 | **中高（Dev bank）** |

## Batch 006 - 第 5 轮质询与全文 claim 着色（2026-07-29）

### 质询结论

本轮对 A13-A15 及整体 Appendix 没有提出新的数据异常。此前五轮对 A1-A12 的定义、
范围、聚合、baseline fidelity、Llama 有效性和 verification 消融修订均保留。

### 当前论文 claim-level 标注

以当前 `paper/acl_latex.pdf` 的 14 页稿件为底稿，复用完整 claim inventory，
对 130 项实质 claim 逐一加入 PDF 高亮、popup comment 和分层 outline。原 PDF
保持不变，审阅输出为：

`output/pdf/acl_latex_claim_evidence_colored.pdf`

颜色定义：

| 颜色 | 数量 | 判定 |
|---|---:|---|
| Green | 72 | 在句子当前限定的模型、benchmark、split、计费和聚合范围内有直接支撑；comment 指向 A1-A15 |
| Blue | 25 | 尚缺实验、人工审计、公开 provenance 或必要消融；comment 写明所需工作 |
| Red | 33 | 现有证据直接反驳、定义/数字错误、错误归因，或量词明显超过已测范围 |

主要红色簇包括：无效 Llama run 被用于架构泛化、把 `simple@32` 误写成 32 samples、
Governor certainty 误写成 token probability、三项 baseline 误称共享同一 probe bank、
DEER “两模型均约 1 pp”、verification branch 的保护性归因、aggregation-independent
dominance，以及把 searched-space negative result 外推成任意 probing/consensus
scheme 的不可能性。

主要蓝色簇包括：taxonomy 与 grader 人工审计、TBD 主表/gross-net 表、
probe-density/KV-reuse 恢复量、boundary-confidence held-out test、signal-only
因果消融、公开匿名 artifact/provenance 和 “among the first” novelty 核查。

生成与验证脚本为 `paper/color_claims_by_evidence.py`。脚本强制检查 130 项全部匹配，
每项恰有一个 colored highlight 和一个 closed popup note；输出共 15 页（1 页图例 +
原稿 14 页），目录按 section 展开并在 claim 标题前显示 GREEN/BLUE/RED。
