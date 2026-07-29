更新日期：2026-07-29

用途：把论文中的每个 finding/claim 拆成可核验陈述，记录直接实验、证据边界、可靠性和下一步。本文是研究台账，不替代论文正文。

引用约定：每个原子 claim 都在对应章节顶部映射到一个或多个附录证据项 `A1-A15`。点击 PDF 中的附录编号可跳转到具体数据表、图、聚合口径和源 artifact；`A15` 专门记录尚未完成、仅探索性或被现有消融削弱的证据。

# 1. 可靠性标准

| 等级 | 判定标准 | 论文中允许的表达 |
|---|---|---|
| **高** | 有直接实验；数据完整且通过审计；claim 的模型、benchmark、split 和计费口径与实验一致；通常还具有多 seed、held-out 或确定性复算支撑 | `we find/show`，但仍须写明适用范围 |
| **中** | 有直接证据，但只覆盖少量模型/seed/domain，或依赖 frozen adaptation、小样本宏平均、未完成人工审计等 | `we observe/provide evidence`；必须紧跟限制 |
| **低** | 仅探索性、单子集、间接比较、缺少关键消融/held-out，或现有消融与 claim 冲突 | 不作为主结论；改写为 hypothesis/limitation/future work |

可靠性评估的是“当前数据能否支撑这句话”，不是 finding 是否有研究价值。精确、窄范围的 claim 可以是高可靠；更宏大的外推即使方向合理，也可能只有中或低可靠。

# 2. 五项主 finding 总览

| Finding | 当前可守住的核心结论 | 总体可靠性 | 最薄弱环节 |
|---|---|---:|---|
| F1 False consensus | 在两模型 × 三 benchmark × 三 seeds 的已测数学推理轨迹中，局部 probe 共识并不等于终止；继续推理经常纠正共识时的错误答案 | **高（范围内）** | taxonomy 尚未完成人工复核；仍只有竞赛数学与 simple@32 |
| F2 Searched-space negative result | 在预注册的 17,712 个 consensus 规则及既定 dense-probe 计费下，dev 上没有规则通过 conservative gate；同两模型 dev-test frontier 高度相关且 joint gate 为空 | **高** | 不能外推成“任何 consensus 规则都不可能”；Llama-8B confirmation 发生退化乱码生成，不能用于架构外推 |
| F3 Accuracy tax / probe tax | 停在中间答案会损失后续纠错机会；probe 输出成本是另一个可分离、可工程化降低的成本 | **高/中** | “更稀疏 probe 可恢复多少净节省”尚无直接 interval/cost 消融 |
| F4 Related-work contrast | 同一 frozen harness 中 CertaIndex 严重掉点；DEER 的 boundary-confidence signal 明显优于 consensus frontier，但有模型依赖 | **中** | DEER/TJE 是 frozen adaptations；跨方法比较不能单独证明 signal 的因果作用 |
| F5 Boundary confidence | Fast path 有 train/dev 配对正面证据；完整 online controller 的 36 个 run directories、1,368 rows 已统一审计，dev 三 seed 宏平均接近中性且有较高 saving | **中（探索性）** | verification branch 当前没有带来净纠错，且没有 test / 新模型验证 |

**总览证据索引**：F1 -> [A1](#app-a1)、[A2](#app-a2)、[A3](#app-a3)、[A4](#app-a4)；F2 -> [A5](#app-a5)、[A6](#app-a6)、[A8](#app-a8)、[A9](#app-a9)；F3 -> [A7](#app-a7)、[A14](#app-a14)；F4 -> [A10](#app-a10)；F5 -> [A11](#app-a11)、[A12](#app-a12)、[A13](#app-a13)。

# 3. F1：False consensus

**逐 claim 附录索引**：F1.1 -> [A1](#app-a1), [A2](#app-a2)；F1.2 -> [A1](#app-a1), [A3](#app-a3)；F1.3 -> [A3](#app-a3), [A7](#app-a7)；F1.4 -> [A3](#app-a3)；F1.5 -> [A2](#app-a2)；F1.6 -> [A4](#app-a4), [A15](#app-a15)；F1.7 -> [A4](#app-a4), [A15](#app-a15)；F1.8 -> [A5](#app-a5), [A7](#app-a7)。

| ID | 原子 claim | 直接实验与主要结果 | 可靠性 | 安全措辞与缺口 |
|---|---|---|---:|---|
| F1.1 | Whole-trajectory consensus 与 online 可见的 recent-window consensus 不同 | Governor v2 的 18 environments：全轨迹一致 coverage 11.5% pooled / 4.7% macro，正确率 97.5% / 98.1%；last-5 unanimous coverage 78.7% / 84.4%，false consensus 9.7% / 16.0%。见 [A1](#app-a1)-[A2](#app-a2) | **高（tested bank）** | 可跨本次两模型、三 benchmark、三 seeds 报告；不外推到未测模型或 probe prompt |
| F1.2 | Naive consensus early stop 会显著损害准确率 | 18-environment strict replay：w=3/5/8 macro accuracy drop 为 -46.60/-29.99/-17.29 pp；w=3 有 1,478 次错误提交，计 probe output 后仍节省 82.3% | **高（配对反事实）** | 明确这是 simplified strict heuristic，不是 Governor/CertaIndex 完整规则 |
| F1.3 | Continued reasoning 经常恢复正确答案 | w=5 first consensus：1,137 recovery vs 39 overthinking（29.15:1）；六个 model × benchmark cells 均同向。1,411 个 first-consensus 与 final 不同样本中 1,139 个最终正确 | **高** | Recovery 是跨当前环境的主要机制；Probe-1 的 86.0%/78.0% 仅作 early-readout control |
| F1.4 | Consensus 出现得更晚不代表更可靠 | 绝对位置从 `<512` 的 90.5% 降至 `≥8K` 的 39.1%；但按完整轨迹相对位置分箱为 85.6%、93.7%、95.1%、91.7%、84.4%，不单调 | **低-中（描述性）** | 只能说 absolute-token correlation 受难度/长度混杂；不得写成稳健或因果规律 |
| F1.5 | Window share 不是校准良好的 correctness confidence | 18-environment w=3/5/8 macro CCE 为 0.201/0.203/0.200；unanimous false consensus 为 16.4%/16.0%/15.3% | **高（tested windows）** | 可说本次 windows/settings 下 miscalibrated；不得声称覆盖所有 agreement 定义 |
| F1.6 | False-consensus errors 可分成稳定数值错误、推导缺口、格式伪影等类型 | 134 例已导出到 Task A，但双人标注尚未回收；现有 28 例 AI-assisted 初标不作为正式实验结果 | **未验证** | 正文 taxonomy 数字必须保持 pending；人工一致性与冲突仲裁完成后才可报告 |
| F1.7 | Probe 本身会制造部分 false consensus（例如字母答案格式伪影） | 仅有 AI-assisted pilot 观察，尚无人工确认比例 | **未验证** | 当前不得报告比例；至多作为待检验假设 |
| F1.8 | False consensus 不只存在于 Stage 1 的 3072-token 截断设置 | Governor v2 16K/32K caps 的六个 model × benchmark cells 均观察到 last-5 false consensus（4.0%-48.5%），三 seeds/cell；并有 17,712-rule 回放的同向证据 | **高（tested bank）** | 已是直接跨设置复现；仍限定于两模型、三 benchmark 与 simple@32 probes |

# 4. F2：预注册搜索与 “no safe-and-saving rule”

**逐 claim 附录索引**：F2.1 -> [A14](#app-a14)；F2.2 -> [A5](#app-a5), [A14](#app-a14)；F2.3 -> [A5](#app-a5)；F2.4 -> [A5](#app-a5)；F2.5 -> [A5](#app-a5), [A8](#app-a8)；F2.6 -> [A5](#app-a5)；F2.7 -> [A5](#app-a5), [A6](#app-a6), [A14](#app-a14)；F2.8 -> [A6](#app-a6)；F2.9 -> [A8](#app-a8)；F2.10 -> [A8](#app-a8)；F2.11 -> [A9](#app-a9)；F2.12 -> [A15](#app-a15)。

| ID | 原子 claim | 直接实验与主要结果 | 可靠性 | 安全措辞与缺口 |
|---|---|---|---:|---|
| F2.1 | 评估协议将 stopping rule 与 main reasoning trajectory 解耦 | 每题先生成并冻结一条 main trajectory，再对固定 prefixes 离线 probing；规则只改变 stop/readout，不改变 main trajectory。配置、manifest、probe banks 和 sweep archives 均保留 | **高** | 这是协议事实；应称 `probe-independent frozen-trajectory evaluation`，不是 online deployment |
| F2.2 | 搜索覆盖统一的 7 个规则维度和 4 个 family | 17,712 个规则覆盖 schedule、maturity、evidence、persistence、certainty、validity、history，规则哈希与归档可复算 | **高（枚举事实）** | “覆盖该 schema”可靠；“覆盖所有合理 consensus 方法”不成立 |
| F2.3 | 搜索规模为 637,632 个 rule-environment-split rows | `17,712 × 18 × 2 = 637,632`，分析文件复算一致，见 [direction_of_effect.txt](../benchmark/FalseConsensus/governor_v2/analysis/direction_of_effect.txt) | **高** | 纯覆盖/完整性 claim |
| F2.4 | Dev 上 conservative gate 为空 | 两模型 × 三 benchmark × seeds 42/43/44；没有规则同时满足 per-model drop ≤1.5 pp、per-benchmark drop ≤2.0 pp、PSF ≥0.8 | **高** | 论文最强 negative claim；必须限定 `in the preregistered searched space, on dev` |
| F2.5 | Dev 上最安全规则的 worst-case per-model drop 为 1.85 pp | 最小值 1.852 pp；但 bootstrap 95% CI 约 `[0, 5.56]`，同一规则 test 为 0.11 pp | **中** | 可作为 dev point estimate；不能把 `1.85 pp` 写成稳定、普适下界 |
| F2.6 | 所有 17,712 个规则在 Development selection 上的 worst-case per-model drop 都为正 | train+dev selection 为 17,712/17,712；development cells 中 67.72% 掉点、6.75% 提升、25.53% 不变 | **高（Development 搜索空间）** | 不能再用混入无效 Llama run 的四模型 Test 统计扩张该全称；held-out 支撑改由 A8 同两模型 cross-split 提供 |
| F2.7 | 正净节省至少要付出 4.87 pp 的 per-model drop | 在 dense simple@32、interval 64 等既定 probe 计费下，获得至少三个 positive-saving rules 的最低 worst-case drop 为 4.87 pp，且对 PSF 0.5-0.8 稳定 | **中** | 必须和 dense-probe accounting 绑定；不是 probe 成本下降后的普适 frontier |
| F2.8 | Adaptive event probing 在当前规则池中被 simple window share 支配 | Dev family frontier：adaptive 最佳 positive-saving 点 worst-case drop 9.70 pp、mean saving 14.2%；window share 对应 4.87 pp | **中高（当前 grid）** | 可说 `did not help in our sweep`；不能否定其他 adaptive trigger/controller |
| F2.9 | Dev frontier 在同模型 held-out test 上稳定 | 17,712 个规则的同两模型 dev/test worst-case drop Pearson `r=0.962`；dev gate pass 0、test-alone pass 272、both 0；见 [A8 strategy points](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/a8_strategy_points.csv) | **高** | 这是比 exact floor 更可靠的确认结论 |
| F2.10 | Test 上直接选出的“赢家”不能泛化回 dev | 272 个 test-alone gate passers 在 dev 的 per-model drop 为 4.98-5.65 pp，0 个同时通过 | **高** | 直接支撑 held-out selection 的必要性 |
| F2.11 | Negative frontier 跨规模/架构延伸 | Qwen-32B：114 trajectories、3 benches、seed 45、仅 0.9% 截断，可作单-seed scale evidence。Llama-8B 输出大面积退化乱码，运行无效 | **规模：中；架构：未验证** | 不得用现有 Llama 数据支撑架构泛化；四模型合并 frontier 也不作为主证据 |
| F2.12 | “任何 consensus-based early exit 都不可能安全且省 token” | 当前没有直接实验能覆盖无限规则空间、其他 probe prompt 或其他 domain | **低/不支持** | 必须改为 `no rule in the searched space`; 这是论文措辞的硬边界 |

完整性补充：seen-model confirmation 已审计 18/18 environments、684 trajectories、无缺行/运行错误，截断率 3.2%。Held-out scale 的 Qwen-32B 完成预注册单-seed范围；Llama 原计划 3 个 environments，实际只有 2 个，且输出退化，因此不得并入有效 confirmation，见 [A9](#app-a9)。

# 5. F3：Accuracy tax 与 probe tax

**逐 claim 附录索引**：F3.1 -> [A14](#app-a14)；F3.2 -> [A14](#app-a14)；F3.3 -> [A7](#app-a7)；F3.4 -> [A5](#app-a5), [A7](#app-a7)；F3.5 -> [A14](#app-a14), [A15](#app-a15)；F3.6 -> [A14](#app-a14), [A15](#app-a15)。

| ID | 原子 claim | 直接实验与主要结果 | 可靠性 | 安全措辞与缺口 |
|---|---|---|---:|---|
| F3.1 | 总 output-token 成本可分成 main stopping cost 与 consumed probe cost | 定义为 `T=s+p`；gross saving `(B-s)/B`，net saving `(B-s-p)/B`；所有相关报告按字段可复算 | **高** | 这是计费定义；当前不包含 prompt/prefill、wall time、KV-cache memory |
| F3.2 | Accuracy drop 来自 stop position，而不是 probe output token 数量 | 在 frozen trajectory 中，给定 stop position 和 committed answer，改变 `p` 不改变 correctness；这是协议内的确定性性质 | **高（frozen 协议内）** | 可称 stop-position accuracy tax；online probing 若改变主生成则需另测 |
| F3.3 | Consensus stopping 破坏 recovery 远多于挽救错误 full answer | Named rules ratio 为 14.59-35.17；first-local-consensus w=3/5/8 为 33.44/29.15/19.70；真正 strict-unanimous stop 为 33.44/17.38/9.43 | **高（多规则、多 window）** | 两种 consensus 定义均同向但数值不同；ratio 是方向强度，不是 causal risk ratio |
| F3.4 | Dense probing 可把 gross saving 变成负 net saving | 最安全 entropy family 停得晚，仍支付大量 probes；dev 最安全点 net saving 约 `-8%` 至 `-9%` | **高（当前计费）** | 可解释当前负 savings；不可据此说 stop 本身增加 main tokens |
| F3.5 | Probe tax 随 probe 密度降低，并可通过 sparse probe / shorter probe / KV reuse 缓解 | 从计费公式上必然随 consumed probe tokens 下降；但尚无完整 interval×probe-length×KV-reuse 实验量化最终 Pareto | **中** | “reducible by construction”可说；“可恢复正净节省”目前只是待验证 hypothesis |
| F3.6 | Accuracy tax 对任何 probing scheme 都不可消除 | 当前依据是 dense grid 使多数 stop positions 可达，且更稀疏 schedule 只会取其子集 | **中** | 宜写 `within frozen trajectories and reachable positions in our grid`；online controller 可改变轨迹，不能直接外推 |

# 6. F4：Related-work baselines 与 signal 对比

共同证据为 [related-work aggregate report](../benchmark/FalseConsensus/results/related_work/aggregate/report.md)：两模型、三 benchmark、seeds 42/43/44 的 train+dev/frozen-trajectory reproduction；主表为 dev benchmark-macro。

**逐 claim 附录索引**：F4.1 -> [A10](#app-a10)；F4.2 -> [A10](#app-a10), [A14](#app-a14)；F4.3 -> [A10](#app-a10)；F4.4 -> [A10](#app-a10), [A15](#app-a15)；F4.5 -> [A10](#app-a10), [A14](#app-a14)；F4.6 -> [A14](#app-a14), [A15](#app-a15)。

| ID | 原子 claim | 直接实验与主要结果 | 可靠性 | 安全措辞与缺口 |
|---|---|---|---:|---|
| F4.1 | CertaIndex 在本项目轨迹上以巨大准确率代价换取高 saving | Qwen：Δacc `-70.11 pp`、saving `90.10%`；DeepSeek：`-55.89 pp`、`76.68%`。逐 benchmark Δacc 范围分别为 `[-83.33,-43.67]` 和 `[-75.00,-42.67] pp` | **高（本 harness）** | 三 benchmark、三 seeds 均同向；仍是 frozen timeline，不代表原论文端到端数字 |
| F4.2 | TJE 表现高度依赖模型和 benchmark | Qwen 宏平均 `-0.44 pp / 2.03%`，逐 benchmark saving `-1.84%` 至 `4.30%`；DeepSeek `-19.09 pp / 65.00%`，逐 benchmark Δacc `-27.78` 至 `-8.67 pp` | **中高（异质性事实）** | TJE 使用 frozen adaptation，structured choice 改变标签分布；不宜写“忠实复现原方法整体性能” |
| F4.3 | DEER 比已测 consensus baselines 更接近 full accuracy | Qwen：`+0.78 pp / 16.29%`；DeepSeek：`-4.83 pp / 20.16%`。matched Governor named rules 的模型宏掉点为 9.94-56.48 pp | **中高（matched比较）** | 可说 boundary confidence 在本 harness 中更有希望；不是 signal-only 因果消融，且 DeepSeek DEER 并非近中性 |
| F4.4 | “问题是 consensus signal，而不是 early exit” | CertaIndex/17,712 consensus rules 与 DEER 在同数据、计费框架下形成明显对照 | **中** | 很有说服力但不是纯因果消融：方法还在 trigger、trial generation、readout 等处不同 |
| F4.5 | Related-work points 与 Governor candidates 的 Pareto 相对位置可靠 | 同一 frozen trajectories 和 answer grader；图中 fair-saving 口径需与正文 net/gross 定义保持一致 | **中** | 每张图必须显式写明计费口径；不能混用 “all-generated/fair” 与 “net dense-probe” |
| F4.6 | Baseline 数字可视为原论文报告水平 | 本实验没有复现所有原始部署细节，也没有在原论文全套 benchmark/settings 上运行 | **低/不支持** | 只能称 `reproduction/adaptation on our harness` |

# 7. F5：Boundary confidence、fast path 与 verification branch

Online 证据分两层：seed 42 有正式的 [aggregate report](../benchmark/FalseConsensus/results/deer_inspired/online_dev/aggregate/report.md) 和 [audit](../benchmark/FalseConsensus/results/deer_inspired/online_dev/aggregate/audit.json)；统一 [Appendix evidence audit](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/report.md) 又逐目录检查了 seed 42/43/44 的 36 个 method × model × benchmark runs、1,368 method-problem rows。36/36 manifests 完整、protocol version 与 config hash 唯一且一致、无缺题。后两 seed 的采集目录仍保留 `nonformal` provenance 标签，但“缺统一审计”已不再是证据缺口。

**逐 claim 附录索引**：F5.1 -> [A11](#app-a11)；F5.2 -> [A11](#app-a11)；F5.3 -> [A12](#app-a12)；F5.4 -> [A12](#app-a12), [A13](#app-a13)；F5.5 -> [A13](#app-a13)；F5.6 -> [A13](#app-a13)；F5.7 -> [A13](#app-a13)；F5.8 -> [A15](#app-a15)；F5.9 -> [A10](#app-a10), [A11](#app-a11), [A12](#app-a12)；F5.10 -> [A15](#app-a15)；F5.11 -> [A14](#app-a14), [A15](#app-a15)。

| ID | 原子 claim | 直接实验与主要结果 | 可靠性 | 安全措辞与缺口 |
|---|---|---|---:|---|
| F5.1 | DEER 的高置信 trial answer 后再生成 formal readout 可能冗余 | 固定脚本重算 486 个 Dev readout pairs：trial/readout 72 次不一致（14.81%）；accuracy 88.68%/88.48%；readout 平均 470.5 output tokens | **中高（Dev配对）** | 原始 artifact 与 grader 可复算；仍无 test，且该比较不等于部署式 latency 消融 |
| F5.2 | `confidence > 0.995` 时直接交付 valid trial answer 的 fast path 有独立价值 | Dev：Qwen `-0.33/+2.39 pp`，DeepSeek `+1.44/+2.01 pp`；Train 也为 Qwen `+0.65/+3.04 pp`、DeepSeek `+1.41/+1.90 pp`。Dev 335/684 fast commits | **中高（train/dev配对）** | 组件级方向在两个 split、两个模型上多数同向；尚无 test，Dev Qwen 有轻微 accuracy trade-off |
| F5.3 | 完整 DEER-inspired online controller 在 dev 三 seed 上接近中性宏准确率并显著省 token | 36/36 run directories 与 1,368 rows 统一审计通过；environment-macro Δacc `-0.75 pp`、fair saving `34.2%`；seed 范围 `[-6.1,+4.2] pp`、`[25%,44%]` | **中高（Dev bank）** | 数据完整性已强化；结果仍 seed-sensitive、无 test，且 online full baseline 并非严格同轨迹反事实 |
| F5.4 | 完整 controller 比 online DEER 同时更准、更省 | Environment-macro：accuracy difference `+1.96 pp`，95% CI `[-5.04,+8.97]`；saving difference `+12.11 pp`，CI `[+0.68,+22.85]` | **中低** | “宏平均下 saving 更高、accuracy 不可区分”可说；不能声称 accuracy 显著更高 |
| F5.5 | DEER-inspired 相对 DEER 的 saving 优势不依赖聚合方式 | Problem-pooled 684 题：Inspired saving 36.26%，DEER 37.74%，即 Inspired 反而低 1.48 pp；accuracy 为 88.74% vs 84.65% | **低/被反例削弱** | 必须明确 macro 是 benchmark/environment 等权；正文的 “saves more” 不能不加口径限定 |
| F5.6 | Verification branch 提升了 Stage-1 candidate 的正确率 | 固定 raw audit：117 个首 branch candidates 中，最终正确数净变化 0（79 对->对、36 错->错、各 1 次正反翻转）；100 次 branch commits accuracy 69%，matched full 78% | **高可靠反证/claim不支持** | 不应写 “verification protects accuracy” 或把收益归功于 branch |
| F5.7 | Verification branch 的 64-token 成本换来了有效验证 | 117/117 个 first-branch verification 均恰好 64 tokens 且 `finish_reason=length`；直接 Stage-1 commit 的反事实宏准确率不变，saving +0.764 pp，少 38,990 output tokens | **高可靠反证/claim不支持** | 现设计更像被截断的继续推理；需要新 verdict 设计或删除这一贡献表述 |
| F5.8 | 128/256-token falsification verdict 可解决 verification 问题 | 单个真实 branch 的 MLX 3-bit smoke 在 128 和 256 tokens 均未稳定产出 verdict | **低** | 仅为 feasibility smoke；不能进入主结果 |
| F5.9 | Boundary confidence 是有效 signal | DEER frozen contrast、fast-path replay、online 三 seed 结果共同同向 | **中** | 可写 `promising / provides constructive evidence`；尚不能写成完成验证的通用方法 |
| F5.10 | Boundary-confidence controller 已跨 split、规模和架构泛化 | 当前 online full test、新模型/32B confirmation 尚缺 | **低/未完成** | 这是优先级最高的新增大算力实验之一 |
| F5.11 | 当前方法实现了 DEER v3 的校准置信度 `C_cali` | 当前 confidence 是答案 token probability 的模型相关聚合，未实现考虑 token-level variance 的 `C_cali` | **低/不支持** | 不得在论文中暗示使用 DEER v3 校准；可作为下一版方法实验 |

# 8. 跨 finding 的共同依赖

| 依赖 | 影响范围 | 当前状态 | 对可靠性的影响 |
|---|---|---|---|
| 最终答案 grader 正确性 | 几乎所有 accuracy、recovery、direction-of-effect 结果 | 自动严格数学等价判分已运行；89 个困难/分歧样本已放入 [Task B 页面](../taskB_grader.html)，双人人工审计待回收 | 在审计完成前，主 accuracy claims 应保留少量 grader-systematic-error 风险 |
| Taxonomy 人工一致性 | F1.6-F1.7 | 134 例、双标注员、待计算 agreement 和仲裁 | taxonomy 目前保持低可靠 |
| Token accounting 口径 | F2、F3、F4、F5 的所有 saving claims | output-token 计费可复算；不同章节存在 net dense-probe、fair/all-generated、macro/pooled 多种视图 | 图表和正文必须同时写清 numerator、probe/readout 是否收费、聚合权重 |
| Preregistration provenance | F2 的可信度 | split、gates、rule hashes 和 artifacts 已留存 | 建议在最终 release 中提供一份不可变 manifest/commit 对照表 |
| Domain scope | 所有 finding | 仅 MATH500、AMC23、AIME24，均为可判分竞赛数学 | 任何对 code、open-ended、agentic reasoning 的外推都只有低可靠 |
| Sampling comparability | F5 online vs full | online 多请求会改变 sampling path，full 并非严格 paired trajectory | F5 的 vs-full accuracy 只能称 approximate；同 controller 间 paired comparison 更可信 |

# 9. 当前最值得补的实验

按“能提升核心 claim 可靠性”排序：

1. **Boundary-confidence 的 held-out test**：固定方法与阈值，在 test 上运行 DeepSeek-7B、Qwen3-8B；它决定 F5 能否从探索性结果升级为论文核心方法贡献。
2. **修复并重跑 Llama confirmation**：现有输出主要是重复标点/乱码，不能只提高 cap。必须先核验 checkpoint、tokenizer/chat template 与 vLLM smoke，确认正常数学回答，再按 ≤5% pilot truncation 目标设 cap 并重跑三 benchmark。
3. **拆开 fast path 与 branch 的在线消融**：至少比较 DEER、DEER+fast、DEER+fast+branch。现有证据已经支持 fast path，却不支持 verification branch；不做消融会使方法归因错误。
4. **重设计或移除 verification**：若保留，必须有短、可解析的 falsification verdict，并证明它改变候选正确率；否则论文应把贡献写成 boundary-confidence fast commit，而不是 verification branch。
5. **Probe-density / probe-cost 消融**：在同一 frozen bank 上系统比较 interval、probe length 和理想 KV-reuse cost，量化 probe tax 可降低到何种程度。
6. **完成人工审计**：Task A 给 taxonomy 定性结论；Task B 给全论文 accuracy grader 提供可信度上限。

# 10. 建议立即修订的论文措辞

| 当前倾向 | 更可靠的写法 |
|---|---|
| “No consensus rule can be safe and saving.” | “No rule in our preregistered 17,712-rule consensus space clears the conservative gate on development, and none clears it jointly on development and held-out test.” |
| “The safest stop costs 1.85 pp.” | “The development minimum is 1.85 pp; the confirmed result is frontier stability and an empty joint gate, not the exact floor.” |
| “DEER stays within about 1 pp on the same models.” | “DEER is near-neutral on Qwen3-8B but loses 4.83 pp on DeepSeek-7B, while still outperforming the consensus frontier near the low-drop region.” |
| “The verification branch escapes the accuracy tax.” | “Boundary confidence, especially the high-confidence fast path, provides exploratory evidence beyond consensus; the current verification branch has not shown independent accuracy benefit.” |
| “Inspired saves significantly more than online DEER.” | “Under environment-macro weighting, Inspired saves 12.1 pp more (95% CI +0.7 to +22.9); problem-pooled saving is 1.5 pp lower, so the advantage is aggregation-dependent.” |
| “Adaptive probing does not work.” | “The preregistered adaptive-event family is dominated within our current trigger and rule grid.” |

# 11. 维护规则

新增实验后只做三件事：

1. 在对应 claim 行加入实验范围、主结果和 artifact；
2. 检查 claim 的量词是否与新实验范围一致，再升降可靠性；
3. 若不同聚合、模型或 split 给出相反方向，不覆盖旧结果，而是拆成新的原子 claim。

论文中出现的新数字或结论，在进入 abstract/introduction/conclusion 前，应先在本文件拥有独立 ID、直接 artifact 和明确可靠性。

\newpage

# Appendix：具体实验数据与图表

本附录提供主矩阵中 43 个原子 claim 的落点。百分比均按对应实验自己的聚合口径报告；不同实验之间不得跨口径直接相减。A1-A3 使用同一 Governor v2 multivariate diagnostic 重算；A5-A13 的扩展核查由 [统一 evidence audit](../benchmark/FalseConsensus/analyze_appendix_evidence.py) 固化，并输出 [summary JSON](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/summary.json) 与逐环境 CSV；汇总图由 [附录绘图脚本](make_finding_map_appendix_figures.py) 从这些固定 artifact 生成。

## A1. Governor v2 多元数据范围与完整性 {#app-a1}

统一设置：DeepSeek-R1-Distill-Qwen-7B 与 Qwen3-8B，MATH500/AMC23/AIME24，seeds 42/43/44，共 18 个 development environments；dense simple@32 每 64 main tokens probe。MATH500/AMC23 main cap 为 16K，AIME24 为 32K。`pooled` 按题加权；`macro` 对 18 个环境等权，避免 MATH500 的题量主导结论。

| 指标 | Problem-pooled | Environment-macro |
|---|---:|---:|
| Main trajectories | 2,736 | 18 environments |
| Probe rows | 229,693 | - |
| Empty probe answers | 1,406 (0.6%) | 0.4% |
| Natural completion | 2,590 (94.7%) | 91.3% |
| Mean main tokens | 5,404 | 9,059 |
| Final accuracy | 88.6% | 78.9% |
| Whole-trajectory unanimous coverage | 11.5% | 4.7% |
| Whole-trajectory unanimous accuracy | 97.5% | 98.1% |

| Model | Benchmark | n（3 seeds） | Full accuracy | Last-5 unanimous false consensus |
|---|---|---:|---:|---:|
| Q3-8B | AIME24 | 72 | 73.6% | 23.1% |
| Q3-8B | AMC23 | 96 | 86.5% | 4.0% |
| Q3-8B | MATH500 | 1,200 | 91.2% | 6.4% |
| DS-7B | AIME24 | 72 | 47.2% | 48.5% |
| DS-7B | AMC23 | 96 | 85.4% | 4.5% |
| DS-7B | MATH500 | 1,200 | 89.8% | 10.1% |

数据源：[统一重算报告](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/report.md)、[cross-axis CSV](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/cross_axis_summary.csv)、[可复现脚本](../benchmark/FalseConsensus/governor_v2/analyze_multivariate_a1_a3.py)。本项将 F1.1-F1.2 的主要证据升级为跨模型、跨 benchmark、跨 seed 的 matched-protocol 数据；早期 Stage 1 单次实验仅保留为 provenance audit。

## A2. Agreement calibration、false consensus 与 window sensitivity {#app-a2}

Calibration 使用轨迹末尾 last-\(w\) window、至少 3 个非空答案，以最终答案正确性作为 \(y\)；CCE 同时报告 problem-pooled 与 environment-macro。完全一致答案的正确性使用项目 grader；下表中的 false-consensus rate 是其补集。作为对照，全轨迹 cumulative CCE 为 0.204 pooled / 0.241 macro；cumulative unanimous coverage 为 11.3% / 4.6%，其中 false consensus 为 1.9% / 1.5%。

| Window \(w\) | CCE pooled / macro | Unanimous coverage pooled / macro | Unanimous accuracy pooled / macro | False consensus pooled / macro |
|---:|---:|---:|---:|---:|
| 3 | 0.124 / 0.201 | 83.7% / 88.0% | 89.1% / 83.6% | 10.9% / 16.4% |
| 5 | 0.124 / 0.203 | 78.7% / 84.4% | 90.3% / 84.0% | 9.7% / 16.0% |
| 8 | 0.117 / 0.200 | 73.9% / 80.6% | 91.9% / 84.7% | 8.1% / 15.3% |

![图 A2a：18 environments 上 w=3/5/8 的 agreement calibration。点大小表示 pooled 样本量；橙色环境宏平均避免 MATH500 主导。](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/fig_a2_calibration_w3_w5_w8.png){width=72%}

作为反事实敏感性检查，strict stop 在首次出现连续 \(w\) 个非空、规范化等价答案时提交，并计入已消费的 probe output：w=3/5/8 的 macro accuracy drop 分别为 -46.60/-29.99/-17.29 pp，macro net saving 为 82.3%/66.1%/51.4%。w=3 产生 1,478 次错误提交；在实际停止的轨迹上平均节省 4,706 main tokens。因此增大 window 明显降低风险，但不能单独解决错误早停。

![图 A2b：strict unanimous stop 的 accuracy-saving window sensitivity。该反事实不是最终 Governor rule。](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/fig_a2_window_sensitivity.png){width=66%}

数据源：[calibration CSV](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/a2_calibration_summary.csv)、[strict-stop CSV](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/a2_stop_summary.csv)。A2 现在直接支撑 tested windows/settings 下的 agreement miscalibration 和 window sensitivity，不再依赖单 seed 的 `w=5, n=36` 局部点。

## A3. Probe-1、first-consensus recovery 与 consensus time {#app-a3}

`Probe-1` 是 64 main tokens 处的第一次 completion，只作为 early-readout control。主要 recovery 证据使用首次 trailing window（至少 3 个非空答案）达到 share \(\geq 0.8\) 的 dominant answer。

| Window \(w\) | Reached pooled / macro | Recovery | Overthinking | Recovery:overthinking | Probe-1 wrong -> correct final pooled / macro |
|---:|---:|---:|---:|---:|---:|
| 3 | 98.9% / 99.6% | 1,204 | 36 | 33.44:1 | 86.0% / 78.0% |
| 5 | 98.8% / 99.5% | 1,137 | 39 | 29.15:1 | 86.0% / 78.0% |
| 8 | 95.8% / 98.1% | 867 | 44 | 19.70:1 | 86.0% / 78.0% |

主分析 \(w=5\) 的 1,137 次 recovery 与 39 次 overthinking 在六个 model × benchmark cells 中方向一致；各 cell 的原始比值至少为 24.4:1，两个 AIME24 cell 没有观察到 overthinking。首次共识答案与 final answer 不同的轨迹为 1,411 条，其中 1,139 条最终正确。由此，consensus-recovery claim 明显强于 Probe-1 控制项。

![图 A3：w=5 首次共识时间与最终正确率。绝对 token 分箱呈下降，但按完整轨迹相对位置归一化后不单调，因此只能作为描述性相关。](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/fig_a3_consensus_time.png){width=72%}

数据源：[mechanism CSV](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/a3_mechanism_summary.csv)、[consensus-time CSV](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/a3_consensus_time.csv)。A3 直接支撑 F1.2-F1.3；“晚共识更差”不再作为稳健 F1.4 证据，因为归一化位置不支持单调关系。

## A4. False-consensus taxonomy 与当前人工审计状态 {#app-a4}

**状态：尚无可报告的人工标注结果。** 完整导出包含 134 个去重案例，已进入
[Task A taxonomy 页面](../taskA_taxonomy.html)，但 repo 中尚未出现 Task A/Task B
返回的 `annotations_P*.csv`。双人标注、inter-annotator agreement 和冲突仲裁均未完成。

早期 28 例 AI-assisted 分类只能用于设计 taxonomy 和标注界面，不能视为人工实验结果，
也不能支撑类别比例或“probe 格式伪影占比”等正文 claim。A4 当前只记录数据准备状态；
F1.6-F1.7 均标为**未验证**，待双人标注回收后再填入类别计数、比例、agreement 和仲裁结果。

## A5. 17,712-rule Development sweep 与 conservative gate {#app-a5}

每条规则覆盖 \(2\) models × \(3\) benchmarks × \(3\) seeds × train/dev 两个 split，
即 36 个 environment-split cells；17,712 条规则共形成 637,632 行。下表先单独定义
selection 使用的三个量，避免把规则级和 cell 级统计混在一起。

| 规则级量 | 明确定义 |
|---|---|
| `D_model(r)` | 对每个 `(split, model)`，先对其 benchmark × seed cells 的 accuracy drop 取宏平均，再取所有 train/dev `(split, model)` 中的最大值；越小越安全 |
| `D_benchmark(r)` | 对每个 `(split, benchmark)`，先对其 model × seed cells 的 accuracy drop 取宏平均，再取所有 train/dev `(split, benchmark)` 中的最大值；越小越安全 |
| `PSF(r)` | 36 个 train/dev cells 中 net total-token saving 严格为正的比例；越大越稳健 |

Conservative gate 要求
`D_model <= 1.5 pp`、`D_benchmark <= 2.0 pp`、`PSF >= 0.8`。结果是
0/17,712 条规则通过；即使只看 `D_model <= 1.5 pp` 也仍为 0 条。

下面的“分位数”是：先为**每一条规则**计算上述
`D_model(r)`，再对 17,712 个规则级数值组成的分布取分位数；
它不是 problem、probe、environment cell 或 token saving 的分位数。

| 规则集合 | Min | P1 | P5 | P25 | P50 |
|---|---:|---:|---:|---:|---:|
| Development selection：`D_model(r)` | 1.852 | 3.370 | 4.259 | 10.722 | 20.074 |

数值单位为 percentage points，使用 development phase 的 train+dev selection rows。
早期版本曾并列完整四模型 Test 分位数，但其中 Llama run 已确认发生退化乱码生成，
因此该行撤回。有效的同两模型 Dev/Test cross-split 比较独立放在 A8。

作为方向性补充，在 637,632 个 development rule-cell 中，67.72% accuracy 下降、
6.75% 上升、25.53% 不变。达到最小 `D_model = 1.852 pp` 的规则在 Dev
仍为负净节省：DeepSeek -8.9%，Qwen -8.3%。这些是另外两种统计口径，不再塞入
规则分位数表。

![图 A5：17,712 个规则在 Development selection（train+dev）上的 worst-case per-model accuracy-drop 分布。虚线为 conservative 1.5 pp gate。](figures/finding_map_appendix/a5_sweep_drop_distribution.png){width=62%}

数据源：[direction-of-effect audit](../benchmark/FalseConsensus/governor_v2/analysis/direction_of_effect.txt)、[confirmation frontier](../benchmark/FalseConsensus/governor_v2/analysis/confirmation_frontier.txt)、[sweep shards 与 checksums](../benchmark/FalseConsensus/governor_v2/generated/sweep_checksums.sha256)、[selection blocker](../benchmark/FalseConsensus/governor_v2/BLOCKERS.md)。本项支撑 F1.8、F2.2-F2.7 和 F3.4。

## A6. Rule-family frontier 与 adaptive event probing {#app-a6}

四个 family 是统一七维规则 schema 中的四个搜索模板；family 指主要 evidence/schedule
结构，其他 maturity、persistence、certainty、validity 和 history 维度仍在各自网格内变化。

| Family | 简短含义 | 该 family 最小 `D_model` | 同一规则的 Dev `S20` |
|---|---|---:|---:|
| Latest persistence | 最新有效答案需连续保持相同若干次，并可要求跨越最短 token span | 8.20 pp | ≈9.7% |
| Window share | 最近 \(w\) 个有效 probes 中，dominant answer share 达到阈值 | 4.87 pp | ≈0.3% |
| Entropy budget fraction | 达到最小预算比例后，答案分布 entropy 低于阈值才允许接受 | 1.85 pp | -11.0% |
| Adaptive event probe | 不只定期 probe；在结论词、entropy drop、反思转折或答案候选等事件处 probe，再用 latest/window/entropy evidence 判停 | 9.70 pp | ≈4.5% |

这里 `S20(r)` 是该规则在 **18 个 Dev environments** 上
`total-token saving fraction` 的第 20 百分位；total tokens 包括主生成和该规则实际消费的
probe output，因此 `S20 > 0` 表示至少约 80% 的 Dev 环境仍有正净节省。表中每行只是
该 family 内 `D_model` 最小的诊断点，不是四个正式 selected rules。

### Pareto sweep 与预注册选择

实际选择器为每条规则计算三个目标：

1. 最大化 Dev `S20(r)`；
2. 最小化 train+dev 的 `D_model(r)`；
3. 最小化 train+dev 的 `D_benchmark(r)`。

若另一规则在三个目标上都不差且至少一个严格更好，则当前规则被支配；完全同指标的规则
只保留复杂度更低者。17,712 个候选最终形成 93 个非支配点。随后分别对
conservative、balanced、token-efficient 三组预注册 gate 过滤 Pareto 前沿；每组在合格点中
优先选择 Dev `S20` 最大的、尚未被其他 operating point 使用的规则，再以 PSF、
规则复杂度和 rule ID 破同分。

关键结果是：conservative gate 下没有合格点，因此预注册 selector **没有成功冻结三个
operating-point 策略**。A6 上表是 family frontier diagnostic，不能写成
“Pareto sweep 选出的四个策略”。此外，当前实现以 train+dev 共同构造风险约束、以 Dev
`S20` 排序，并不是先只用 train 剪枝、再完全独立用 Dev 选择。

数据源：[selection implementation](../benchmark/FalseConsensus/governor_v2/replay_rules.py)、
[protocol](../benchmark/FalseConsensus/governor_v2/protocol.json)、
[selection blocker](../benchmark/FalseConsensus/governor_v2/BLOCKERS.md)、
[candidate rule registry](../benchmark/FalseConsensus/governor_v2/generated/candidate_rules.jsonl)。
本项支撑 F2.7-F2.8；它只否定当前 Dev grid 中的 adaptive-event family，不否定未来
online adaptive controller。

## A7. Accuracy-tax 的方向强度 {#app-a7}

这里比较同一题目的完整生成与反事实早停结果：

- **Harm（破坏恢复）**：完整生成答对，但早停提交错误答案；
- **Rescue（避免过度思考）**：完整生成答错，但早停提交正确答案；
- **Harm/rescue ratio**：Harm 数量除以 Rescue 数量。大于 1 表示早停破坏正确恢复
  比挽救错误终局更常见。旧缩写 `FC/SW`、`FW/SC` 不再使用。

四个 named Governor rules 均在固定 128-token probe schedule 上运行：

| Rule | 具体停止条件 |
|---|---|
| Naive consensus | 不设最小 token；连续 3 个非空 probe 答案一致即停止，不要求 certainty |
| Conservative | 至少生成 1,024 tokens；连续 8 个 schema-valid 答案一致，且全部标记 certain |
| Balanced-general | AMC/AIME 至少生成 1,536 tokens；连续 5 个 task-aware-valid 答案一致且 certain |
| Balanced-math | MATH level <4 至少 768 tokens、level ≥4 至少 2,048 tokens；连续 5 个 schema-valid 答案一致且 certain |

| Named rule | Stopped | Harm：完整对、早停错 | Rescue：完整错、早停对 | Harm/rescue |
|---|---:|---:|---:|---:|
| Naive consensus | 2,649 | 1,055 | 30 | 35.17 |
| Conservative | 2,157 | 467 | 32 | 14.59 |
| Balanced-general | 325 | 60 | 4 | 15.00 |
| Balanced-math | 1,946 | 476 | 26 | 18.31 |

Naive 的模型拆分也同向：Qwen 为 575/16 = 35.94，DeepSeek 为
480/14 = 34.29。它们不是额外规则，因此不再混入主表。

下面两个 diagnostic 必须区分。`First local consensus` 在最近最多 \(w\) 个 probes 中
至少有 3 个有效答案、dominant share ≥0.8 时触发，可能在窗口尚未填满时触发；
`Strict unanimous` 则要求恰好连续 \(w\) 个非空答案全部一致。

\Needspace{9\baselineskip}

**First local consensus（share ≥0.8，至少 3 个有效答案）**

| Window \(w\) | Reached | Harm | Rescue | Harm/rescue |
|---:|---:|---:|---:|---:|
| 3 | 2,707 | 1,204 | 36 | 33.44 |
| 5 | 2,702 | 1,137 | 39 | 29.15 |
| 8 | 2,621 | 867 | 44 | 19.70 |

**Strict unanimous stop（连续 \(w\) 个答案全部一致）**

| Window \(w\) | Stopped | Harm | Rescue | Harm/rescue |
|---:|---:|---:|---:|---:|
| 3 | 2,707 | 1,204 | 36 | 33.44 |
| 5 | 2,620 | 730 | 42 | 17.38 |
| 8 | 2,456 | 415 | 44 | 9.43 |

![图 A7：named rules、first local consensus 与真正 strict-unanimous replay 的 harm/rescue ratio。所有已测设置均大于 1，但两种 consensus 定义不能混称。](figures/finding_map_appendix/a7_direction_ratio.png){width=72%}

数据源：[named-rule direction audit](../benchmark/FalseConsensus/governor_v2/analysis/direction_of_effect_ratio.txt)、
[local-consensus mechanism CSV](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/a3_mechanism_summary.csv)、
[strict-stop CSV](../benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3/a2_stop_summary.csv)。
本项直接支撑 F1.3 与 F3.3；该 ratio 是配对结果的方向强度，不是 causal risk ratio。

## A8. Dev-Test cross-split confirmation {#app-a8}

比较同一两个 development models 上共同存在的 17,712 个规则；Dev 选择与 Test 评估分别使用各自 split。

| 指标 | 结果 |
|---|---:|
| Dev gate pass | 0 |
| Test-alone gate pass | 272 |
| Joint Dev and Test pass | 0 |
| 272 个 Test passers 回看 Dev | drop min 4.98；median 5.09；max 5.65 pp |
| Dev least-bad rule | Dev 1.85 -> Test 0.11 pp |
| Test least-bad rule | Test -0.33 -> Dev 4.87 pp |
| Across-rule correlation | Pearson r = 0.962 |

为直观看完整策略空间，图 A8 对 Dev 和 Test 分别画出全部 17,712 条规则。横轴是
同两模型的 worst per-model accuracy drop，纵轴是 18 个对应 environments 的
total-token saving 第 20 百分位；每个点是一条规则，黑线是“accuracy drop 更低、
saving 更高”的二维非支配前沿。二维线只用于展示，不替代完整 gate 中额外的
per-benchmark drop 和 PSF 约束。

![图 A8：同两模型的 Dev/Test 策略点阵与二维 Pareto frontier。红虚线为 1.5 pp per-model gate，灰虚线为零净节省。](figures/finding_map_appendix/a8_confirmation_gate.png){width=78%}

此前报告的“完整 4-model Test 有 204 个 test-only passers”混入了无效 Llama run，
因此不再作为证据。A8 只使用两个采集有效且 Dev/Test 对齐的 development models；
Qwen-32B 作为单独 scale diagnostic 放在 A9，不与同模型 cross-split frontier 混池。

数据源：[cross-split audit](../benchmark/FalseConsensus/governor_v2/analysis/confirmation_cross_split.txt)、
[per-rule plot data](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/a8_strategy_points.csv)、
[rebuild script](../benchmark/FalseConsensus/governor_v2/analysis/build_a8_strategy_points.py)。
本项支撑 F2.5、F2.6、F2.9-F2.10，并说明可靠结论是 joint gate 为空与 frontier 同向，
而非某个精确 floor。

## A9. Confirmation 覆盖与 unseen-model 边界 {#app-a9}

| Model role | Model | 计划范围 | 实际有效性 | 结论 |
|---|---|---|---|---|
| Seen development | Qwen3-8B | 3 benchmarks × seeds 45/46/47 | 342/342 trajectories；13 truncated (3.8%) | 完整有效 |
| Seen development | DeepSeek-7B | 3 benchmarks × seeds 45/46/47 | 342/342；9 truncated (2.6%) | 完整有效 |
| Held-out scale | DeepSeek-Qwen-32B | 3 benchmarks × seed 45 | 114/114；1 truncated (0.9%) | **预注册范围内完整**；只有单 seed，因此只是规模证据 |
| Held-out architecture | DeepSeek-Llama-8B | 原计划 3 benchmarks × seed 45 | 仅 MATH/AMC，共 108 条；缺 AIME；98 length-stop、95 个空 final answer、仅 1/108 正确 | **运行无效，不能作为架构证据** |

32B 并非采集不完整：held-out scale 模型从一开始就只计划 seed 45，以控制 32B confirmation
成本；三 benchmark 的全部 114 题和 probes 均齐全。

Llama 的问题也不只是 cap 设置偏小。98 条 `finish_reason=length` 轨迹达到 16K cap，
但其正文从开头便主要是重复的句点、括号、`and` 等退化乱码，而不是正常数学推理；
95/108 无法抽取答案，最终只有 1 题正确。提交记录说明 AIME24 因 32K
“non-terminating generation”被省略。现有 artifact 没有保存足以唯一归因的 server log、
checkpoint hash 或 tokenizer smoke，因此无法判断具体是 checkpoint、tokenizer/chat
template 还是 serving/解码错误；但可以确定该 run 不应解释成“较弱模型推理更长”。

因此，目录级审计是 **23 个 observed environments 文件齐全**，但预注册计划实际为
24 个 environments、912 条轨迹；最终只有 23/24、906/912，且其中两个 Llama
environments 科学上无效。修复顺序应是：先用固定数学题做可读性与答案抽取 smoke，
核对模型权重/tokenizer/template，再进行 cap pilot，最后补齐三 benchmark。

数据源：[统一 environment audit](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/confirmation_environment_audit.csv)、
[Llama trajectories](../benchmark/FalseConsensus/results/governor_v2/confirmation__deepseek-ai-deepseek-r1-distill-llama-8b__math500__seed_45/main/traj/)、
采集提交 `612cc69b` 与
[seen-model audit](../benchmark/FalseConsensus/results/governor_v2/confirmation_runtime/audit_final.json)。

## A10. Related-work baselines 与 Governor Pareto 位置 {#app-a10}

Dev benchmark-macro；2 models × 3 benchmarks × seeds 42/43/44。`Saving` 为 all-generated output-token saving，包含方法辅助输出，不含 prompt/prefill。

三项 baseline 都进行了**独立的 method-specific GPU probing**，不是把 Governor
`simple@32` probe 改名后重放；每种方法均有 2,736 条逐题记录和 18 个完整
method-environments。但 “有真实 probe 数据” 不等于三者都是端到端 faithful：

| Baseline | 原始覆盖 | 忠实复现的 probe 部分 | 仍存在的 adaptation / 正确标签 |
|---|---:|---|---|
| CertaIndex mid | 2,736 rows；27,193 probe calls | 原作 suffix、64-token interval、20-token cap、patience=3、certainty 与数学等价 stop rule | 只把 live chunk timing 换成相同位置的 frozen prefixes；**probe-level faithful，frozen-timing reproduction** |
| DEER | 2,736 rows；14,017 trial calls | 官方 `Wait` trigger、最多 10 次、20-token trial、0.95 门槛、avg1/avg2、Qwen `</think>` gate 与正式 readout | main path 预先冻结；**official probe/readout replay，不是完整 online controller run** |
| TJE | 2,736 rows；38,672 confidence calls | Figure-2 system instruction、10 个 confidence labels、`Wait` + `</think>` trigger、`Almost certain` 门槛 | main trajectory 未在 TJE system prompt 与低置信 `Wait` 续写下重新生成，且 label 用 constrained choice；**frozen adaptation，不能称 fully faithful** |

因此，A10 数字是可审计的同轨迹、真实 re-probing 比较。CertaIndex 的 probe
faithfulness 最强；DEER 的 trial/confidence/readout 逻辑忠实，但部署路径冻结；
TJE 的 probe 内容有原文依据，因主轨迹分布和 constrained decoding 两项改动，
只能作为较低保真度的 adaptation。三者均不应直接称为“复现了原论文端到端结果”。

| Model | Method | Accuracy | Δacc vs Full | Saving | Main saving | Stop rate |
|---|---|---:|---:|---:|---:|---:|
| Qwen3-8B | Full | 85.44% | 0.00 pp | 0.00% | - | - |
| Qwen3-8B | CertaIndex | 15.33% | -70.11 pp | 90.10% | 91.00% | 99.78% |
| Qwen3-8B | DEER | 86.22% | +0.78 pp | 16.29% | 21.37% | 41.35% |
| Qwen3-8B | TJE | 85.00% | -0.44 pp | 2.03% | 5.82% | 22.50% |
| DeepSeek-7B | Full | 79.76% | 0.00 pp | 0.00% | - | - |
| DeepSeek-7B | CertaIndex | 23.87% | -55.89 pp | 76.68% | 78.60% | 98.67% |
| DeepSeek-7B | DEER | 74.93% | -4.83 pp | 20.16% | 25.68% | 56.07% |
| DeepSeek-7B | TJE | 60.67% | -19.09 pp | 65.00% | 78.45% | 93.44% |

逐 benchmark 的三-seed macro 显示重要异质性：

| Model | Method | Δacc range across benchmarks | Saving range across benchmarks |
|---|---|---:|---:|
| Qwen3-8B | CertaIndex | -83.33 to -43.67 pp | 89.85% to 89.98% |
| Qwen3-8B | DEER | 0.00 to +2.33 pp | 4.83% to 33.36% |
| Qwen3-8B | TJE | -1.33 to 0.00 pp | -1.84% to 4.30% |
| DeepSeek-7B | CertaIndex | -75.00 to -42.67 pp | 63.33% to 83.50% |
| DeepSeek-7B | DEER | -10.33 to 0.00 pp | 4.47% to 39.77% |
| DeepSeek-7B | TJE | -27.78 to -8.67 pp | 56.42% to 73.89% |

同一 matched harness 中，三个 named Governor consensus baselines 的模型宏结果也明显远离低-drop 区：balanced-task-aware 为 Qwen `-34.39 pp / 54.31%`、DeepSeek `-15.13 pp / 40.42%`；conservative 为 `-29.69/47.83%` 与 `-9.94/26.22%`；naive 为 `-56.48/84.36%` 与 `-36.22/68.98%`。

![图 A10：Dev 上 train-retained Governor candidates、Pareto boundary 与三项 related-work anchors。横轴为 accuracy drop，纵轴为 all-generated token saving。](../benchmark/FalseConsensus/report/figures/governor_related_work_pareto_dev.png){width=72%}

![图 A10b：两模型上的 related-work anchors 与 matched named Governor rules。点越靠左上越好；跨 benchmark 范围见上表。](figures/finding_map_appendix/a10_matched_methods.png){width=68%}

数据源：[related-work protocol/commands](../benchmark/FalseConsensus/related_work/README.md)、
[raw method-specific outputs](../benchmark/FalseConsensus/results/related_work/full/)、
[related-work aggregate report](../benchmark/FalseConsensus/results/related_work/aggregate/report.md)、
[benchmark audit CSV](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/related_work_benchmark_macro.csv)、
[matched Governor macro](../benchmark/FalseConsensus/results/governor_v2/existing_methods_matched/governor_dev_macro.csv)、
[Pareto source CSV](../benchmark/FalseConsensus/report/figures/governor_related_work_pareto_frontiers.csv)。
本项支撑 F4.1-F4.5 与 F5.9；上述 fidelity label 必须随结果出现，现有 artifact
仍无 related-work Test rows。

## A11. Fast-path-only 配对消融与 trial/readout 冗余 {#app-a11}

Fast path 规则：若已有 DEER trial answer 非空且 confidence >0.995，直接交付 trial answer 并省去 formal readout；否则完全保持原 DEER。主轨迹和 branch 均不改变。

| Split / model | Original DEER acc | Fast acc | Δacc | Original saving | Fast saving | Δsaving |
|---|---:|---:|---:|---:|---:|---:|
| Train / Qwen3-8B | 79.10% | 79.75% | +0.65 pp | 17.17% | 20.21% | +3.04 pp |
| Train / DeepSeek-7B | 67.55% | 68.96% | +1.41 pp | 23.61% | 25.51% | +1.90 pp |
| Dev / Qwen3-8B | 86.22% | 85.89% | -0.33 pp | 16.29% | 18.69% | +2.39 pp |
| Dev / DeepSeek-7B | 74.93% | 76.37% | +1.44 pp | 20.16% | 22.17% | +2.01 pp |

Dev 共 684 trajectories：340 个 confidence candidates，5 个 invalid 回退，335 个 fast commits；16 个 readout-wrong -> trial-correct，6 个 readout-correct -> trial-wrong；避免 131,199 output tokens 和 361,079 prompt/prefill tokens。统一 raw audit 又重算 486 个 Dev triggered pairs：72 次 trial/readout 不一致（14.81%），trial/readout accuracy 88.68%/88.48%，formal readout 平均 470.5 output tokens。

![图 A11-A12：左图为 Train/Dev fast-path-only 配对组件效果；右图为完整 online controller 的三 seed environment-macro。](figures/finding_map_appendix/a11_a12_boundary_components.png){width=78%}

数据源：[fast-path report](../benchmark/FalseConsensus/results/deer_inspired/fast_path_only_replay/report.md)、[fixed summary.json](../benchmark/FalseConsensus/results/deer_inspired/fast_path_only_replay/summary.json)、[统一 evidence summary](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/summary.json)、related-work DEER raw artifacts。Train/Dev fast-path table 支撑 F5.2；固定的 486-pair readout audit 支撑 F5.1。

## A12. 完整 DEER-inspired online controller：三 seed Dev {#app-a12}

每个 seed 含 456 method-problem rows；两模型、三 benchmark。统一 raw audit 检查了 36/36 run directories、1,368/1,368 rows；所有 manifest 完整，36 个 run 使用同一个 protocol version 与 config hash。下表为 benchmark/environment 等权宏平均。逐 seed 与三-seed summary 分开，避免把 macro 当成额外 seed。

| Seed | Inspired Δacc vs Full | Inspired fair saving | Qwen Δacc / saving | DeepSeek Δacc / saving |
|---|---:|---:|---:|---:|
| 42 | -0.36 pp | 43.7% | +2.78 pp / 45.6% | -3.50 pp / 41.8% |
| 43 | +4.17 pp | 33.8% | -1.72 pp / 36.1% | +10.06 pp / 31.5% |
| 44 | -6.06 pp | 25.1% | -5.56 pp / 41.2% | -6.56 pp / 8.9% |

| Method summary | Δacc vs Full | Fair saving | Qwen Δacc / saving | DeepSeek Δacc / saving |
|---|---:|---:|---:|---:|
| Inspired | -0.75 pp | 34.2% | -1.50 pp / 41.0% | 0.00 pp / 27.4% |
| Online DEER | -2.71 pp | 22.1% | -1.54 pp / 18.0% | -3.89 pp / 26.1% |

Paired 18-environment bootstrap（Inspired - DEER）：Δaccuracy +1.96 pp，95% CI [-5.04, +8.97]；Δsaving +12.11 pp，95% CI [+0.68, +22.85]。数据源：[统一 evidence summary](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/summary.json)、[逐环境 metrics](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/deer_online_environment_metrics.csv)、[multiseed report](../benchmark/FalseConsensus/deer_inspired/multiseed_report.txt)、[seed-42 formal aggregate](../benchmark/FalseConsensus/results/deer_inspired/online_dev/aggregate/report.md)。本项支撑 F5.3-F5.4 与 F5.9；数据完整性问题已补齐，但仍尚无 test。

## A13. 聚合敏感性与 verification-branch 消融 {#app-a13}

### A13.1 Environment-macro 与 problem-pooled

| 聚合 | Inspired accuracy / saving | Online DEER accuracy / saving | Inspired - DEER |
|---|---:|---:|---:|
| Environment-macro | Δacc -0.75 pp / 34.2% | Δacc -2.71 pp / 22.1% | +1.96 pp accuracy；+12.11 pp saving |
| Problem-pooled（684 problems） | 88.74% / 36.26% | 84.65% / 37.74% | +4.09 pp accuracy；-1.48 pp saving |

### A13.2 Verification branch raw audit

| 诊断 | 结果 |
|---|---:|
| First branch candidates | 117 |
| Correct -> correct | 79 |
| Wrong -> wrong | 36 |
| Wrong -> correct | 1 |
| Correct -> wrong | 1 |
| Branch commits | 100；accuracy 69% vs matched full 78% |
| Verification termination | 117/117 first branches 恰好 64 tokens，`finish_reason=length` |
| Counterfactual: 直接 Stage-1 commit | 宏准确率不变；saving +0.764 pp；少 38,990 output tokens |

第一张表说明 F5.4 的 saving 优势依赖 environment-macro weighting，直接支撑 F5.5。第二张表现已由 [统一 evidence audit](../benchmark/FalseConsensus/analyze_appendix_evidence.py) 从 3-seed online raw records 固化重算；它以高可靠度反驳 F5.6-F5.7 当前版本，而不是为 verification 提供正面支撑。117 个 first branch records 中只有 1 个包含后续第二次 branch，表中转移统一按 first branch candidate 到最终 delivered answer 定义。

## A14. 协议、置信度与 token accounting {#app-a14}

| 项目 | 固定定义/实现 | 影响 |
|---|---|---|
| Frozen-trajectory Governor | 先冻结 main trajectory，再对固定 prefixes 离线 probe；规则只选择 stop/readout | 支撑 stopping rule 与 main generation 解耦；不是 online deployment |
| `simple@32` | 单次 probe completion，最多 32 output tokens；不是 32 次采样 | 所有 dense-probe 税和 evidence density 解读均依赖此事实 |
| Probe interval | 当前主 sweep 为每 64 main tokens 一个可用 probe | 使 stop position 足够稠密，也造成较高 probe tax |
| Governor `is_certain` | simple@32 文本中不含 uncertainty markers | 不是 token-probability confidence |
| DEER confidence - DeepSeek | Trial-answer token probabilities 的算术平均（`avg1`） | 模型相关 readout |
| DEER confidence - Qwen3 | Trial-answer token probabilities 的几何平均（`avg2`），并要求 `</think>` | 过滤 incomplete thinking；与 DeepSeek 聚合不同 |
| DEER v3 `C_cali` | 当前未实现 token-level variance calibration | 不得声称实现 `C_cali` |
| Output-token accounting | `T=s+p`；gross `(B-s)/B`；net `(B-s-p)/B` | `p` 为 consumed probe/aux output；不含 prompt/prefill、wall time、KV memory |
| Online fair saving | `(full output - all controller-generated output)/full output` | 包含 main、probe、verification、readout output |

实现/协议来源：[dense probing implementation](../benchmark/FalseConsensus/governor_v2/dense_probe.py)、[related-work README](../benchmark/FalseConsensus/related_work/README.md)、[DEER config](../benchmark/FalseConsensus/related_work/configs/deer.json)、[Governor v2 protocol](../benchmark/FalseConsensus/governor_v2/protocol.json)、[在线 36-run audit](../benchmark/FalseConsensus/results/appendix_evidence_upgrade/summary.json)。本项支撑 F2.1-F2.2、F3.1-F3.2、F3.5-F3.6、F4.2、F4.5-F4.6 和 F5.11 的实现边界。

## A15. Evidence gaps、反证与待完成实验 {#app-a15}

| 对应 claim | 当前缺口/反证 | 升级可靠性所需最小证据 |
|---|---|---|
| F1.6-F1.7 | 仅 28 例 AI-assisted 初标；134 例人工双标尚未回收 | 双标 agreement、冲突仲裁、最终 taxonomy 表 |
| F2.12 | 有限 17,712-rule schema 不能覆盖所有 consensus controller/domain | 只能收窄量词；新增规则空间也不能证明无限全称 |
| F3.5-F3.6 | 无 interval × probe length × KV reuse 的直接消融 | 固定 stop rule 的 probe-density/cost factorial ablation |
| F4.4/F4.6 | Baselines 在 trigger、trial、readout 等处同时不同；不是原论文完整端到端复现 | matched-signal ablation；在各论文原设置上的独立 sanity check |
| F4.1-F4.5 | Related-work artifacts 只有 Train/Dev，Test rows 为 0 | 冻结方法与配置后运行 held-out Test；不得用 Dev Pareto 代替 |
| F5.6-F5.7 | Branch 净纠错为 0；所有 commit verification 均被 64-token cap 截断 | 删除该贡献，或预注册新 verdict/controller 并做组件消融 |
| F5.8 | 单个真实 branch 的 128/256-token smoke 均未稳定输出 verdict | 更简洁的可解析 verdict，先做批量 feasibility，再做 accuracy test |
| F5.10 | 完整 boundary controller 尚无 held-out test、32B 或新架构 online 结果 | Test × 多 seed × 至少一个 scale/architecture holdout |
| F5.11 | 当前没有 DEER v3 `C_cali` | 实现 variance-aware calibration，并与现聚合做 paired ablation |
| F2.11 | Llama-8B confirmation 出现退化乱码；缺 AIME，98/108 length-stop，95 个空答案 | 先修复/核验 checkpoint-tokenizer-template-serving 链路并通过 smoke，再 pilot cap、补齐三 benchmark |
| 全部 accuracy claims | 89 个困难/分歧 grader cases 的双人人工审计待回收 | agreement、仲裁与自动 grader 的 error-rate 区间 |
| 全部 domain claims | 仅竞赛数学 | 至少一个 code 或 open-ended reasoning benchmark |

本项是“证据落点”而非正面结果：凡主矩阵引用 A15，均表示该 claim 当前必须降格、收窄或保留为 future work。
