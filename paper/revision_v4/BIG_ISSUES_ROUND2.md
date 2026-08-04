# v4 第二轮：大问题清单

基线 `v4` @ `0265b37a`。上一轮（`REVIEW_ISSUES.md`）的 A1–A13 / B1–B13 已全部落实，
本轮只列**框架与术语层面的大问题**，通读全文的小问题留到下一轮。

---

## 1. 术语总方针：`stability` 整体降级，统一到 `self-consensus`

**决定：** `stability` 不再是关键词。核心概念名改为
**`consensus--termination gap`**。全文只保留一组术语：

- **`self-consensus`** —— 唯一的正式名称，在首次出现处定义清楚；
- **`consensus`** —— 声明为其缩写，正文后续使用；
- **`agreement` / `agree`** —— 描述行为时的普通用词，不是术语。

### 1.1 定义声明放在哪里

canonical 定义留在 `01_introduction.tex` 第一段（现在已经有了），保持这个结构：

> A natural and increasingly studied proxy is \emph{self-consensus}: repeatedly
> probing a \emph{single} partial trajectory for its current answer … and stopping
> once recent probe answers \emph{agree}. We abbreviate self-consensus as
> \emph{consensus} below, and reserve \emph{self-consistency} for the distinct
> setting in which several trajectories are sampled independently.

摘要保留一次简短引入（`---\emph{self-consensus}`），§2 复述其与 self-consistency 的对比。

### 1.2 `terminality` → `termination`

`terminality` 不是常用词，全文 13 处：标题 2（`acl_latex.tex:38,50`）、
`01_introduction.tex` 4、`02_related_work.tex` 1、`06_mechanism.tex` 4、
`09_conclusion.tex` 1、`10_limitations.tex` 1。

- `stability--terminality gap` → **`consensus--termination gap`**
- `reasoning terminality` → **`reasoning termination`**
- 动词 `has terminated` / `non-terminal` 保持不变

### 1.3 概念名替换（6 处 + 标题 + 注释）

| 文件:行 | 现有 | 改为 |
|---|---|---|
| `acl_latex.tex:38` | 标题里的 `The Stability--Terminality\\ Gap` | 见第 2 条（换标题） |
| `acl_latex.tex:50` | 注释 `% 4 The Stability--Terminality Gap` | `% 4 The Consensus--Termination Gap` |
| `01_introduction.tex:25` | `\emph{stability--terminality gap}` | `\emph{consensus--termination gap}` |
| `01_introduction.tex:97` | `a stability--terminality gap in probe-based early exit` | `a consensus--termination gap in probe-based early exit` |
| `06_mechanism.tex:1` | `\section{The Stability--Terminality Gap}` | `\section{The Consensus--Termination Gap}` |
| `06_mechanism.tex:75` | caption `Two sides of the stability--terminality gap.` | `Two sides of the consensus--termination gap.` |
| `09_conclusion.tex:8` | `\emph{stability--terminality gap}` | `\emph{consensus--termination gap}` |
| `10_limitations.tex:50` | `the stability--terminality gap` | `the consensus--termination gap` |

### 1.4 删掉竞争术语

| 词 | 位置 | 处理 |
|---|---|---|
| `probe stability` | `00_abstract.tex:12`、`01_introduction.tex:23`、`01_introduction.tex:99` | 整个标签删除 |
| `Probe Stability: Full Analysis` | `03_false_consensus.tex:1`（附录 B 标题） | → **`Self-Consensus: Full Analysis`** |
| `probe agreement` | `02_related_work.tex:16` | → `self-consensus` |

### 1.5 ⚠️ 必须同时改写的核心句，否则会变成同义反复

原来的对比是"agreement 建立的是 **stability**，不是 termination"——两个属性对举。
换成 `consensus--termination` 之后，如果照抄旧句式就成了"agreement 建立的是
agreement"，是废话。**解法：不给信号起第二个名字，用 `persists` 承担语义**：

> …repeated agreement establishes only that the current answer \emph{persists}
> under a fixed probing procedure, not that the reasoning has
> \emph{terminated}---a \emph{consensus--termination gap}.

需要按这个句式改写的有：`00_abstract.tex:10-13`、`01_introduction.tex:21-25`、
`01_introduction.tex:97-99`（contribution 第一条）、`06_mechanism.tex:2-4`、
`09_conclusion.tex:5-8`。

**顺带一提，新名字其实更好。** `stability–terminality` 是两个抽象属性对举；
`consensus–termination` 直接点名**我们能观测的信号**与**我们真正需要的性质**，
读者一眼就知道 gap 的两端分别是什么。

### 1.6 `stability` / `stable` 作为普通词的残留处理

这些不是术语，但既然 `stability` 已降级，建议顺手清掉当名词用的几处：

| 文件:行 | 现有 | 建议 |
|---|---|---|
| `06_mechanism.tex:120` | `screens out some non-terminal stability` | `screens out some non-terminal agreement` |
| `06_mechanism.tex:185` | `a statement about the stability of one line of reasoning` | `a statement about one line of reasoning not having changed its answer` |
| `A_appendix.tex:342` | `Its stability therefore says nothing about…` | `That it never changes therefore says nothing about…` |
| `05_results.tex:72` | `self-consensus supplies a stable policy` | `supplies a \emph{transferable} policy`（此处 stable 是"稳健"另一义，易混） |

形容 model / trajectory 状态的 `settled`、`stable but mistaken belief`、
`a long, stable agreement`（`05_results.tex:26`）都是普通英语用法，**保留不动**。

替换完成后自检：`probe stability`、`probe agreement`、`terminality`、
`intermediate answer consensus`、`answer stability`、`false consensus` 应全部为 0 次。

## 2. 标题

**现有：** Stable Answers, Unfinished Reasoning: The Stability--Terminality Gap in
Probe-Based Early Exit

**建议：** **Agreed Answers, Unfinished Reasoning: Why Self-Consensus Is Not a
Safe Early-Exit Signal**

在 Antony 的候选基础上改了两个字，理由：

1. **主标题的 "Stable" 也要跟着降级。** 既然 `stability` 不再是关键词，
   主标题却以 Stable 开头会与正文脱节。`Agreed Answers` 直接呼应 `self-consensus`，
   而且 "Agreed / Unfinished" 的反差比 "Stable / Unfinished" 更锐利。
2. **现标题把同一件事说了两遍。** 主标题已是 gap 的白话版，副标题再复述一次，
   信息量为零；候选的副标题补的是**结论**。
3. **候选把研究对象写进了标题。** `self-consensus` 可检索、可被引用；
   `Consensus–Termination Gap` 目前还是自造词，没人拿它检索。
4. **负面结果的论文应在标题陈述发现而非概念**，现标题读起来像方法论文。

**已定：用 `safe`，不用 `reliable`。** 全文 gate 讲的就是 safe-and-saving，
§5 和结论也都用 `safe`，术语链条闭合。

**代价：** 标题丢掉了"我们命名了一个现象"这层贡献。缓解办法是让
`consensus--termination gap` 在摘要首句、§4 标题和 contribution 第一条里保持醒目
（现在已经是这样）。

## 3. 45:1 该不该继续用作头条

**判断：保留这个数字，但从"头条锚点"降级为"区间的一端"。图不用重画。**

**为什么它有风险。** $45{:}1$ 是 $W{=}1$，即完全不设窗口的 latest-probe 停止。
从 `harm_rescue_cache.json` 看，这个操作点同时伴随 **65.9pp 的准确率下降**和
**92.3% 的 token 节省**——没有任何人会部署它。审稿人只要翻到 §4.4 的曲线就会发现
"up to ~45×" 里的 "up to" 承担了全部重量，反而削弱可信度。

**为什么不必删。** 数字本身是对的，图画的是**整条窗口轴**（$W$ = 1/3/5/8/12/16/24/30，
ratio 45.1 → 25.7 → 13.3 → 8.6 → 5.7 → 4.3 → 2.6 → 2.0），本来就是诚实的对象。
真正做论证的是"**在任何还能省 token 的窗口下，比值都远高于 1:1**"，不是端点。

**只改正文锚点（三处）：**

| 位置 | 现在 | 建议 |
|---|---|---|
| `00_abstract.tex:14` | "destroys … up to ${\sim}45\times$ more often" | 改为区间 + 对照，例如 "destroys a correct-in-the-end answer $2$--$45\times$ more often than it banks a wrong one---never approaching the $1{:}1$ of sampling noise at any window that still saves tokens" |
| `01_introduction.tex:44` | "roughly ${\sim}45\times$ … at an aggressive latest-probe stop" | 同上，并把 DEER 的对照提到同一句：DEER 在 **2.4–3.5:1** 的同时省 **28–32%**，而 consensus 要压到 2:1 就只剩 **7.9%** 的净节省 |
| `09_conclusion.tex` | "up to ${\sim}45\times$ … ${\sim}2\times$ at the largest windows" | 现有写法已经带了两端，可保留，只需与摘要/intro 措辞一致 |

`06_mechanism.tex:133` 与图 caption 里的 45:1 是在完整曲线的语境中出现的，**不用动**。

**参考数据**（dev，18 环境，`harm_rescue_cache.json`）：

| $W$ | harm:rescue | 停止题数 | 净节省 | drop |
|---:|---:|---:|---:|---:|
| 1 | 45.1 | 668 | 92.3% | 65.9pp |
| 5 | 13.3 | 603 | 52.6% | 26.3pp |
| 8 | 8.6 | 525 | 37.2% | 15.8pp |
| 16 | 4.3 | 311 | 21.3% | 8.0pp |
| 30 | 2.0 | 121 | 7.9% | 2.0pp |
| DEER C/B/T | 3.0 / 2.4 / 3.5 | 537/550/566 | 28.2/29.6/31.9% | 0.33/1.03/2.75pp |

---

## 4. 本轮重扫新发现的大问题

### 4.1 ⚠️ 最重要：§5.7 把 DEER 对照的归因说过头了

`05_results.tex`「Locating the Failure」现在写：

> …since the same machinery, gates, and accounting produce both outcomes, what
> separates them is the \emph{signal}.

**这一步是全文的承重墙**（把"consensus 不行"升级成"信号不行"），但对照并没有控住。
DEER 与 consensus 的差别**不止读什么信号**：

1. **何时读** —— DEER 在 reasoning boundary 触发，consensus 按固定间隔（或事件）触发；
2. **怎么提交** —— DEER 直接提交 trial answer，consensus 提交探针答案。

我们控住的是 pipeline、gate、token 记账，没有控住"读取时机"和"提交方式"。
审稿人完全可以说：你证明的是 *boundary-triggered confidence 优于 fixed-interval
agreement*，而不是 *confidence 优于 agreement*。

**处理：主动承认，代价很小、收益很大。** §5.7 现有三条 qualification 里加第四条，
或把第一条改写为：

> DEER differs from the swept family in more than the statistic it reads---it is
> triggered at reasoning boundaries and commits a trial answer rather than a probe
> answer. The contrast therefore localizes the failure to the consensus
> \emph{family} as deployed, not to the agreement statistic in isolation.

同时 §5.1「A non-consensus control, swept identically」的小标题也要改，
`identically` 目前只对 pipeline/gate/accounting 成立。

### 4.2 Figure 1 里烤死了旧术语，术语改名后必须重新生成

`figures/gen/fig1_idea.pdf` 面板 (a) 的标题文字是
**`a  Agreement ≠ terminality`**，是 pptx 里的固定文本，不会随 `.tex` 改动。
源文件 `paper/revision_v3/make_fig1_idea.py` → `fig1_idea.pptx` → `fig1_idea.pdf`，
需要改脚本后重新导出，并同步 `fig1_idea_b`（若仍保留）。

建议改为 **`a  Agreement ≠ termination`**（或更贴合新框架的
`a  Consensus ≠ termination`）。

**顺带一个判断题：** 同一面板右下角印着 `harm : rescue ≈ 45 : 1`。这是**18 环境的聚合量**，
却放在**一条轨迹**的示意图里，读者容易误以为是这条轨迹的数字。既然图无论如何要重导，
建议要么移到面板 (b)/(c)，要么加上 "(dev, all windows: 45:1 → 2:1)" 的限定。

### 4.3 「可迁移策略」的提法比实际结果**弱**，而且摆在摘要最显眼处

摘要现在写：

> We ask whether any such rule can be selected once and stay both safe and saving
> \emph{elsewhere}.

但实际结果分两层，且第一层更强：

1. **在 dev 上就没有任何一条规则通过任何 gate**（0/3,520）——根本不存在"可迁移"的
   候选，谈不上迁移失败；
2. 只有在 train 上**in-sample** 通过的 478 条，到 dev/test 才谈得上"没保住"。

照现在的写法，读者会以为结论是"换个环境就不灵了"，这**弱于**真实发现。
建议摘要与 intro 都把两层分开说，例如：

> No rule is safe and saving even on the split where the gate is applied; the
> $478$ that clear it \emph{in-sample} on train do not survive on dev or test.

§5.5 和附录里两层已经写清楚了，需要改的是摘要与 intro（`01_introduction.tex:52-60`）
以及 §5 开头的 "environment-robust policy" 那段。

### 4.4 摘要与正文的叙事顺序相反（中等，可接受但要有意识）

摘要：sweep 结果 → DEER → "The reason is…" → 机制。
Intro / 正文：机制（§4）→ sweep（§5）。

结果先行的摘要在 ACL 是常规，但读者从摘要进正文时会觉得正文"慢"。
如果保留现顺序，建议在 §4 开头加半句衔接（"the sweep of \S5 rests on what this
section measures"），让倒序是显式的而非偶然的。

---

## 5. 上一轮我提的 5 个叙事绊点——已全部修复

记录在此供核对，无需再改：

1. **§4.1 三套数据混在 15 行里** → 已拆出独立段落 "The same question on a broader
   environment set"，明确说明 18 环境、684 条、去掉 certainty 条件。
2. **摘要先给 headline、§4 再降级** → 摘要改为先讲 sweep 再讲机制；intro 加了
   "the first two are single-environment observations, the third spans all $18$"；
   §4.2 改为 "diagnostic: nothing in §5 rests on them"。处理得比我建议的更干净。
3. **§4.4 标题低估自己** → 已改为 "A Directional Cost, Not Sampling Noise"。
4. **§5.6 位置突兀** → 已删除，压缩成 §5.2 末尾两句 + 附录 `tab:grossnet` 段。
5. **附录 B 旧招牌** → 已改名，但改成了 "Probe Stability"，正好撞上本轮第 1 条。

---

## 6. 小问题（下一轮通读时一并处理）

- **53% / 46% 的舍入方向不一致。** 前 10% 的实际值是 46.48% 一致 / 53.52% 不一致；
  正文写 53%（下舍），caption 写 46%（下舍），两处方向相同但加起来是 99%。
  建议统一写 "$46\%$ agree / $54\%$ disagree" 或都用"不到一半 / 过半"。
- **两处未写分母。** §4.2 说 "the $241$ trajectories it covers end to end"，
  没说是 400 条中的 241 条（60%）。选择性偏差的 caveat 需要这个分母才站得住。
- **`custom.bib` 有 9 条孤儿引用**：`wei2022cot`、`tje`、`guo2017calibration`、
  `snell2024scaling`、`brown2024monkeys`、`kadavath2022know`、`kuhn2023semantic`、
  `huang2024selfcorrect`、`ross1977false`。其中 `tje`（TJE 基线已删）和
  `ross1977false`（false-consensus 脚注已删）是这轮改动造成的，可清理。
- **`paper/README.md` 仍被 ACL 上游模板的 README 覆盖**，我们自己的构建说明没了；
  同批混进来的还有 `acl_latex_template.tex`、`acl_lualatex.tex`、`formatting.md`、
  `anthology.bib.txt`、`tests/regression/run_tests.py`（测的是 bst 作者格式，与本文无关）。
  建议回滚 README 并把这几个移出投稿目录。
