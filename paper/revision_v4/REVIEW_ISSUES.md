# v4 论文修改清单

分支 `v4` @ `36d661ac`。正文 8 页 / 全文 16 页，编译干净、无 undefined ref。

分两部分：**Part A 是 Antony 的意见（优先）**，**Part B 是数据核对发现的问题**。
Part B 各条已经过 Antony 裁定，每条开头标注了处理方式。

---

# Part A — Antony 的修改意见

## A1. 统一 self-consensus 措辞并声明简写

现状：`self-consensus` 全文只在 `02_related_work.tex:26` 出现一次，之后一律写
`consensus` / `intermediate answer consensus` / `probe agreement`，术语漂移。

改法：在 §2「Where agreement gets its meaning」首次定义 **self-consensus**（单轨迹上
对同一前缀反复探测得到的一致性），并紧接着声明后文简写：

> …which we call \emph{self-consensus} to keep the two apart; where no ambiguity
> arises we abbreviate it to \emph{consensus} in the remainder of the paper.

然后全篇检查一遍：凡是指"单轨迹探针一致"的地方统一到 self-consensus / consensus 这一对，
不要再混用 `probe agreement`、`intermediate answer consensus`、`answer stability` 等同义词。
（当前 `consensus` 出现约 76 次，散在 9 个文件里。）

## A2. 三个 gate 的来历要交代，且 tab:gates 移回正文

现状：`tab:gates` 在 `A_appendix.tex`（Preregistration Text 一节），正文 §5.1 只用一句话
列了三组数值，完全没说这三组数是怎么定的 —— 审稿人会直接问"阈值是不是挑出来的"。

改法：把 `tab:gates` 移回 §5.1（Preregistered Rule Space and Gates），并加入说明。建议措辞：

> We fix three increasingly permissive operating points before evaluation to
> represent conservative, balanced, and token-oriented deployment regimes. They
> are not proposed as universal safety standards; rather, they test whether
> self-consensus offers a practically meaningful trade-off across a range of
> accuracy and saving requirements.

## A3. 补上"为什么要做 sweep"的动机声明

现状：§5 开头只说"有人会说是你没调好，所以我们穷举"。这是防守式的，没说清我们问的是
**更严格的部署问题（单一策略能否迁移）**。

改法：在 §5 开头（或 §5.1 之前）加入。建议措辞：

> Existing results show that favorable consensus-based operating points can
> exist, while performance varies substantially across settings. We therefore ask
> the stricter deployment question of whether a single selected policy transfers.

## A4. 删掉重复措辞，尤其是 "positive control"

`positive control` 出现在 `01_introduction.tex:57`、`01:108`、`02_related_work.tex:44`、
`05_results.tex:9`、`10_limitations.tex:27,31` —— 6 次。强调一到两次足够。
建议保留 intro 一次 + §5.1 一次，其余改成 "DEER"、"the non-consensus control" 等。

同类需要去重的还有（每处只保留最有力的一次）：

- "swept through the identical pipeline, gates, and token accounting" —— intro、§5.1、
  §5.3、§5.7、Limitations 各一次。
- "the failure is the signal's, not early exit's" —— 摘要、intro、§5.7、Conclusion 各一次。
- "not because the rule is untuned" —— intro、Conclusion。
- "reproduced on a held-out split and two unseen models" —— 摘要、intro、Conclusion、§5.5。

## A5. 不要主动说 macro 会让单题影响变大

现状：`A_appendix.tex` 的 **Metric resolution** 段写了
"one AIME24 problem is $16.7\pp$ of a $6$-problem split but only ${\sim}1/108$ of the
macro drop"；**Selection-pipeline details** 段又把 dev/test 不对称归因于
"AMC23 and AIME24 under Qwen3-8B, $8$ and $6$ problems, which carry the same weight as a
$100$-problem environment under macro-averaging"。

这两处是在自曝 macro 加权的脆弱面。删掉或大幅弱化 —— 保留"macro 防止 MATH500 主导"
这一正面理由即可，不要展开单题/小环境的敏感性讨论。

## A6. §4.1 四个 fact 全部要改

**(a) 要报 first consensus 的错误率。** 现在 §4.1 没有一个数字直接回答"第一次形成共识时
答案有多大概率是错的"，而这正是在线规则真正面对的量。fact4 的 stopped-answer acc
$50.5\%$ 已经是这个量（首次三连一致且 certain），应该把它提上来讲清楚，而不是当成
"naive stop" 的副产品。

**(b) 删掉 first probe 那条。** "of the 1,148 trajectories whose first probe is wrong,
89.1% eventually flip to correct" —— 第一个探针根本不构成共识，这条对论点没有意义，还给
审稿人留下"你在拿最弱的情形凑数"的口实。直接删。

**(c) 84.2% 必须说清是谁的正确率。** 已核对源码
（`false_consensus_16k.py` fact2）：这里的 `ended up correct` 取的是
`r["final_correct"]`，即**轨迹最终答案**的正确率，不是早停答案的正确率。
现在的写法"$84.2\%$ ended up correct"字面上没错，但极易被读成后者。改成显式表述，例如
"…their trajectory's final answer was correct in $84.2\%$ of cases"。

**(d) "later consensus is worse" 这条不成立，建议删除或重写。**
已核对源码：fact3 的 `acc` 同样是 `final_correct`，所以这条实际测的是
**"晚形成共识的题目最终正确率更低"**，即难题更难 —— 它完全没有度量共识本身的可靠性，
而正文却写成 "consensus formed before 512 tokens is $91.0\%$ correct, but consensus forming
only after 2048 tokens is $71.6\%$ correct"，读起来像是共识答案的正确率。这是明确的误述。

更关键的是，按**相对位置**（早停位置 / 轨迹全长）分箱时结论完全反过来。
`report/figures/gen/consensus_position_cache.json`（dev，18 环境，共识答案正确率）：

| 相对位置 | n | 共识答案正确率 |
|---|---:|---:|
| 0–10% | 338 | 27.5% |
| 10–20% | 155 | 47.1% |
| 20–30% | 78 | 51.3% |
| 30–40% | 46 | 52.2% |
| 40–60% | 44 | 77.3% |

晚共识**更准**，不是更差。绝对 token 阈值把"难题轨迹更长"混进来了。
建议：删掉 fact3，或改写成"绝对时间上的晚共识来自更难的题目；按相对位置归一后，
早期共识才是最不可靠的区间"—— 后者反而更支持全文论点（且 `fig_consensus_pos` 已经画了这个）。

## A7. 删掉 "the cheapest thing to write is what it wrote last time"

出现两处：`01_introduction.tex:30`、`06_mechanism.tex:100`。这是对模型动机的拟人化归因，
无法从数据支持。替换为：

> A model that has not finished reasoning is nonetheless forced by the probe to
> write an answer, and consecutive unsettled prefixes naturally produce similar or
> equivalent answers;

（`06_mechanism.tex` 那一处同样改写，不要保留"cheapest"这类表述。）

## A8. Intro 的 45:1 要点明它与 early exit 的初衷冲突

现状（`01_introduction.tex:38`）只是陈述比值，没说这个数字为什么致命。加一句：

> Early stopping aims to reduce token costs without compromising accuracy, while
> ideally avoiding overthinking—a goal that is directly undermined by a high
> harm-to-rescue ratio.

## A9. Intro 不要反复强调 "none clears any gate"

现状 `01_introduction.tex:49-51` 连着说了两遍（"No setting of these knobs closes the gap" +
"not one of the 3,520 rules is both safe and saving—none clears any gate"）。合并为：

> No setting of these knobs clears any gate: not one of the $3{,}520$ rules is
> both safe and saving.

同时检查 `01:82`（Fig 1 caption）和 `01:87` 是否与正文重复表述同一件事。

## A10. 删掉 §2 结尾的 Huang 那半句

`02_related_work.tex:32-34`：

> …that the same-prefix answer is still moving is what Section~\ref{sec:mechanism}
> establishes by direct measurement (distinct from prompted, post-hoc
> self-correction, which \citet{huang2024selfcorrect} find unreliable).

整句删除（括号内外一并删）。与本文论点无关，且引入了一个会分散注意力的对照。

## A11. "declining to stop" 要补上"停得很晚"

`06_mechanism.tex:15`（§4 导语）和摘要、Conclusion 里同类表述。窗口变大的实际效果是
**要么不触发、要么触发得极晚**，只说前者不准确。改为
"only by declining to stop, or by stopping very late"。

## A12. "every probe reads the same prefix" 不准确

`06_mechanism.tex`（§4.5 The Role of Independence）：探针读的是**逐步延长的嵌套前缀**，
不是同一个前缀。改为：

> …probing one trajectory yields nested, highly dependent observations of one
> trajectory, so the readings move together…

## A13. Caption 全面精简

现在 `fig:idea` 的 caption 约 210 词、`fig:split-transfer` 约 130 词、`fig:ws-heatmap` 约 130 词。
按 ACL 惯例压到 60–90 词，把解释性内容移进正文或删除。
（`paper/revision_v3/CAPTIONS.tex` 里有长版本可留作备份。）

---

# Part B — 数据核对发现的问题（已裁定）

## B1. 〔改用裁决记录的计数〕taxonomy

**裁定：** 采用已提交的裁决记录。文中只写"两名标注者独立标注"，
**不提 A/D 的合并或口径调整**——我们的处理本身是合理的，不必自找麻烦。

**(a) 计数改为裁决记录。** 目前正文和图取的是标注者 1 的原始计数
（A:27 / D:80 / E:23 / 其他:4 → 20.1% / 59.7% / 17.2% / 3.0%）。
改用 `results/human_eval/adjudicated/`：

| 类别 | n | 占比 |
|---|---:|---:|
| D 未收敛的猜测 / placeholder | 82 | **61.2%** |
| A 已收敛但答错 | 24 | **17.9%** |
| E 探针格式伪影 | 25 | **18.7%** |
| 其他（B 表达式坍缩 / C 符号错） | 3 | 2.2% |
| 合计 | 134 | |

结论不变（仍是三比一），但摘要、intro contribution、§4.3、
`fig:wording-taxonomy` (b) 的百分数都要同步。
同时改 `report/make_v3_figures.py`：现在 `fig_taxonomy` / `fig_wording_taxonomy` 里写的是
`adj = a1[k] if a1[k] in ("A","D","E") else "O"`，即直接取标注者 1，需改为读裁决结果。

**(b) $\kappa$ 一处提醒。** 现在文中的 $\kappa=0.82$ 是在 {substantive error /
format artifact / other} 这个三类编码上算出来的（我重算 = 0.8175）。这本身没问题，
但如果只写一个裸的 "$\kappa=0.82$" 紧挨着上面那张四类分布表，审稿人问起来
"这个 $\kappa$ 是在哪几类上算的"时不好回答。建议顺手把编码写出来即可，一句话：

> Two annotators independently labelled all cases; agreement on the top-level
> coding (substantive error / probe-format artifact / other) is $\kappa=0.82$.

不需要任何额外说明。

## B2. 〔按清洗后数据改〕two-wording 的 57% 要更新

**裁定：** 采用清洗后的干净数据。

**为什么要清洗：** paired 探针库只重探到 **3,072 token**，比这更长的轨迹在
"位置占全长百分比"的后段 bin 里根本没有观测，位置归一化失真。清洗 = 丢弃
**140** 条超过探针覆盖范围的轨迹 + **19** 条撞预算未自然结束的轨迹，
剩 **241 / 400** 题、**2,898** 个可比位置（未清洗为 6,525）。

清洗脚本已在工作区（`report/compute_probe_wording.py`，未提交），需要连同重生成的
`report/figures/gen/probe_wording.json` **一起提交**。

**清洗后的完整数据（`probe_wording.json`）：**

| 位置（占全长 %） | n | 两种问法一致 | 探针答案正确 |
|---|---:|---:|---:|
| 0–5 | 34 | 41.2% | 17.6% |
| 5–10 | 179 | 47.5% | 24.0% |
| 10–15 | 161 | 59.6% | 28.6% |
| 15–20 | 150 | 52.7% | 37.3% |
| 20–30 | 340 | 60.6% | 43.8% |
| 30–40 | 316 | 69.6% | 56.6% |
| 40–50 | 325 | 82.2% | 70.8% |
| 50–60 | 321 | 87.9% | 76.0% |
| 60–70 | 299 | 87.6% | 79.9% |
| 70–85 | 422 | 90.3% | 81.8% |
| 85–100 | 351 | 88.6% | 80.9% |
| **合计** | **2,898** | **76.0%** | — |

**需要改的数字：**

| 位置 | 现值（未清洗） | 应改为（清洗后） |
|---|---|---|
| 摘要 "changes the early answer $57\%$ of the time" | 57% | **约 53%**（前 10%：46.5% 一致 → 53.5% 不一致） |
| `01_introduction.tex:34` "$57\%$ … against $11\%$ near the end" | 57% / 11% | **53%** / 11%（末段 70–100% 为 89.5% 一致 → 10.5% 不一致，"11%" 可保留） |
| `06_mechanism.tex` §4.2 "different answers $57\%$ of the time … only $11\%$" | 同上 | 同上 |
| `fig:wording-taxonomy` (a) caption "$43\%$ in the first tenth … $89\%$" | 43% / 89% | **46%**（前 10% 合计）或直接报最早一档 **41%**（0–5%）；末档 **89%** 不变 |

**图必须重画。** `fig_wording_taxonomy.pdf` 的 (a) 面板现在是 5 个 bin 的旧数据，
要换成清洗后的 11 个 bin；(b) 面板的计数也要换成 **B1** 的裁决记录。
两个面板都改完后跑 `python report/make_v3_figures.py` 重新生成，
并把 PDF 复制到 `paper/figures/gen/`。`fig_taxonomy.pdf`（独立版本，当前未被引用）
若保留也要一并重生成。

清洗后曲线更陡（overall 从 66.7% 升到 76.0%），对论点是**有利**的：早期一致率更低。
另外可以顺带在正文或附录给出这张分箱表 —— 现在正文只有两个孤零零的百分数，没有 $n$。

## B3. 〔重写附录 B 的 taxonomy 小节 + 补数据来源〕

**裁定：** 28 例 AI 辅助标注**全部删除**；过渡语删除；人工标注的数据来源写清楚。

**具体动作：**

1. 删除 `03_false_consensus.tex` 的整个 `\subsection{An error taxonomy}`
   （28 例、A=14/28、D=7/28、E=6/28、"preliminary AI-assisted labeling" 那一整段）。
   它与正文 §4.3 的 134 例结论直接冲突（正文说 A 只占五分之一，它说 A 占一半）。
2. 删除 `03_false_consensus.tex` 结尾的 `\paragraph{Takeaway.}`
   （"The rest of the paper asks whether…"），这是旧正文的过渡语，在附录里读不通。
3. 在 §4.3 补一句数据来源，**只提 scope 和预算，不展开**。
   注意别写成"随机抽样"—— 我查了生成脚本 `analyze.py`，这 134 例是那轮日志里
   false-consensus 案例的**穷举**（cumulative-share-1 错、window-unanimous 错、
   governor-stop 错三个条件的并集）。穷举比抽样更强，照实写就行。一句话即可：

   > We label \emph{all} $134$ false-consensus cases from an exploratory dense-probe
   > pass (\dsseven{}, \textsc{MATH}500, seed $42$, $3{,}072$-token cap).

   预算（3,072）要写出来 —— 这批案例最多只有 24 个探针（≈1,536 token），和正文
   §4.1 的 16K/32K 主轨迹不是同一批数据，不写会被误读。
   Limitations 里已有的 "collected under a short window" 一句可以保留并与此呼应。

## B4. 〔删除〕Limitations 里 "unseen models contribute a single seed"

裁定：删掉。实测 `heldout_test/consensus_heldout_32b_llama_3seed.jsonl.gz`：
32B 和 Llama **都是 seeds 45/46/47**，每模型 9 个环境，与 §3、§5.5 的 "three test seeds each"
一致。这不构成 limitation。该段其余内容（AIME24/AMC23 集合小）可保留。

## B5. 〔同意，改〕§4.4 对 pid 320 的表述过头

> …including a first-probe placeholder held for $27$ consecutive probes---long
> enough to outlast every window we searched.

27 < W=30，所以 W=30 **不会**在这里触发。附录 F 自己的写法是准确的
（"even $W{=}24$, the second-largest we searched, fires here"）。把 §4.4 改成与附录一致。

## B6. 〔同意，改〕附录 F Case 3 的触发位置算错

现写"A three-probe rule fires at token 192 and commits `52`"。
实际探针流（已从 `dense_simple32/probes/problem_240.json` 重放）是
`52@64, 52@128, 104@192, 52@256, 52@320, 52@384, …` —— token 192 处答案是 `104`，
首次三连一致出现在 **token 384**。把 192 改成 384。

（pid 320、pid 253 与 Fig 1 的 pid 68 探针流全部逐个重放核对过，**完全正确**，
包括 pid 68 在 token 256 触发、pid 253 的 D×20 覆盖 384–1600 token。）

## B7. 〔同意，改〕§5.5 对 444 的描述过头

> …the $444$ rules admissible on test alone are exactly the in-sample winners a
> held-out split exists to reject.

实测：test 上通过保守 gate 的共 **444** 条，其中只有 **364** 条属于那 478 条 train-winner
（另 80 条不是）。附录的写法（"$364$ of the $478$ are admissible on test"）是对的。
正文改为不那么绝对的表述，例如 "$444$ rules are admissible on test, $364$ of them the
in-sample winners a held-out split exists to reject"。

## B8. 〔按重算值改〕tab:main / tab:grossnet 的 save≥10% 一行

重算基准（dev，18 环境，budget filter 后）：**macro baseline accuracy = 82.546%**。

| 操作点 | 准确率 | drop | net saving | gross saving |
|---|---:|---:|---:|---:|
| drop$\le1.0\pp$ 中最省的规则 | 81.62% | 0.93pp | **0.21%** | 2.07% |
| save$\ge10\%$ 中最安全的规则 | 79.89% | 2.66pp | **10.94%** | **14.93%** |
| save$\ge20\%$ 中最安全的规则 | 76.38% | 6.17pp | 20.21% | 27.00% |

对照论文：

- `tab:main` 第一行（81.6% / −0.9pp / +0.2%）✓ 无需改。
- `tab:main` 第二行 79.9% / −2.7pp / **+10.7%** → net 应为 **+10.9%**。
- `tab:grossnet` 第一行 14.7% / 10.7% → 应为 **14.9% / 10.9%**。
- `tab:grossnet` 第二行 27.0% / 20.2% ✓ 无需改。
- 正文 §5.6 "a $4$--$7\pp$ gap between gross and net" ✓（实际 4.0 和 6.8pp）。

## B9. 〔同意，改〕§5.3 的符号

> …at a stricter threshold it is accuracy-neutral ($-0.06\pp$) while still saving $20.8\%$

$\tau=0.9999$ 的 `accuracy_drop_pp` $=-0.06$，即准确率**上升** 0.06pp。
`tab:deer` 的列名是 "Total drop (pp)"，写 $-0.06$ 正确；但 `tab:main` 的列名是 $\Delta$acc，
正文这句也在 $\Delta$acc 语境下，应写 $+0.06\pp$ 或改成 "slightly above baseline"。

## B10. 〔加一个括号即可〕§4.1 用到了 test 种子

§4.1 的 1,500 条轨迹 = 500 题 × 3 seeds，其中 test 划分的题目来自确认种子 45/46/47。
现在只有附录 B 的脚注声明了这是 descriptive-only。在 §4.1 加个括号带过即可，例如
"(all $500$ problems across three seeds; descriptive only---it selects nothing and does
not touch the test commitment)"。

## B11. 〔保留范围，但要诚实声明〕§4.2 / §4.3 的单环境 scope

§4.2（two-wording）和 §4.3（134 例 taxonomy）都只来自
**DeepSeek-7B × MATH500 × seed 42 单一环境**的探索性数据，而 §4.4（harm:rescue）是 18 环境的。
`main` 分支上原有的 scope caveat 在 merge 进 v4 时丢了。

裁定：范围小可以接受（两者都是现象性发现），但**必须诚实声明**。
在 §4.2 和 §4.3 各加一句，例如 "on a single environment (\dsseven{} $\times$
\textsc{MATH}500, seed $42$); we report it as a supporting observation rather than a
headline result"。摘要引用这两个数字时相应弱化。

## B12. 〔不改〕placeholder 机制的语气

裁定：有人工标注支撑，维持现有表述。（A7 的措辞替换仍然要做。）

## B13. 〔保留〕§4.5 独立性一节

裁定：保留。它的作用是解释 **self-consensus 为什么没有准确率兜底机制** ——
self-consistency 的多数投票能吸收单条路径的错误，是因为路径独立采样；单轨迹上的
嵌套观测没有这个机制，所以错误停止无人纠正，这正是大量准确率损失的成因之一。
建议把这层因果在节首点明（现在要读到结尾才明白），并按 **A12** 修掉
"every probe reads the same prefix"。

---

## 已逐项验证、无需改动的数字

以下全部从 committed banks 重算并吻合：

- **harm:rescue**：45.1:1 → 2.0:1；stops 668 → 121（共 684 题）；net saving 92.3% → 7.9%；
  DEER 三个操作点 3.0 / 2.4 / 3.5，saving 28.2 / 29.6 / 31.9%。
- **Sweep**：40 条规则 drop $\le1.0\pp$（最高省 0.21%）；saving$\ge$10/20/30% 的最小 drop
  = 2.66 / 6.17 / 11.76pp；64.9% 下降 / 10.5% 上升 / 均值 13.0pp；126,720 行；
  $W{=}1$ 最小 drop 22.25pp、最大 saving 98.1%；$W{=}30$ 为 0.81pp / 38.8%。
- **泛化**：dev↔test $r = 0.9808$；train-winner 478；dev 通过 0；test 通过 444；两者皆通过 0；
  478 条的 median drop dev 4.50pp / test 0.62pp；32B $r=0.970$、gate 0/4/6、drop$\le$1.0pp
  下最高省 0.63%；Llama $r=0.941$、0/0/0、9.33%；DEER heldout −0.24pp@32.4% 与 0.67pp@26.7%。
- **tab:deer**：14 个阈值全部逐行吻合。
- **tab:baselines**：full-gen 85.4 / 79.8；CertaIndex 15.33/−70.11/90.10/99.78 与
  23.87/−55.89/76.68/98.67；DEER 86.22/+0.78/16.29/41.35 与 74.93/−4.83/20.16/56.07。
- **§4.1 各数**：97.8 / 90.4 / 89.1 / 84.2 / 91.0 / 71.6 / 1477 / 50.5 / 90.7 / 40.2
  （数值本身对，但含义与取舍见 **A6**）。
- **consensus position**：679/684 形成共识，338 条（约一半）在前 10%，27.5% vs 85.2%。
- **案例**：Fig 1 的 pid 68、附录 F 的 pid 320 与 pid 253 探针流全部精确吻合
  （pid 240 的触发位置除外，见 **B6**）。
- **0.65pp 读法效应 vs 9.15pp 时点效应**：与 `results/probe_paired_2x2/report.md` 一致。
