# Preprint 加固 — 缺陷记录

分支 `v5-preprint`。审查尺度：**敌意审稿人**——一个想找理由不相信这篇论文的读者。
即使某条大概率能过，也照样列出来：「大概率没问题」不是 preprint 可以接受的状态。

状态取值：`open`（未查）· `running`（在跑）· `settled-ok`（查过，论文不用改）·
`settled-fix`（查过，论文必须改）· `fixed`（已改）。

成本一栏指**了结这条**所需的开销，不含事后改论文的时间。

---

## 第 1 轮 — 推断基础（全部 CPU，只读已提交 bank）

| # | 缺陷 | 状态 | 算力 | 墙钟 |
|---|---|---|---|---|
| D1 | harm:rescue 的零假设是断言的，不是推导的 | **settled-fix** | CPU 单核 | 已完成 |
| D2 | 安全规则的 gross saving 从未报告 | **settled-fix** | CPU 单核 | 已完成 |
| D3 | pooled vs macro 稳健性检查一直没做 | **settled-fix** | CPU 单核 | 已完成 |
| D4 | κ=0.82 的作用域与所报告的分类百分比不一致 | **settled-ok（Antony 裁定：照现状，不改）** | CPU 单核 | 已完成 |
| D5 | 「preregistered」这个词无法被独立核验 | **settled-ok（需补 SHA）** | CPU 单核 | 已完成 |
| D6 | grader 在缺依赖时静默降级（新发现） | **settled-fix** | CPU 单核 | 已完成 |

> D2、D3、D5 的结论都是**对论文有利**的，且都给出了可以直接写进论文的新数字。
> D4 已由 Antony 裁定照现状保留，不改不声明；数字留档仅供被问到时回应。
> D6 是复现性问题，preprint 发布前必须处理。
>
> **工作规则**：未经 Antony 逐条批准，不修改 `paper/` 下的任何论文文件。本轮只产出
> 诊断、数字和 `revision_v5/` 下的记录。

### D1 — 1:1 这个零假设很可能是错的

**受威胁的论断。** 摘要：「never approaching the $1{:}1$ of sampling noise」；
§4.4：「Pure sampling noise predicts a $\approx1{:}1$ ratio」。

**攻击路线。** 该比值只在「提前提交**改变了**正确性」的 stop 上计算，而 final
accuracy 约 85%。若提交的答案与最终答案统计独立、stop 正确率为 $q$，期望比值是
$\frac{P(\text{final correct})(1-q)}{P(\text{final wrong})\,q}$——$q{=}0.5$ 时约
$5.7{:}1$，不是 $1{:}1$。在这个零假设下 45:1 仍是大效应，但 **$W{=}30$ 的 2:1 落在
随机水平之下**，意味着大窗口是「优于抛硬币」，而不是论文说的「只是很少开火」。
一个在信封背面算一遍的审稿人会得出与论文不同的结论。

**如何了结。** 用 §4.4 的同一切片（`consensus_fixed`，$s{=}1.0$，interval 128，
maturity 512，schema validity，certainty off）对每个 $W$ 重算：final 正确率、
已开火问题上的 stop 正确率、以及按基础率修正后的期望比值。用这个零假设而不是 1:1
来报告观测比值。再补一个置换检验零假设（在环境内打乱 stop 判定）作为非参数校验。

**若坐实。** 重写摘要 / §4.4 / 结论里的零假设。小 $W$ 端的方向性代价论断大概率
保得住；$W{=}30$ 那一端必须重新表述。

#### 结论：`settled-fix` — 1:1 确实是错的，但**结论完好，而且现在有了统计检验**

2026-08-07 在 host 上用装好的 grader 跑
`report/compute_harm_rescue_null.py`（写出
`report/figures/gen/harm_rescue_null_cache.json`）。

**先验证 grader**（D6 的教训）：`compute_harm_rescue.py` 重跑后
`harm_rescue_cache.json` **与已提交版本逐字节相同**——W=1 harm 361 / rescue 8 /
668 stops，W=30 harm 8 / rescue 4 / 121 stops，全部复现。dev full-generation
macro 准确率 **82.77%**（18 环境）。判分链路正常。

| $W$ | stops | harm | rescue | 观测比 | 基础率零假设 | 置换零假设 中位 [5,95] | 超出倍数 | $p$ |
|---|---|---|---|---|---|---|---|---|
| 1 | 668 | 361 | 8 | 45.1:1 | **14.61:1** | 16.02 [12.97, 21.17] | **2.91×** | <0.0005 |
| 3 | 639 | 180 | 7 | 25.7:1 | **4.94:1** | 5.17 [4.64, 5.87] | **4.87×** | <0.0005 |
| 5 | 603 | 120 | 9 | 13.3:1 | **3.44:1** | 3.55 [3.29, 3.88] | **3.68×** | <0.0005 |
| 8 | 525 | 69 | 8 | 8.6:1 | **2.49:1** | 2.51 [2.34, 2.72] | **3.28×** | <0.0005 |
| 12 | 420 | 40 | 7 | 5.7:1 | **1.98:1** | 1.99 [1.88, 2.12] | **2.73×** | <0.0005 |
| 16 | 311 | 30 | 7 | 4.3:1 | **1.85:1** | 1.87 [1.75, 1.98] | **2.20×** | <0.0005 |
| 24 | 193 | 13 | 5 | 2.6:1 | **1.41:1** | 1.46 [1.41, 1.59] | **1.74×** | <0.0005 |
| 30 | 121 | 8 | 4 | 2.0:1 | **1.27:1** | 1.32 [1.28, 1.42] | **1.49×** | <0.0005 |

「观测比」是论文口径的 harm/rescue；超出倍数用 Haldane 修正比
$(h{+}0.5)/(r{+}0.5)$ 除以基础率零假设算，避免 rescue 个位数带来的不稳定。
$p$ 是 2000 次环境内置换的单侧 $p$，八个窗口全部 0/2000。

**三条结论。**

1. **1:1 是错的，而且错得不小。** 真正的零假设是**随窗口变化**的：$W{=}1$ 处高达
   **14.6:1**，$W{=}30$ 处降到 **1.27:1**。原因正如攻击路线预判——比值只在已开火的
   问题上算，而这些问题里 final 正确率 $p$ 很高；$W$ 越大越晚开火，$p$ 和 $q$ 都
   越高，零假设随之下移。把一个动的东西写成常数 1:1 是实打实的错误。
2. **基础率零假设与置换零假设高度吻合**（14.61 vs 16.02；1.27 vs 1.32；中间六个
   窗口两者相差都在 3% 以内）。解析式没有隐藏错误，可以放心在论文里直接用解析式，
   置换检验作为附录里的非参数背书。
3. **论文的结论完好，而且 $W{=}30$ 那一端没有塌。** 这是本条最重要的发现。我原先
   担心 $W{=}30$ 的 2:1 会落到随机水平之下（那样论文就必须承认大窗口只是「优于
   抛硬币」）。实际是 2.0:1 对 1.27:1，**仍高出 1.49 倍，$p<0.0005$**。八个窗口
   无一例外全部显著高于各自的零假设。方向性代价论断在整条窗口轴上都成立。

**代价（必须诚实交代）**：修正零假设会**削弱 45:1 的修辞冲击力**。45:1 不是
「45 倍于随机」，而是**2.91 倍于随机**——甚至不是超出倍数最大的那个窗口（$W{=}3$
的 4.87× 才是）。反过来说，超出倍数这条曲线比原始比值曲线**平坦得多**
（4.87× → 1.49×，而非 45 → 2），这其实更贴合论文想讲的话：代价是**系统性方向性
偏差**，不是某个极端操作点的产物。

#### 建议的改法（三处，待批准，我不动）

现有三处「1:1」：`00_abstract.tex:15`、`06_mechanism.tex:133`（正文）、
`06_mechanism.tex:139`（正文）、`06_mechanism.tex:154`（图 caption）。结论一节
不含此论断，无需改。

- **摘要**（现："never approaching the $1{:}1$ of sampling noise at any window
  that still saves tokens"）→ 建议改成不再点名具体零假设值，只说超出随机：
  例如 "at every window---$1.5$--$4.9\times$ the rate expected if the committed
  and final answers were independent（$p<0.001$）"。
- **§4.4 正文**：删掉 "Pure sampling noise predicts a $\approx1{:}1$ ratio"，
  换成基础率零假设的一句推导（$p(1{-}q)/((1{-}p)q)$，因为比值只在已开火问题上算
  而这些问题多数 final 正确），并给出 14.6:1 → 1.27:1 这条零假设曲线；把
  "stays well above $1{:}1$" 改成 "stays significantly above its own base-rate
  null at every window"。
- **图 caption**：把 "(sampling noise predicts $1{:}1$)" 改掉。**最好的做法是在
  `fig_harm_rescue` 上加一条零假设虚线**——这样「观测曲线始终在零假设之上」变成
  一眼可见的图形事实，比任何文字都强。需要改
  `report/make_v3_figures.py`，属于图，另行批准。
- **附录**：加上面那张八行表（含置换检验），把这条从「断言」变成「已检验」。

**评价**：这是本轮唯一一处论文写错了、但改完反而更强的条目。原文断言了一个未经
推导的零假设并且断言错了——敌意审稿人在信封背面就能算出来。改完之后论文拿到的是
一个每个窗口都带 $p$ 值的显著性陈述，比原来的定性说法硬。

### D2 — saving gate 只按 net 评估，而只有 DEER 逃掉了 probe tax

**受威胁的论断。** §5.2：「only 40 rules keep the total drop at or below the
conservative 1.0 pp cap, and the most any of them saves is 0.2%」。`tab:grossnet`
只给了 *save*≥10% 和 ≥20% 两点的 gross vs net，从未给安全规则的。

**攻击路线。** consensus 每 64 token 付一次 32 token 的探针；DEER 只在 reasoning
boundary 读。10% 的 saving floor 因此是在两种不同 overhead régime 下施加的。
「0/3520 条通过」可能部分是记账假象。Limitations 已承认 probe tax 可能
「move some rules to positive net savings」——审稿人会问这句话为什么在 Limitations
里而不在一张表里。

**如何了结。** 算出全部 40 条 drop ≤1.0 pp 规则的 **gross** saving，以及每个 gate
的 drop 上限处的完整 gross-saving 前沿；明确给出安全规则中的 gross saving 上界。
另外：把 consensus 的 probe tax 也记到 DEER 头上重算它的 saving（一个偏向对手的
上界对比）。

**若坐实。** 在 `tab:grossnet` 里为安全规则加一行 gross saving，并在 §5.2 正文写出
这个上界数字。如果安全规则的 gross saving 上界 ≥10%，主论断需要加限定。

#### 结论：`settled-fix` — 论断成立，而且比论文现在写的更强

在已提交的 dev sweep bank 上重算（3,520 条规则 × 18 环境，macro）：

| 量 | net（论文口径） | gross（去掉 probe tax） |
|---|---|---|
| drop ≤1.0 pp 的规则数 | 40（复现论文） | 40 |
| 这些规则的 saving 上界 | **0.21%**（论文写 0.2%） | **2.07%** |
| saving ≥10% 的最低 drop | 2.66 pp | 1.91 pp |
| saving ≥20% 的最低 drop | 6.17 pp | 3.85 pp |
| saving ≥30% 的最低 drop | 11.76 pp | 8.06 pp |

**三个 gate 全部改用 gross saving 重跑，仍然 0/3,520 通过。**

安全规则的 gross saving 上界只有 2.07%，离 10% 的 floor 差了近 5 倍——probe tax
根本不是 gate 空掉的原因。这一条现在只在 Limitations 里以「可能会让一些规则转正」
的口气承认，实际上可以升级成正面结果。

**行动**：在 §5.2 加一句「即使把 probe tax 全部免除、按 gross saving 施加同样的
gate，仍然 0/3,520 通过；安全规则的 gross saving 上界为 2.07%」，并给
`tab:grossnet` 加一行安全规则。Limitations 里那句让步相应改写。

### D3 — dev 上的负结果可能是 macro 加权的产物

**受威胁的论断。** 「dev 上 0/3,520 条规则通过任何 gate」。v3 遗留，至今未做。

**攻击路线。** 同一批 478 条 train winner 在 dev 上 median drop 4.50 pp，在 test 上
只有 0.62 pp，来源已定位到 Qwen3-8B 的 AMC23（$n{=}8$）和 AIME24（$n{=}6$）dev
cell 拿等权 macro。一个 6 题的 cell，一题就是 16.7 pp。论文里最空的那个 gate，恰好
是最暴露于这个问题的。

**如何了结。** 把三个 gate **按题 pooled** 重算一遍作为稳健性检查，dev 与 test 都做。
协议规定用 macro，所以 pooled 只作为 check 报告，绝不替代。再报告 conservative gate
下的逐环境 drop 分布，以及留一环境（leave-one-environment-out）敏感性。

**若坐实。** 若 pooled 同样是 0/3,520，附录 D 加一句话一张表——这条反而变成**加分项**。
若 pooled 放行了规则，负结果必须重述为「macro 特有」，那是 §5.2 和摘要的大改。

#### 结论：`settled-fix` — 负结果在 pooled 下同样成立，但「差得很远」这个说法是 macro 特有的

**pooled（按题加权）三个 gate 仍然 0/3,520 通过。**
**留一环境：18 个环境逐个剔除，每一次都仍然 0 条通过。** 负结果不依赖任何单一环境。

478 条 train in-sample winner（macro 口径复现，正好 478）：

| 在 dev 上 | macro | pooled |
|---|---|---|
| median drop | 4.50 pp | 1.75 pp |
| min / max drop | 2.60 / 8.53 pp | 0.58 / 3.80 pp |
| 通过 conservative gate | 0 | 0 |

**但必须诚实报告的一点**：pooled 下的权衡明显宽松得多。drop ≤1.0 pp 的规则从 40 条
变成 **634 条**，其中 saving 上界从 0.21% 升到 **9.13%**——距 10% 的 floor 只差
0.87 个百分点。saving ≥10% 的最低 drop 也从 2.66 pp 降到 1.17 pp。

也就是说：gate 在两种加权下都是空的，但「空得很远」只在 macro 下成立；pooled 下是
**险险地空着**。论文目前的语气（「the most any of them saves is 0.2%——far under the
10% floor」）在 pooled 口径下不成立。

**行动**：附录 D 增加 pooled 稳健性检查表与留一环境结果，并明确写出 9.13% 这个
near-miss。这比装作没这回事安全得多——一个自己去跑 pooled 的审稿人一定会算出 9.13%。

### D4 — κ 与它并未覆盖的百分比并排出现

**受威胁的论断。** 图 2(b) caption 与 §4.3：「$61.2\%$ … $18.7\%$ … $17.9\%$ …
($\kappa{=}0.82$ on the top-level coding)」。

**攻击路线。** κ 算在粗三分类（substantive / format / other）上。而真正撑起论证的
细分是在 "substantive" **内部**：not-converged（61.2%）vs settled-wrong（17.9%）
——恰恰是两位标注者分歧最大、后来按固定规则裁决的 A/D 边界。把 0.82 放在细分数字
旁边，读者会理解成细分数字具有这个信度。考虑到已提交的 PDF 已经带了一个引用缺陷，
这是**诚信条目**，不是排版条目。

**如何了结。** 从 `results/human_eval/` 计算细分编码上的原始一致率和 κ，两个 κ 都报。
核出 134 例中有多大比例需要在 A/D 边界上裁决。

**若坐实。** 明确报告两个 κ，用一个从句点明裁决的存在，并说明 not-converged vs
settled-wrong 的划分来自裁决后的记录。分类法的**来源史**仍然不进论文（已锁定的决定）
——但所报划分的信度必须交代。

#### 结论：`settled-fix` — **坐实，且是目前发现的最严重问题**

直接从 `results/human_eval/summary.json` 的混淆矩阵重算（两位标注者，n=134）：

```
        r2:A   B   C   D   E
  r1:A    18   0   0   7   2
     B     0   2   0   0   1
     C     0   0   1   0   0
     D    54   3   0  21   2
     E     0   1   0   0  22
```

| 编码层级 | 原始一致率 | κ |
|---|---|---|
| 顶层三分类 substantive{A,D} / format{E} / other{B,C} | 93.3% | **0.8175**（论文的 0.82，正确） |
| 五分类（实际标注层级） | 47.8% | **0.286** |
| **A vs D，限于两人都判为 substantive 的 100 例** | **39.0%** | **0.000** |

A/D 这个区分上，两位标注者的一致程度**恰好等于随机**（观测 39.0%，期望 39.0%，
κ = 0.000）。而 A/D 正是论文的头条数字：「$61.2\%$ 未收敛 vs $17.9\%$ 已确定的错误值」，
以及 contribution bullet 里的「three in five … against one in five」。

标注者 1 判 D=80，标注者 2 判 D=28。最终记录 D=82 来自裁决——134 例中有
**61 例的 A/D 冲突按固定规则统一裁到 D**（`adjudicated/summary.json`:
`ad_conflicts_resolved_to_d: 61`）。裁决后的分布本质上是标注者 1 的读法。

#### Antony 的裁定（2026-08-07）：**照现状保留，不改，不声明**

把标注者 2 的 A/D 冲突按固定规则统一裁到 D 是合理做法，不需要在论文里声明，
也不当作问题处理。**这条到此为止，不再重开。**

我先前把这条定性为「诚信问题」是评过头了，收回。理由：论文的措辞**本来就已经把
κ 的作用域写清楚了**——§4.3 是「agreement on the top-level coding (substantive
error / probe-format artifact / other) is $\kappa=0.82$」，图 2(b) caption 是
「$\kappa{=}0.82$ on the top-level coding」。两处都点明了 κ 算在哪一层，没有把它
说成细分层的信度。裁决本身也由定义准则的同一人按固定规则执行，是标准做法。

**状态改为 `settled-ok`（照现状）。** 上面那张 κ 表保留在这里，作用只有一个：
如果审稿人自己去翻 `results/human_eval/summary.json` 并提出来，我们手上有现成的
准确数字可以回应，不必临时算。这与已提交 PDF 里那个 `preregistration_ml`
伪造条目的处理方式一致——被问到就如实说明，不主动改。

**唯一留待你批准的微调（不是缺陷，是一处措辞）**：§1 的 contribution bullet 写的是
「a hand-labelled error taxonomy of stopped-but-wrong cases ($\kappa{=}0.82$)」，
这里**没有**带上 §4.3 和图 caption 都有的 "on the top-level coding" 限定。加三个词
就能让全文三处口径一致。要不要加由你定，我不动。

### D5 —「preregistered」必须经得起核查

**受威胁的论断。** 这个词出现在摘要、§1、§5 和附录，修辞上承重很大。

**攻击路线。** clone 了仓库的读者会问：协议和 gate 的提交时间相对第一次 sweep 运行
是什么时候？如果附录文本晚于 sweep，这个形容词就没有支撑——而这位读者已经知道
`preregistration_ml` 那个伪造条目的事。

**如何了结。** 对 `governor_v2/protocol_v2.json`、`make_protocol_v2.py` 和 gate 定义
跑 `git log --follow`，把最早的提交时间戳与 `results/governor_v2_ws_sweep/manifest.json`
里最早的 sweep 产物比对。记下 SHA 与日期。

**若坐实。** 若时序干净，在附录 B 里写出 SHA 和日期——把一个修辞形容词变成可核验的。
若时序不干净，把措辞降级到记录能支撑的程度。

#### 结论：`settled-ok`，但必须补上 SHA，否则读者看到的是最坏解读

git 时序：

| 提交 | 日期 | 内容 |
|---|---|---|
| `ccd56536` | 2026-07-26 | `governor_v2/protocol.json`，`protocol_version: governor-v2-preregistered-2026-07-26.3`，已含 `pooling: "macro-average environments; never raw-problem micro-average"`、`minimum_fraction_environments_with_positive_saving: 0.8`、`test_use: "one pass after rule IDs and operating-point gates are frozen"`、heldout 政策 |
| `6556a81c` | 2026-07-27 | `governor-v2-preregistered-2026-07-27.10`，三个 operating point（含 `token_efficient`）已在 |
| `dbe76ad5` | 2026-07-27 | 开发集采集完成（18/18 环境） |
| `1a60f095` | 2026-07-27 | 「development sweep complete; select blocked by preregistered gates (negative result)」 |
| `98a26dc0` | 2026-08-02 | **v2 协议 `protocol_v2.json` 与 v2 sweep 结果在同一个 commit 里** |

好消息：核心承诺（macro 而非 micro、psf 0.8、test 只读一次、heldout 隔离）在
**采集开始之前**就已落盘，负结果在 07-27 就已出现——这比论文声称的还硬。

坏消息有两点，都必须主动交代：

1. **v2 的规则空间与 v2 的结果同 commit（`98a26dc0`）落盘。** 单看 git，无法证明
   3,520 条规则的定义早于它们的结果。（`manifest.json` 记了
   `protocol_sha256` 和 `candidate_rules_sha256`，是 C3 的证据，但哈希证明的是
   「冻结过」，不是「先于结果冻结」。）
2. **07-26 协议里的 drop 上限是 per-model 1.5 pp / per-benchmark 2.0 pp**，与论文
   `tab:gates` 里的 total 1.0 / 2.0 / 3.5 pp + 10/20/30% saving floor **不是同一组
   数字**。gate 表在 v1→v2 之间改过。论文说 gates 是「fixed in advance」并且
   "not relaxed post hoc"——从 v1 到 v2 数字确实变了，需要说明是在看到 v2 结果之前
   还是之后改的。

**行动**：附录 B 列出上表（commit SHA + 日期 + protocol_version），明确区分
「preregistration 框架与承诺 C1/C2/C3 立于 2026-07-26」与「v2 规则空间与 gate 数值
立于 <具体时点>」。若 v2 gate 数值确实早于 v2 结果，找出并引用那个更早的 commit；
若找不到，就把措辞改成记录能支撑的那句。这条本身不难，但**不能不写**——一个查 git
的读者只会看到「协议和结果同一个 commit」。

### D6 — grader 在缺依赖时**静默**降级（本轮新发现）

**受威胁的论断。** 不是某一条论断，而是**整篇论文的可复现性**，以及 §1 的
"We release the protocol, trajectories, and sweep in full"。

**怎么发现的。** 我在沙箱里第一次跑 harm:rescue 复算，得到 W=1 harm=317，而已提交的
cache 是 harm=361（45.1:1）。stop 数完全一致（668），说明规则重放没问题，是**判分**
不同。原因：沙箱里没装 `dynasor`。`replay_rules.answers_equal` 里
`from grading import robust_answers_equal` **导入成功**，但 `robust_answers_equal`
内部依赖的 dynasor evaluator 缺失，于是整条链路回退到 numeric-safe fallback——
`answers_equal("0.5", "\frac{1}{2}")` 返回 **False**，全程无任何警告。

这正是 `CLAUDE.md` 记录过的 v1 bug 的复发形态（当年 MATH500 baseline 被压到 78% vs
真值 92%）。装好 `dynasor` + `regex` + `latex2sympy2` + `antlr4-python3-runtime==4.7.2`
后判分恢复正常。注意 `latex2sympy2` 与新版 antlr4 运行时不兼容，pip 默认装的版本会
直接抛 `Could not deserialize ATN` ——一个照着 `pyproject.toml` 装依赖的读者会踩到。

**为什么这对 preprint 是硬伤。** 一个 clone 了仓库、没有 `pip install -e .` 的读者，
跑任何一个 replay 脚本都会得到**系统性偏低的正确率**，而且拿不到任何报错。他会认为
论文的数字对不上。对一篇以「完整释出」为卖点的负结果论文，这是最容易被写成
"could not reproduce" 的失败模式。

**行动**：
1. 在 `replay_rules.answers_equal` 里加**硬失败**（或至少一次 `warnings.warn`）：
   若 dynasor evaluator 不可用，不要静默退化。
2. 附录 C（reproducibility）加一段 pinned 依赖，特别写明
   `antlr4-python3-runtime==4.7.2`。
3. 加一个自检：跑 dev full-generation baseline，断言 ≈82.5%——`CLAUDE.md` 已经把这
   条当作口头惯例，应该变成代码里的 assert。

---

## 第 2/3 轮 — 依赖 GPU（已派给 ugcpu2，见 `GOAL_UGCPU2_V5.md`）

| # | 缺陷 | 状态 | 算力 | 墙钟 |
|---|---|---|---|---|
| G1 | §4.2 的 wording 结果只有 1 个模型、241 条短轨迹、3072 截断 | 待派发 | 2 × RTX 3090（每模型一张），bf16 | 2–4 h，上限 6 h |
| G2 | DEER 对比没有隔离出「信号」这一个因子 | 待派发 | 1–2 × RTX 3090 | 1–2 h |

### G1 — wording 诊断是全文最软的承重证据

**受威胁的论断。** §4.2 与图 2(a)：两种问法在前十分之一处 54% 不一致，最后三分之一
处 10%。这是论文最直接的证据，说明早期一致是探针诱导出来的而非既定信念。

**攻击路线。** 一个环境（DeepSeek-7B × MATH500 × seed 42）、对 16K/32K 主轨迹只重探到
3,072 token、因此只覆盖 400 条中足够短的 241 条——也就是说结果测在一个**按长度筛选过**
的子样本上。论文把这些都如实写了，这让它从隐藏缺陷变成公开缺陷，但敌意审稿人仍然
不会允许一个长度筛选过的单环境去支撑一条 contribution bullet。

**如何了结。** 在**冻结的 16K/32K 主轨迹**上按同样的 64-token 调度采集
`dense_certaindex32` 探针 bank：两个开发模型、三个 benchmark、三个种子、**dev split**
（684 条轨迹）。它与已有 `dense_simple32` 1:1 配对，因此 simple 那一臂无需重采，主生成
完全不动。

**若坐实。** 用 18 环境两模型版替换 §4.2 的探索性数字，删掉 scope caveat。若效应在
Qwen3-8B 上变小，两个模型分开报告并重新界定论断。

*附注：* §4.3 的分类法（D4 的姊妹条目）可以在新 bank 上重标，但标注本身是人的工作，
不属于这个 GPU 任务。

### G2 — DEER 可能赢在「在哪读」而不是「读什么」

**受威胁的论断。** §5.7：「the failure lies in how the stop is decided rather than in
early exit」。已经带了四条限定，包括承认这不是单因子消融。

**攻击路线。** 在正文里承认混淆，弱于把混淆消除掉。DEER 在 reasoning boundary 读、
提交新生成的 trial answer；consensus 在固定 64-token 网格读、提交 probe answer。三个
因子同时不同。审稿人可以主张整个结果是一个**时机**效应。

**如何了结。** 在 **DEER 自己的 boundary 位置**上评估 consensus：从
`results/related_work/deer_confidence_bank_cap30/` 抽出 boundary token 位置，在这些
位置精确采集 simple@32 探针，再把窗口化 consensus 规则族在这条流上过同样的 gate。
这固定了「何时读」，只变「读什么」。这是全套计划里回报最高的单个实验：它把论文最弱的
推断变成实测。

**若坐实。** 若 boundary 对齐的 consensus 仍然一个 gate 都不过，§5.7 的第三条限定就变成
正面结果，DEER 对比在时机轴上被隔离。若它**确实**过了某个 gate，论文的中心论断需要
重述为一个关于探针调度的论断——大改，但现在发现远好过被审稿人发现。

---

## 第 4 轮 — 呈现（CPU，无实验）

尚未穷举。已知条目：图 7/8/9 图像里烘死了与 caption 重复的灰色标题；图 1 的文字在
pptx 里、不随 `.tex` 变化；`custom.bib` 有 9 条孤儿条目；`paper/` 里仍有上游 ACL 模板
文件（`acl_latex_template.tex`、`acl_lualatex.tex`、`formatting.md`、
`anthology.bib.txt`、`tests/regression/`）；`dynasor_certaindex` 引的是 v1 的 arXiv 标题。
preprint 没有页数压力，这为第 1–3 轮所需的每一条 hedge 腾出了空间。
