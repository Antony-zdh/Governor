---
title-meta: "Governor：核心实验与概念补强计划"
author-meta: "Governor Project"
lang: zh-CN
documentclass: article
fontsize: 10pt
CJKmainfont: "Hiragino Sans GB"
geometry:
  - margin=1.7cm
colorlinks: true
linkcolor: blue
urlcolor: blue
header-includes:
  - \setlength{\parindent}{2em}
  - \setlength{\parskip}{0.12em}
  - \usepackage{enumitem}
  - \setlist{nosep,leftmargin=2em}
  - \usepackage{titlesec}
  - \titlespacing*{\section}{0pt}{0.65em}{0.25em}
---

\begin{center}
{\Large\bfseries Governor：核心实验与概念补强计划}\\[0.25em]
{\small 面向论文主结论与竞争力的最小实验集合 \quad 2026-07-28}
\end{center}

# 目标

当前最重要的不是继续增加 heuristic，而是闭合三条证据链：Governor 的离线筛选能否在真实在线部署中成立、冻结策略能否泛化到不可见 Test，以及现有 probe 信息与规则决策分别距离可达到上限多远。

# 必须完成的核心实验

1. **原 Governor 的在线部署验证。** 对最终三条 Pareto 策略比较 frozen replay 与真实 online controller 的停止位置、准确率和成本，排除分段生成与 probe 干预改变后续轨迹所造成的偏差。

2. **改良版 DEER 的独立在线实验。** 完成当前 Dev 实验，验证 fast path、retained verification branch 和双答案一致性是否带来优于原 DEER 的 accuracy--token trade-off；结果不反向修改原 Governor Pareto 筛选。

3. **冻结后的 Test confirmation。** 在 Dev 上冻结三条 Governor 策略和改良版 DEER 后，只在不可见 Test 上运行一次，并与 full generation、固定 cap、CertaIndex、TJE 和原 DEER 进行同口径比较。这是论文最终主结论的唯一依据。

4. **Governor--Oracle gap。** 分别计算最早正确答案 oracle、受现有 probe history 限制的 observation oracle 与实际 Governor，由此区分瓶颈来自 probe 信息不足，还是规则没有充分利用已有信息。

5. **最终策略的规则维度消融。** 对 probe、validity、maturity、evidence、persistence、certainty 和 history 逐项 neutralize，证明统一规则格式中的各维度分别贡献准确率保护还是 token 节省。

6. **Adaptive probing 消融。** 将事件触发与固定 interval 在相同停止规则下比较，检验 adaptive probing 是否真正把 Pareto 前沿向外推，而不只是增加观测与 prompt 成本。

# 提高论文竞争力的实验

7. **Leave-one-environment-out 泛化。** 留出一个 benchmark 或一个模型进行规则选择外评估，证明 Governor 学到的是跨环境治理原则，而不是在混合 Dev 环境上的平均最优点。

8. **规模与架构泛化。** 用 Qwen-32B 验证规模泛化，用 Llama-distill 验证架构泛化；只运行冻结后的少量最终策略和最强 baselines，不重新搜索规则。

9. **真实 serving 成本。** 除生成 token 外报告 latency、GPU-seconds、prompt/prefill volume、并发吞吐和 prefix-cache 命中率，避免把 probe 税或长 prefix 成本隐藏在 token saving 中。

10. **校准与失败机制。** 按 confidence、persistence、switch 和 entropy 分桶，分析高置信错误、停止后答案切换、underthinking、overthinking、invalid answer 与 cap failure，解释 Governor 为什么成功以及何时失败。

# 建议强化的核心概念

**跨环境稳健的约束最优停止。** 将 Governor 表述为在每个评估环境都满足准确率下降不超过容忍度的前提下，最大化公平 token saving，而不是依赖任意的 accuracy--token 加权分数：

$$
\max_{\pi}\ \mathbb{E}[\mathrm{Saving}_{\mathrm{fair}}]
\quad
\mathrm{s.t.}\quad
\Delta\mathrm{Accuracy}_{e}(\pi)\geq-\epsilon,\ \forall e.
$$

**昂贵观测与控制动作解耦。** Probe 是有成本的 observation action，stop/continue 是 control action；adaptive probing 近似选择何时值得购买新信息，统一规则则根据累积 belief state 决定是否停止。

**信息缺口与决策缺口分解。** Oracle 实验把性能损失拆成 observation gap 与 policy gap，使论文能够明确回答：Governor 已接近现有观测可达到的上限，还是仍需要更好的规则设计。

# 最小完成顺序

1. 完成改良版 DEER online Dev，并冻结其参数。
2. 完成原 Governor 三策略的 online validation。
3. 在现有数据上完成 Oracle、规则消融、adaptive probing 和校准分析。
4. 冻结全部方法后运行一次 Test confirmation。
5. 最后补充 32B/Llama 泛化与 serving 指标，并形成主表、Test Pareto 图、Oracle gap 图和消融图。

如果资源受限，前四步优先级最高；它们对论文可信度的提升显著高于继续增加新的规则 family。
