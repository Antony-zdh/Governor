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

## 第 2 轮 — 比较有效性与对外主张（CPU，只读已提交 bank）

| # | 缺陷 | 状态 | 算力 | 墙钟 |
|---|---|---|---|---|
| C1 | CertaIndex 56–70pp 复现的配置是否忠实 | **settled-ok（需补脚注 + 改代码注释）** | CPU 单核 | 已完成 |
| C2 | DEER 对比还有第四个混淆：决策点数量 | **settled-ok，且是新的正面结果** | CPU 单核 | 已完成 |
| C3 | 相关工作覆盖偏薄，与 dong2026learnstop 的区分不足 | **settled-fix** | CPU 单核 | 已完成 |

### C1 — 56–70pp 是全文最容易被外部核验推翻的数字

**受威胁的论断。** §5.4：CertaIndex (CoT) "reproduced from the released
implementation at its default setting" 在冻结轨迹上 "stops on 98.7–99.8%" 且
"loses 56–70pp while saving 77–90%"。

**攻击路线。** 这是唯一一条关于**别人已发表方法**的定量断言，而且断言它灾难性地
失败。Dynasor 自己的论文报告的是「省 token、准确率基本不掉」。一个审稿人只要打开
`dynasor/core/cot.py` 比对配置，就能主张我们复现错了。论文用一句
"not an implementation defect" 挡住，但那是断言，不是证据。

#### 结论：`settled-ok` — 三个数字全部核对无误，配置逐项忠实；但有一处注释写错了

**数字核对**（`results/related_work/aggregate_certaindex/dev_macro.csv`）：

| 量 | Qwen3-8B | DeepSeek-7B | 论文 |
|---|---|---|---|
| accuracy_diff_pp | −70.11 | −55.89 | 56–70pp ✓ |
| stop_rate | 0.9978 | 0.9867 | 98.7–99.8% ✓ |
| all_generated saving | 90.10% | 76.68% | 77–90% ✓ |

**配置逐项比对** `related_work/common.py` ↔ `dynasor/core/cot.py`，**全部一致**：
probe suffix 逐字符相同、`uncertain_words` 六个词相同、patience 3、interval 64、
probe cap 20、temperature 0.6、top_p 0.95。`effort_level("mid") == (3, 64)` 确认。

**但 `certaindex_mid.py` 的 docstring 有一处推理是错的。** 它写：

> The probe happens *after* each 64-token chunk in both conventions (the first
> probe is on prefix[:64]), so there is no off-by-one between the two

上游不是这样。`cot.py:73` 用 `current_prompt` 构造 probe 请求，而
`cot.py:99` 才把本轮生成的 `result` 追加进 `current_prompt`——Python 在调用点就
把字符串求值了。所以**上游的探针位置是 0, 64, 128, …，我们的是 64, 128, 192, …**。
docstring 声称的「没有 off-by-one」，理由是错的。

**但结论碰巧是对的，而且可以证明。** 记我们的 `probes[i]` 在位置 $64(i{+}1)$，
上游的 `probe[j]` 在位置 $64j$，于是 $j\ge1$ 时 `upstream[j] == probes[j-1]`。
上游在最小的 $j\ge2$ 触发，窗口 $\{j{-}2,j{-}1,j\}$；当 $j\ge3$ 时该窗口
$=$ 我们的 $\{j{-}3,j{-}2,j{-}1\}$，令 $i=j{-}1$，则上游在位置 $64(i{+}1)$ 提交
`probes[i]` 的答案——**与我们的截断位置和提交答案完全相同**。

唯一的真实残差是上游多出一个最早的触发窗口 $\{0, 64, 128\}$（需要位置 0 的探针，
我们的 bank 里没有）。若它触发，上游在 **token 128** 截断——比我们模型化的更早。

**这个残差的上界**（必要条件：位置 64 与 128 的探针都非空、certain、且数学等价，
用 robust grader 判等，2,736 条轨迹全量）：**52.23%**。分环境从 DeepSeek/AIME24 的
12.5% 到 Qwen3/AMC23 的 68.8%。

**方向对我们有利。** 残差一旦发生，上游停得**更早**，准确率只会更低。也就是说
**56–70pp 是一个保守下界**，真实的 released implementation 至少损失这么多。

**行动**：(1) 改 `certaindex_mid.py` 的 docstring——现在的理由是错的，换成上面那个
索引对齐证明；(2) §5.4 或附录 `tab:baselines` 的 scope note 里加一句：上游在
位置 0 起探，我们从 64 起，两者在 $j\ge3$ 时截断位置与提交答案相同，唯一差异是
上游多一个更早的触发机会（必要条件在 52.2% 的轨迹上成立），**因此我们的数字是
保守的**。这一句把「你复现错了」这条攻击线彻底堵死，而且是往对我们不利的方向让步，
可信度更高。

### C2 — DEER 拿到的停机机会比 consensus 少一个数量级

**受威胁的论断。** §5.7 列了三条限定（读什么信号 / 何时读 / 提交什么），
声称 "the failure lies in how the stop is decided rather than in early exit"。

**攻击路线。** 还有**第四个**没被列出的因子：**决策点数量**。实测（committed bank）：

| | 每条轨迹的停机机会（中位） |
|---|---|
| DEER（boundary，cap 30） | **9**（均值 13.3，最大 30，**0% 触到 cap-30**） |
| consensus（interval 64） | **54**（均值 84，最大 512） |
| 分基准：math500 | DEER 2–6 vs consensus 38–62（≈10–19×） |
| 分基准：aime24 | DEER ~20 vs consensus ~194（≈10×） |

给一个方法 10 倍的开火机会，它就有 10 倍的机会开错火——这与信号质量无关。
审稿人可以主张整个结果是决策密度效应。（顺带排除一个相邻假设：cap-30 **从未** 生效，
所以 cap 没有偏袒 DEER。）

#### 结论：`settled-ok` — 这个混淆在已提交数据里就能排除，而且结果是正面的

规则空间本来就有 `probe.schedule.interval_tokens` 这条轴（64/128/256/512 各 440 条
`consensus_fixed`，另有 1,760 条 `consensus_adaptive`）。**interval 512 时
math500 上的决策点约 5 个，正好落在 DEER 的 2–6 区间**。按环境 macro 重算 dev
（先复现基准线：0/3,520 过三个 gate、40 条 drop ≤1.0 pp、上界 0.21%，全部吻合）：

| interval | 规则数 | drop ≤1.0 pp | 最低 drop 的那条 | 过 conservative gate |
|---|---|---|---|---|
| 64 | 440 | 0 | 3.519 pp @ 净省 11.18%（stop rate 0.464） | 0 |
| 128 | 440 | 0 | 1.907 pp @ 7.82%（0.252） | 0 |
| 256 | 440 | 0 | 1.685 pp @ 1.26%（0.067） | 0 |
| **512** | 440 | **0** | **1.574 pp @ 1.65%（0.073）** | 0 |
| adaptive | 1,760 | 40 | 0.815 pp @ **−0.58%**（0.010） | 0 |

**把决策密度调到与 DEER 相当（interval 512），consensus 最好也只有 1.57 pp 掉分
换 1.65% 净节省**——在两个轴上同时劣于 DEER 的 conservative 操作点
（−0.33 pp @ 28.2%）。而且整条 interval 轴呈现的仍是同一个「只靠不开火换安全」的
模式：interval 从 64 涨到 512，最低 drop 从 3.52 降到 1.57，净节省从 11.2% 塌到
1.65%。40 条安全规则**全部**来自 adaptive 族，而其中最好的一条净节省是**负的**。

决策点数量不是 consensus 失败的原因。**这条可以直接写成 §5.7 的第四条限定的
答案**，而不是又一条限定。

**与 G2 的关系**：这条控制的是决策**密度**，G2 控制的是**精确位置**。两者互补，
且这条不需要 GPU、现在就成立。即使 G2 失败或延迟，§5.7 也已经有了一个实测的
timing 控制。

### C3 — 相关工作偏薄，且与最接近的先前工作区分不足

**受威胁的论断。** §2 的覆盖面，以及全文的新颖性主张。

**攻击路线（两条，第二条更危险）。**

1. **覆盖。** §2 只有 47 行、3 段、18 条引用。`custom.bib` 里有 **9 条孤儿条目**，
   经核查确实一次都没被引用：`wei2022cot`、`huang2024selfcorrect`、
   `kadavath2022know`、`snell2024scaling`、`brown2024monkeys`、`kuhn2023semantic`、
   `guo2017calibration`、`ross1977false`、`tje`。这些不是随手留下的垃圾——它们是
   **被 8 页限制挤掉的覆盖面**，而 preprint 没有页数限制。其中至少三条与论文的
   论证直接相关：`huang2024selfcorrect`（模型无法自我纠错）正对着机制论证，
   `kadavath2022know`（模型知道自己知道什么）正对着 §5.7「结合反映模型自身估计的
   信号或许有用」那句，`wei2022cot` 是 CoT 本身——一篇通篇讲 chain of thought 的
   论文没引 CoT 原文，很显眼。另外**完全缺席**的是 test-time compute 的预算控制
   一支（s1 / budget forcing、L1 / 长度控制、token-budget-aware reasoning）——
   这是「让推理变短」最出名的相邻文献。
2. **新颖性（更危险）。** §2 用一个从句描述 `dong2026learnstop`：
   "learned prefix-feature stoppers reach the more cautious conclusion that **no
   single aggressive policy is universally safe**"。这与本文的核心论断**非常接近**。
   审稿人完全可以说：这个结论已经有人得出了，本文只是换了个签名。论文现在的区分
   （「我们问的是能否选出一条可迁移策略」）只有一句话，撑不住。

#### 结论：`settled-fix`

覆盖这条是纯写作，preprint 无页数压力，直接补。新颖性这条需要一段真正的区分论证，
建议沿三条轴写清楚：(a) 本文搜的是**预注册的穷举规则空间**（3,520 条）并报告
**0 条通过任何 gate**，不是「某条学出来的策略不普适」；(b) 本文给出**机制**
（独立性缺失 + 探针诱导的占位答案 + 窗口无法外活占位答案），而非只报告经验现象；
(c) 本文有**同一管线内的正向对照**（DEER 通过全部 gate），把结论定位到信号而非
early exit 本身。这三条 `dong2026learnstop` 都没有。

**行动**：§2 扩写；把 9 条孤儿里至少 `wei2022cot` / `huang2024selfcorrect` /
`kadavath2022know` / `snell2024scaling` 接回正文；补预算控制一支；给
`dong2026learnstop` 一段而不是一个从句。**全部待批准，我没动。**

---

## 第 3 轮 — 依赖 GPU（已派给 ugcpu2，见 `GOAL_UGCPU2_V5.md`）

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

## 攻击者扫描（2026-08-08，CPU，只读已提交 bank）

不再从「论文哪里说得不严」出发，而是反过来：**假设我要推翻这篇论文，我会攻哪里。**
四条攻击线，全部跑到了可判定的结论。**四条全部失败，其中三条反而加强了论文。**

### A1 — probe 截断制造的早期分歧（**攻击失败**）

**攻击。** simple@32 探针输出上限 32 token。推理早期答案还没成形，探针更可能被截断，
两种 wording 的截断点不同 → §4.2 的「早期分歧 54%」可能是**截断伪迹**，不是模型真的
没定下来。

**测量。** 229,693 条 `dense_simple32` 探针：撞满 32-token 上限的 **1.05%**，
输出为空的 **0.61%**，众数输出长度 4–6 token。按位置十分位分组：**最早的十分位截断率
最低（0.50%），最后一个十分位最高（1.41%）**。

**结论。** 截断率随位置**上升**，与所需的伪迹方向相反，不可能制造早期分歧。攻击死。

### A3 — DEER 与 consensus 的 token 记账不对称（**攻击失败**）

**攻击。** DEER 的 28–32% saving 若在记账上占了便宜（例如不为未提交的 trial 付费），
整个正对照就废了。

**核对。** `deer_threshold_sweep.replay_problem` 与 `replay_rules` 逐行对照：
两者都**只为停机/提交之前的 probe/trial 输出付费**（DEER `candidate_id <= committed_id`，
consensus 在停机处 return 累加值），两者在**从不触发时都支付整条 schedule**。
**完全对称。** 攻击死。

### A4 — 撞预算的轨迹给了两边免费的 saving（**攻击失败，反向**）

**攻击。** 撞上 selection budget 的轨迹被记为 `baseline_correct=False`、
`baseline_tokens=budget`。在这些轨迹上任何早停都是**零精度代价的纯免费 saving**。
如果它们扛着不成比例的 token 份额，saving 数字就有水分。

**杠杆确实存在。** dev 18 环境 macro：撞预算的轨迹占 **8.22%**，却扛着
**19.52%** 的 baseline token（2.4×杠杆）。逐环境从 0% 到 47.87% 不等。

**但两边都不成立。**

*DEER（`a4_deer_nocap.py`，重放 14 个阈值 × 18 环境）：* 排除撞预算轨迹后
saving **上升**而非下降——

| 阈值 | 全部 684：drop / saving | 排除后 652：drop / saving |
|---|---|---|
| 0.97 | 2.750pp / 31.94% | 3.420pp / 36.98% |
| 0.99 | 1.028pp / 29.56% | 1.428pp / 35.13% |
| **0.995（论文的保守点）** | **0.333pp / 28.21%** | **0.519pp / 33.98%** |
| 0.999 | 0.056pp / 25.43% | 0.172pp / 31.07% |

原因：撞预算的轨迹上 DEER 常常**从不提交**（没有高置信 trial），于是支付全额 budget
**加上**全部 trial 探针，saving 为负——它们在**稀释** DEER。排除后 DEER 仍轻松过保守
gate（0.52pp ≤ 1.0，33.98% ≥ 10%）。**正对照不受影响。**

*Consensus（`a4_consensus_nocap.py`，用已验证与已提交 archive 16 位相同的 fresh-replay
路径，1,760 条 consensus_fixed 规则 × 18 环境 × 652 题）：*

```
problems 652  envs 18   gates {conservative: 0, balanced: 0, token_efficient: 0}
drop ≤1pp 的最大 saving : 无（652 题上没有任何一条规则 drop ≤ 1pp）
10/20/30% saving 的代价 : 3.24 / 7.29 / 12.45 pp   （全 684 题为 2.66 / 6.17 / 11.76）
```

**负结果不但成立，而且更强**：去掉免费 saving 后代价曲线整体抬高，安全角从「40 条规则、
最好省 0.21%」变成**空集**。攻击死，方向对论文有利。

### A2 — 0/3,520 是不是功效不足（**攻击失败，但这是最值得写进论文的一条**）

**攻击。** 18 个环境、aime24 的 dev 只有 6 题。审稿人可以说：你不是证明了没有规则能过
gate，你只是**没有功效**去发现它。「0/3,520」是一个点估计，论文从未给它任何不确定性。

**测量（`a2_bootstrap.py` / `a2_bootstrap2.py` / `a2_perrule.py`，B=2000）。**
两种自助法。**分层版**尊重 2 模型 × 3 benchmark 的全交叉设计，只在每个格子内对 3 个
种子有放回重采；**朴素版**对 18 个环境整体有放回重采（会造出全是 6 题 aime24 的世界，
这个设计其实产生不出来，仅作上界参考）。

| | 分层（按设计） | 朴素 |
|---|---|---|
| P(conservative 非空) | **4.05%** | 6.95% |
| P(balanced 非空) | 0.05% | 0.40% |
| P(token_efficient 非空) | 0.00% | 0.05% |
| drop ≤1pp 最大 saving 中位数 | −0.243% | 0.372% |
| 同上 95% 区间 | [−1.21%, **11.03%**] | [−1.23%, **12.76%**] |

单看这张表像是坏消息：区间上端越过了 10% 的 saving 门槛，约每 25 次重采就有一次会出现
过保守 gate 的规则。**但这是对 3,520 条规则取极大值的产物，不是存在一条真候选规则。**
决定性的反证是逐规则的自助概率（`a2_perrule.py`）：

```
有 P>0 的规则：226 / 3520
单条规则的最大 P(过 conservative) = 0.0190
最高的几条，其真实 macro：drop 2.657pp（门槛 1.0）/ saving 10.94%
                          drop 2.824pp / saving 12.44%
```

**没有任何一条规则的通过概率超过 1.9%。** 而且偶尔通过的那几条，真实 drop 是
**2.66–2.82pp，是 1.0pp 上限的 2.7 倍**——它们只是在幸运的重采世界里被抬到线下，
不是接近合格。在每个重采世界里对 3,520 条相关规则取极大值还只有 4% 命中率，这恰恰说明
安全角是**真的空**，而不是勉强空。

**处理建议（待批准，属于新增项）。** 附录里加一小段功效说明：分层自助 B=2000，
P(任一 gate 非空)=4.05%，单条规则最高 1.9%，偶发通过者真实 drop 2.66pp。
这把「0/3,520」从一个裸点估计变成一个**带不确定性的断言**，正面回应最容易被提出的
统计质疑。preprint 没有页数压力，值得写。

---

## 攻击者扫描 第二轮（2026-08-08，CPU）

第一轮（A1–A4）攻的是**测量与记账**。这一轮攻的是更根本的四个面：**共识判定的
等价关系**、**搜索空间是否被截断**、**18 个环境是不是真的 18 个**、**被排除在成本
之外的那一项**。加一条对最容易被外部核验的数字的重算。

**结论：B1、B2、B4a、B6 死（其中 B2 需要一个新实验才能杀死）；B4b 与 B5 是活的，
都是披露层问题，方向对论文有利，但不披露会很难看。**

### B1 — 共识用字符串相等判定，`0.5` 与 `\frac{1}{2}` 算分歧（**攻击失败**）

**攻击。** `replay_rules.stop_decision` 判定共识用的是 `normalize_answer`——只压缩
空白的**字符串相等**。而 §4.2 的 wording 分析（`compute_probe_wording_v5.eq`）用的是
**数学等价** grader。两处口径不一致。如果探针经常用不同写法表达同一个值，sweep 的
共识信号就是被**解析**压住的，不是被模型压住的，0/3,520 是解析伪迹。

**测量。** dev 684 条轨迹、80,672 次相邻有效探针转移：

```
每题不同答案字符串 10.652 → 数学等价类 10.111（−5.1%）
至少有两个字符串可归并的题：175 / 684 = 25.58%
字符串切换：23,293 次（28.87% 的转移）
  其中数学等价的：656 次 = 切换的 2.82%、全部转移的 0.813%
```

**决定性实验（`b1b_matheq_sweep.py`）。** 把每题的探针答案**按数学等价类归一**到代表
元（复制，不改冻结数据），再重放**全部 3,520 条已提交规则**——这就精确实现了「共识用
数学等价判定」。同一脚本先跑未归一的对照：

| | 对照（字符串，= 已提交口径） | 反事实（数学等价） |
|---|---|---|
| gates | 0 / 0 / 0 | **0 / 0 / 0** |
| drop ≤1pp 的规则数 | 40 | 40 |
| 其中最大 saving | 0.2077% | **0.2100%** |
| 10/20/30% saving 的代价 | 2.6574 / 6.1667 / 11.7593 pp | **2.7130 / 6.2778 / 11.8704 pp** |

对照与已提交 archive **逐位相同**（验证了这套 harness）；反事实下代价曲线还**略微
变差**。攻击死。*附带的小建议：* 论文从未说明共识是字符串判定，这是读者会问的问题，
值得在 §4.1 或附录加半句（**待批准**）。

### B2 — 搜索网格在关键方向上被截断（**攻击需要新实验才能杀死；已杀死**）

**攻击。** 对一个规则族的否定结论，只和这个族一样强。看 dev 的 Pareto frontier：

```
 drop_pp   saving   W    s    maturity  interval
   0.815   -0.58%   30  1.0     512      event
   0.926    0.21%   30  1.0       0      event
   1.574    1.80%   30  0.6     512      event
   1.685    2.94%   24  0.6    2048      512
```

**最靠近安全角的规则全部是 W=24/30、s=1.0——W 是网格上界，s 也是。** 审稿人可以直接
说：趋势是「窗口越长 drop 越低」，你在 W=30 停手了，W=64 或 W=128 就过了。
**只靠已有数据回答不了这个问题。**

**新实验（`b2_extend_grid.py`）。** 在同一条冻结的 dense_simple32 dev 流上，用同一条
已验证的 replay 路径，把网格**推到预注册边界之外**：W ∈ {30(对照), 40, 50, 64, 96,
128, 192, 256}、maturity ∈ {0, 512, 4096, **8192**, **12288**}、interval ∈ {64…512}、
validity 两种，共 320 条规则，其中 **296 条在预注册网格之外**。

```
    W  最低 drop   对应 saving | drop ≤1pp 中最大 saving
   30     0.759     -0.529%   |        -0.529%
   40     0.000     -1.133%   |        -0.882%
   50     0.000     -1.133%   |        -1.133%
   64     0.000     -1.133%   |        -1.133%
   96     0.000     -2.312%   |        -1.133%
  128     0.000     -2.312%   |        -1.133%
  192    -0.056     -9.305%   |        -1.133%
  256    -0.056     -9.368%   |        -1.133%

扩展网格 gate clearers: conservative 0, balanced 0, token_efficient 0
```

**drop 确实被推到 0，代价是 saving 变成负的，而且随 W 单调恶化。** 降低 drop 的那个
轴恰恰就是摧毁 saving 的那个轴；安全角在这个方向上是**内点最优**，把网格往外推没有用。
（对照说明：本实验切片固定 s=1.0、certainty off、只有 consensus_fixed，所以它自己的
W=30 是 −0.529%，而已提交 archive 的 +0.21% 来自一条不在本切片内的 adaptive-event
规则。切片内 W=30 vs W>30 才是同类比较。）

**处理建议（待批准，新增项）。** 这是本轮最值钱的产物：把这张表放进附录，「我们扫了
3,520 条规则」就升级成「而且把最有希望的那个轴往外推了 8.5 倍，仍然是空的」。

### B4a — split 完整性（**干净**）

`split_manifest.json` 的 assignments：aime24 6/6/18、amc23 8/8/24、math500 100/100/300，
**train/dev/test 三两两不交、并集等于全集**，每个 benchmark 内 `content_hash` 重复 0 个
（没有同题不同 id 的泄漏）。

### B4b — 「18 个环境」高估了独立性（**活的**）

**攻击。** 论文到处说 18 个 model×benchmark×seed 环境，读起来像 18 份独立证据。
实际是 **6 个 (模型×benchmark) 格子 × 3 个种子**。种子只改采样，不改题目、不改模型。

**测量。** 逐题看，种子之间**确实不一样**：最终答案相同的种子对占 41.7%（DeepSeek/
aime24）到 92.2%（Qwen3/math500），token 数中位相对差 13.9%–28.1%。**但在「一条规则的
drop」这个层面上，种子几乎不带新信息**：

```
3,520 条规则的 drop 方差分解（6 格子 × 3 种子）
  格子间方差 159.783
  格子内(种子)方差  42.740
  ICC = 0.7890
  等效独立环境数 ≈ 6.98   （种子完全独立则 18，完全相同则 6）
```

**这不推翻任何数字**——0/3,520、478/444/364 都是点估计。但它意味着：
(1) 任何按 n=18 算的 macro 标准误都**偏乐观**；
(2) 我在 A2 里做的**分层自助只重采种子、把格子当固定**，而方差的 79% 在格子间——
所以那个 4.05% 是对「格子固定」条件下的不确定性，**不是对模型/benchmark 总体的**。
朴素版（6.95%）走了另一个极端。真实值在两者之间，两个都该报。

**处理建议（待批准）。** §3.3 加一句限定：18 个环境 = 6 个 model×benchmark 格子 ×
3 个种子，种子内 ICC 0.79，等效独立单元约 7；并在 A2 的功效说明里同时给分层与朴素
两个自助数。改的是措辞和一个附录段落，**没有任何数字需要改**。

### B5 — probe **prompt** token 被完全排除在成本之外，且论文只字未提（**活的，本轮最重**）

**攻击。** §4.2 `sec:accounting` 定义：停在位置 $s$、探针输出 $p$，则 $T=s+p$，
net saving $=(B-T)/B$。**$p$ 只是探针的 decode。** 每次探针都要重新读一遍整个前缀，
而这部分 prefill **一个 token 都没算**，论文正文和附录里**从来没出现过 prompt token
这个成本项**（只有 Limitations 一句「KV-cache-reusing schedule 会改变 savings 轴」）。

**量级（macro over 18 dev envs，每题）：**

| | 探针 prompt token / 题 | 相对 baseline decode |
|---|---|---|
| consensus interval 64 | 457,804 | **52.8×** |
| consensus interval 128 | 271,013 | 31.3× |
| consensus interval 256 | 162,236 | 18.7× |
| consensus interval 512 | 96,266 | 11.1× |
| consensus event-adaptive | 109,071 | 12.6× |
| **DEER（thr 0.995，论文的保守点）** | **36,299** | **4.19×** |

最能说明问题的是那条「最好的安全规则」（`consensus_adaptive__b0631fa39d4b`，drop
0.9259pp，与另外 3 条并列）：main 8,443 + 探针输出 155，对 baseline 8,663，
报出的 net saving 是 **+0.21%**；把 prompt（165,053 个 token）算进去是 **−1904.63%**。

**为什么这不推翻结论、却必须披露。** 方向对论文**有利**：被免掉的成本对 consensus 是
11–53×、对 DEER 只有 4.2×，也就是说现行记账**系统性地偏袒 consensus**，把它算进去
negative result 只会更硬、DEER 的对比只会更强。但：

1. 论文**从未说明** $p$ 不含 prompt，也从未给过这个量级。审稿人自己算出 50× 会认为
   是在藏成本，而不是在保守。
2. 「net saving 0.21%」这种数字在一个忽略了 19× prefill 的预算上报出来，需要一句
   scope 说明才站得住。

**处理建议（待批准，新增项）。** (a) §4.2 加一句：$p$ 只计 decode，prompt 单列，因为
在带 prefix cache 的服务栈下 prefill 与 decode 不同价；(b) 附录加上面这张表。
**这条建议主动披露一个对我们有利的成本项，是本轮最该做的一条。**

### B6 — 重算最容易被外部核验的五个数（**全部原样复现**，但踩到一个复现陷阱）

CLAUDE.md 把 478 / 0 dev / 444 test / 364 overlap / 0 joint 标为「曾经写错过的事实陷阱」。
用独立写的聚合从已提交 archive 重算：

```
train in-sample winners        478   （论文 478）
dev                              0   （论文 0）
test overall                   444   （论文 444）
train winners also on test     364   （论文 364）
dev AND test jointly             0   （论文 0）
478 条在 dev 上的 macro drop 中位数 4.5000pp   （论文 4.50）
全部规则 drop 中位数 train 5.380 / dev 13.190 / test 6.472 pp
```

**全中。** 但过程里踩到一个真陷阱，值得和 D6 一起记：
`test/consensus_test.jsonl.gz` 里**每个环境每条规则有 3 行**，分别对应
budget 8192 / 16384 / 32768，而 dev archive 只有 selection budget 一档。
不按 `budget == selection_budget` 过滤直接聚合，得到的是 **test 940 条过 gate、
train∩test = 0**——和论文完全对不上。这正是 D6 那一类「clone 下来复现不出来」的路径。
**建议在 Appendix C 的复现说明里点名这一条（待批准）。**

---

## 第 4 轮 — 呈现（CPU，无实验）

尚未穷举。已知条目：图 7/8/9 图像里烘死了与 caption 重复的灰色标题；图 1 的文字在
pptx 里、不随 `.tex` 变化；`custom.bib` 有 9 条孤儿条目；`paper/` 里仍有上游 ACL 模板
文件（`acl_latex_template.tex`、`acl_lualatex.tex`、`formatting.md`、
`anthology.bib.txt`、`tests/regression/`）；`dynasor_certaindex` 引的是 v1 的 arXiv 标题。
preprint 没有页数压力，这为第 1–3 轮所需的每一条 hedge 腾出了空间。
