# Paper Storyline (v0 draft) — False Consensus / Early-Exit Limits

状态标记:**[FROZEN]** = 脊椎级、已核实、方向不会翻;**[PENDING]** = 等
confirmation / baseline / 决策,影响幅度数字或某一节的有无,但不改主方向。

最后更新:2026-07-27。

---

## 0. 工作标题(候选)

- *False Consensus: The Limits of Confidence-Based Early Exit in Reasoning LLMs*
- *No Free Stop: Preregistered Evidence Against Confidence-Based Early Exit for
  LLM Reasoning*

## 1. 一句话 thesis  **[FROZEN]**

长链推理中,"中间共识"——Dynasor / Certaindex 式早停赖以工作的信号——是
**系统性非终局的**;在一个预注册、穷举式的 17,712 条停机规则搜索里
(2 开发模型 × 3 benchmark × 3 seed),**没有任何规则能同时做到安全
(逐模型 ≤1.5pp 准确率损失)与省 token(正净节省)**,而 prior-work 的原始早停器
最多掉 55pp。结论:推理早停需要的是**一个根本不同的信号,而不是调得更好的
置信度阈值**。

## 2. 叙事弧(6 拍)

1. **动机**:推理模型输出极长 → 早停诱人 → 现有方法(Dynasor/Certaindex)
   赌"探针看到共识 = 可以停"。
2. **现象 [FROZEN]**:False Consensus —— 中间共识会改变、且经常改对;
   窗口 share 高估可信度;误差分类 A–E。(Stage 1–5,MATH500×500,DeepSeek-7B)
3. **预注册的严格检验 [FROZEN 方法, PENDING 全部环境]**:冻结主轨迹 +
   离线密集 re-probe(每 64 token,simple@32);7 维规则空间;17,712 候选;
   问题分组 60/20/20 split;门槛不可事后放宽;test/Llama-8B/32B 对 sweep 全程不可见。
4. **负结果 [FROZEN(dev)]**:不存在安全甜点。报前沿——准确率地板 1.85pp、
   正净节省需 ≥4.87pp、**adaptive 事件触发严格更差**(entropy/conclusion 越省越掉准)。
5. **机制 [FROZEN 概念, PENDING 1–2 个数]**:方向性(继续推理纠错)+
   拆解"准确率税(内在)vs probe 税(可调)"。
6. **prior work + 启示 [PENDING baseline]**:CertaIndex/Entropy/Patience 灾难性失败;
   我们的规则家族更稳健但也过不了门槛 → 早停**信号本身**要换,而非换阈值。

## 3. Contributions

- **C1** 定义并量化 False Consensus(现象 + 校准 + 误差分类)。**[FROZEN]**
- **C2** 预注册穷搜的"近似不可能性"结果 + 完整 Pareto 前沿刻画。**[FROZEN(dev)]**
- **C3** 机制:方向性 + 准确率税 / probe 税分解。**[PENDING 少量数]**
- **C4** prior-work baseline 对比,证明规则家族在稳健性上 Pareto-dominate。**[PENDING]**
- **C5**(仅当走 option C)"一个能用的早停信号需要什么"的建设性方向。**[可选]**

## 4. claim → 证据 → 冻结状态

| # | Claim | 证据 | 状态 |
|---|---|---|---|
| 1 | 窗口/累积共识非终局 | Stage 1–5:window share=1 仍 6.5% false consensus | **FROZEN** |
| 2 | 朴素早停代价大 | Stage 1–5:3-probe 早停 −16.4pp(69.2→85.6) | **FROZEN** |
| 3 | 预注册空间无安全甜点 | v2 sweep:min 逐模型降幅 1.85pp,门槛全灭 | **FROZEN(dev)** |
| 4 | 正净节省最低价 ≥4.87pp | v2 sweep 前沿 | **FROZEN(dev)** |
| 5 | adaptive 触发更差 | adaptive_event 家族:最保守点也 −5.88pp macro / 最坏 −9.70pp,越激进越差(今日逐位复现) | **FROZEN(dev)** |
| 6 | 准确率地板与 probe 税无关 | 降幅只取决于停机位置,不含 probe 成本 | **FROZEN(论证)** |
| 7 | 净节省崩塌部分因 probe 税 | total = main + probe_decode;保守规则一路交税 | **FROZEN(机制), PENDING gross/net 表** |
| 8 | 继续推理系统性纠错 | 方向性检验(final-对&早停-错 : 反向) | **PENDING(待跑一个数)** |
| 9 | 在 held-out 模型/seed/test 上复现 | confirmation 阶段 | **PENDING** |
| 10 | prior work(CertaIndex 等)灾难性失败 | 3 baseline 同轨迹回放 | **PENDING(同事在跑 / 我方待复现)** |

## 5. 主要图表(锚定各 claim)

- **Fig 1**:False Consensus 示意 + share→accuracy 校准曲线(claim 1)。
- **Fig 2**:早停 vs 继续 的准确率(claim 2)。
- **Fig 3**:v2 Pareto 前沿(降幅 vs 净节省),标出门槛线与"无点可过"(claim 3/4)。
- **Fig 4**:家族对比条形图,含 adaptive 越激进越差(claim 5)。
- **Fig 5**:gross vs net 节省分解 = 准确率税 vs probe 税(claim 6/7)。
- **Table 1**:方法总表(full / fixed-budget / CertaIndex / Entropy / Patience /
  Governor 三工作点),准确率 / main / total token / stop-rate(claim 10)。
- **Table 2**:confirmation —— 各家族最优点在 test + Llama/32B 上的下界(claim 9)。

## 6. 最大风险 + 预先拆解

**风险**:审稿人说"负结果是你 dense probe 税造成的伪影"。
**拆解**:
1. **准确率地板(1.85pp)与 probe 税完全无关**——它只取决于停在哪,不含 probe 成本;
2. **gross / net 双报**——把 probe 成本剥掉后仍有准确率税;
3. **规则空间是预注册的、宽的**(7 维、17k),报完整前沿,证明不是"挑了一条烂规则";
4.(若走 C)**已尝试用更稀疏 probe / 答案形态过滤去救**,给出可达上界。

**次要风险**:AIME24 dev 仅 18 题,单点 −11.1pp ≈ 2 题,统计不稳。
**拆解**:报 seed 聚合 + confirmation 扩样;主结论用宏平均而非单格。

## 7. 与 A/B/C 决策的关系

- **走 A(纯负结果)**:C1–C4 + confirmation 验证下界。骨架已完整,无需 C5。
- **走 C(扩展规则空间)**:在 C4 后加 C5,报"救出的正节省上界",故事从"不可能"
  变"当前信号不行、这样改才可能"。**C5 是增量,不改前 4 节。**
- **走 B(改门槛重注册)**:只改 §3 的门槛叙述与前沿标注,claim 1/2/5/6 不动。

三条路都建立在 §4 的 FROZEN 行之上,所以现在写 storyline 是安全的。
