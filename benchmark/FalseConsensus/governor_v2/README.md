# Governor v2：多环境规则开发协议

本目录把下一轮实验分成三个彼此独立的对象：

1. **环境（environment）**：benchmark、model、main seed、题目及其预先给定的难度、采集上限与评估 budget；
2. **规则（rule）**：只读取推理过程中可在线获得的通用信号；
3. **数据角色（split）**：train 用于宽搜索，dev 用于选择 operating point，test 只在规则冻结后评估一次。

`protocol.json` 是当前唯一配置入口。协议已预注册：开发模型为
DeepSeek-R1-Distill-Qwen-7B 与 Qwen3-8B；DeepSeek-R1-Distill-Llama-8B
只验证架构泛化，DeepSeek-R1-Distill-Qwen-32B 只验证规模泛化。后两者及 test
都不能被 `sweep` 或 `select` 读取。

## 1. 为什么采用 60/20/20

不存在对所有实验都正确的固定比例。Google 的数据划分说明使用
70/15/15 作为示意，同时明确指出比例取决于数据量，验证集和测试集必须足以代表总体并支持有统计意义的判断：

- <https://developers.google.com/machine-learning/crash-course/overfitting/dividing-datasets>

本项目对三个 active benchmark 都采用题目级 **60/20/20**。对应数量为：
MATH500 300/100/100、AMC23 24/8/8、AIME24 18/6/6。后两者显式设置
`force_ratio_split=true`，因为本轮需要在 train/dev 中开发针对难题的规则，而不是
只把难题留作外部压力测试。GSM8K 的既有文件只作为历史 artifact 保留，不进入矩阵。

切分约束如下：

- 题目是最小 group；同一题的所有 model、seed、probe 和 rule 结果永远属于同一 split。
- 每个 benchmark 单独按相同比例切分，不能先把不同 benchmark 混在一起再随机切。
- MATH500 按 `level × subject` 分层；切分只使用生成前已知的 metadata。
- AMC23/AIME24 虽小，仍按预注册比例切分；其 dev/test 只有 8/8 和 6/6 题，
  必须报告宽置信区间，不能把单一难题 benchmark 的小幅差异当成稳定结论。
- train/dev/test 之间检测题目 ID 重复；跨 benchmark 的相同题面不得落入不同 split。
- test 只在规则 ID、阈值和选择门槛冻结后运行一次。反复依据 test 修改规则会造成选择偏差；同一数据上调参与报告结果也会给出偏乐观估计：
  <https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html>

这里的 `train` 是“规则发现集”，不是神经网络参数训练集：

| 数据角色 | 允许的操作 |
|---|---|
| train | 宽规则搜索、剪掉明显劣势点、构建 Pareto 候选 |
| dev | 施加跨环境门槛、选择三个互异 Pareto operating points、冻结规则 ID |
| test | 一次性主结果和置信区间；不得据此回改规则 |
| external_stress | 当前无 active benchmark；保留该角色供未来额外数据集使用 |

## 2. 环境变量和规则维度

model、seed、benchmark、题目难度与 budget 是**环境变量**。它们可以用来分层汇报、
检查稳健性或定义评测环境，但不能让规则写成 “Qwen 时用阈值 A、seed 42 时用阈值
B”。难度标签也不应作为在线规则输入；若要适配题目，应使用到当前时刻为止可见的
通用动态信息。

每条规则无论属于哪种 family，都必须包含相同的七个顶层维度：

| 维度 | 统一字段 | 含义 |
|---|---|---|
| `probe` | style、output cap、schedule、event/cooldown/fallback | 何时询问以及 probe 成本；固定频率、结论词、entropy drop、反思转折、答案候选和混合触发都属于这一规则维度 |
| `validity` | `nonempty` / `schema` | 哪些 probe 答案可进入证据 |
| `maturity` | none/fixed/budget fraction/online instability | 最早允许停止的成熟度条件 |
| `evidence` | latest/window share/entropy | 当前证据如何聚合成候选答案 |
| `persistence` | consistent accepts、consensus span | 候选共识需要维持多久 |
| `certainty` | enabled、certain fraction | 是否排除显式犹豫的 probe |
| `history` | switches、switch window、stable span | 最近一段窗口内是否频繁改答，或是否刚发生切换 |

`rule_schema.py` 负责统一校验、稳定哈希 ID、模板展开和消融生成。即使某个 family
不用某一维，它也必须写出该维的 neutral/reference 值，不允许再使用不同 family
各自一套无可比性的扁平字段。

简化示例：

```json
{
  "rule_id": "latest_persistence_fixed_maturity__<hash>",
  "probe": {
    "style": "simple",
    "output_cap": 32,
    "schedule": {
      "kind": "fixed",
      "start_token": 128,
      "interval_tokens": 128,
      "phases": [],
      "event": {
        "trigger_types": [],
        "marker_profile": "none",
        "minimum_gap_tokens": 64,
        "fallback_interval_tokens": null
      }
    }
  },
  "validity": {"mode": "schema"},
  "maturity": {"kind": "fixed_tokens", "minimum_tokens": 1024},
  "evidence": {"family": "latest", "window_probes": 1},
  "persistence": {
    "minimum_consistent_accepts": 5,
    "minimum_consensus_span_tokens": 256
  },
  "certainty": {"enabled": true, "minimum_certain_fraction": 1.0},
  "history": {
    "maximum_switches": 2,
    "switch_window": {"kind": "tokens", "size": 2048},
    "minimum_stable_span_tokens": 256
  }
}
```

实际记录包含全部必填字段；以上只展示主要值。

## 3. 数据与采集架构

旧版 `logging_run.py` 将主生成和 probe 交错执行，改变 interval 会重置主请求并可能改变
后续主轨迹。v2 改为：

1. `collect_main.py` 对每题只发出一次完整主生成请求；
2. `dense_probe.py` 对冻结后的文本前缀做 interval-64 simple@32 re-probe；
3. `adaptive_probe.py` 在同一冻结文本上定位 event candidates，做 teacher-forced
   top-k entropy scoring，并只对 dense bank 未覆盖的位置补采 simple@32；
4. 固定、分阶段、agreement-adaptive 或 event-adaptive schedule 在离线 replay
   时从两类 bank 的并集取样。

因此比较 probe interval 时，主文本不再随 interval 改变。总成本仍必须计入截至停止点
已经发生的 probe output token；prompt token 和 wall-clock 另列，不混成“免费 probe”。
entropy scoring 使用冻结序列的 teacher-forced prompt logprobs：服务端所需的一个
额外 decode token会被丢弃，不进入主轨迹，也不会改变答案。事件位置先对齐到后续
step boundary，再应用最小间隔；同一位置若也属于 dense-64，直接复用已有 probe。

当前预注册的 adaptive trigger family 是：

- `conclusion_marker`：strict（therefore/thus/hence/consequently/conclude）；
- `entropy_drop`：局部 16-token 平滑 entropy 相对前 64 token 明显下降；
- `reflection_transition`：wait/however/alternatively/check 等重新审视信号；
- `answer_candidate`：boxed/final answer/answer is 等候选答案信号；
- hybrid：上述事件的并集，并带 64/128-token cooldown。周期 fallback 复用
  dense-64 bank，不额外发请求。

`capture_cap` 是为了建立可复用长轨迹库的最大采集视野，不等于部署时 Governor
必须允许使用的预算。5% 是结合 prior/pilot 选择 cap 时的设计目标，不是主实验跑完后
必须通过的验收线：cap 在主实验前冻结，实际截断率即使超过 5% 也如实报告，不能据此
事后提高 cap。test 永不参与 cap 选择。当前设置为 MATH500 16K、AMC23 16K、
AIME24 32K；同一条长轨迹
再离线截断到各 benchmark 预注册的 `evaluation_budgets`。这样既能
比较 B3072/B8192/B16384，又不会把 3072-token 截断误当成自然终点。达到
`capture_cap` 的序列仍按 right-censored 单独标记。

现有证据只有 MATH 可直接验证：已有 400 条 16K 长 rollout 中，12,288 token
仍有 21/400=5.25% 未结束，而 16,384 token 为 15/400=3.75%，所以选 16K。
AIME 的 240 条 rollout 在 16K 仍有 81/240=33.75% 未结束，因此提高到共同原生
上下文范围内的 32K，但不为了追求事后小于 5% 而启用额外 context extension。AMC
只有 3K 截断 pilot。报告同时给 point estimate 和 binomial confidence interval，
二者都只描述实际
截断情况，不触发 post-hoc cap 修改。

生成固定切分、候选规则和两阶段采集矩阵：

```bash
python benchmark/FalseConsensus/governor_v2/make_splits.py
python benchmark/FalseConsensus/governor_v2/prepare_rules.py expand
python benchmark/FalseConsensus/governor_v2/build_experiment_matrix.py \
  --phase development \
  --output benchmark/FalseConsensus/governor_v2/generated/development_matrix.jsonl
python benchmark/FalseConsensus/governor_v2/build_experiment_matrix.py \
  --phase confirmation \
  --output benchmark/FalseConsensus/governor_v2/generated/confirmation_matrix_base64.jsonl
python benchmark/FalseConsensus/governor_v2/build_experiment_matrix.py \
  --phase confirmation --exclude-model-role heldout_scale \
  --output benchmark/FalseConsensus/governor_v2/generated/confirmation_small_models_base64.jsonl
```

开发矩阵含 2 个开发模型 × 3 个 benchmark × 3 seeds = 18 个环境；
对应 18 个 main、18 个 interval-64 base probe 和 18 个 adaptive bank，共 54 行。
完整 confirmation 矩阵为 72 行；排除 32B 后的
`confirmation_small_models_base64.jsonl` 共 63 行。矩阵只生成命令，
不自动提交 GPU 作业。

正式 dense bank 冻结为 `64,128,192,...`。probe frequency 仍然是规则维度，但
可优化范围是从该 bank 无损下采样得到的 64/128/256，而不是无法由数据支持的 32。
本轮不生成互补 offset pass。

## 4. 规则搜索和选择

```bash
python benchmark/FalseConsensus/governor_v2/prepare_rules.py expand
```

interval-64 dense bank 加 adaptive event bank 后，当前宽搜索空间共有 17,712 条规则：

- latest + persistence + fixed maturity：10,368（无限制、最近 2,048
  token、最近 16 probes 三种 history switch 配置）；
- window share + budget-fraction maturity：1,296；
- entropy + budget-fraction maturity：5,184；
- adaptive event schedule：864。其 4 个 schedule 分别为 conclusion、
  entropy drop、reflection+answer，以及
  hybrid；再与其余六维的紧凑网格组合。

执行时采用 funnel，而不是让 test 参与筛选。回放可按规则分片并行：

```bash
python benchmark/FalseConsensus/governor_v2/replay_rules.py sweep \
  --phase development \
  --rules benchmark/FalseConsensus/governor_v2/generated/candidate_rules.jsonl \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
  --shard-index 0 --shard-count 8 \
  --output benchmark/FalseConsensus/governor_v2/generated/sweep_0.jsonl

python benchmark/FalseConsensus/governor_v2/replay_rules.py select \
  --rules benchmark/FalseConsensus/governor_v2/generated/candidate_rules.jsonl \
  --metrics benchmark/FalseConsensus/governor_v2/generated/sweep_*.jsonl \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
  --output benchmark/FalseConsensus/governor_v2/generated/frozen_rules.json
```

`select` 只接受 development/train/dev 指标，并把 protocol、split、candidate
rules 与 sweep 文件的 SHA-256 一并冻结。确认评估会再次校验这些 hash：

```bash
python benchmark/FalseConsensus/governor_v2/replay_rules.py evaluate \
  --frozen benchmark/FalseConsensus/governor_v2/generated/frozen_rules.json \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
  --output benchmark/FalseConsensus/governor_v2/generated/confirmation_metrics.jsonl
```

`select` 会先验证 17,712 条规则是否都具有完全相同且完整的 36 个
development 环境行（train/dev × 2 models × 3 seeds × 3 benchmarks），并拒绝未知
rule、重复行、缺失 shard 或环境污染。随后在三个目标上构造真正的非支配前沿：
最大化 dev 环境 token saving 的第 20 百分位，同时最小化最差 split-by-model 与
split-by-benchmark accuracy drop。指标完全相同的规则只保留复杂度最低者。

具体 funnel：

1. 在 train 上评估全部候选并施加稳健性门槛；
2. dev 独立施加同样门槛，并只用 dev 的第 20 百分位节省量排序；
3. 环境按宏平均评估，不按原始题数做 micro pooling；
4. 从非支配前沿依次冻结三个互异点：conservative（model/benchmark drop
   ≤1.5/2.0 pp，≥80% 环境正节省）、balanced（≤2.5/3.0 pp，≥80%）和
   token-efficient（≤4.0/5.0 pp，≥70%）；
5. 任一点没有合格的互异非支配规则时立即失败，不得重复一个 rule ID 来凑数；
6. 三个完整 `rule_id` 与 Pareto 前沿、输入 SHA-256 一并冻结后，才运行三个
   benchmark 的 test。

环境的统计单元是 `benchmark × model × seed`。这样大 benchmark 不会仅凭题目多就压过
其他环境，也会暴露“平均省 token、但某一模型系统性退化”的规则。

## 5. 每一维都必须消融

把冻结后的规则保存为一个 JSON/JSONL 后执行：

```bash
python benchmark/FalseConsensus/governor_v2/prepare_rules.py ablate \
  --selected selected_rules.json
```

对三个 selected rule 分别自动产生两套设计：

- **one-at-a-time：** 原规则 + 七个单维 reference replacement，共 8 个 cell；
- **full factorial：** 七维分别取 selected/reference，共 \(2^7=128\) 个 cell。

这里用 `reference replacement` 而不是笼统的 “remove”。例如拿掉 probe 或 evidence
会使 Governor 根本无法决策，所以它们的 reference 分别是固定 simple@32/128 schedule
和 latest evidence；其余维度尽量使用 neutral 值。报告中必须同时写出每个 reference
的语义，不能把 reference 错称为绝对无组件。

所有消融继续使用相同的 frozen main trajectories、dense/adaptive probe bank 和
split；只允许离线替换规则维度，不重新采样主轨迹。对 adaptive winner 替换整个
`probe` reference 时，会同时消融触发类型、阈值、cooldown 与 fallback。

## 6. 8×A100 时间预算

以下是“全部 4 个模型、全部预注册 seed、全部 3 个 benchmark”的 Governor v2
collection 与离线选择，不包含需要重新生成主轨迹的 related-work 方法。总计
3,648 条 main trajectories，矩阵为 126 个环境级 stage（54 development +
72 confirmation）。

在模型已缓存、无排队、8×A100-80GB、NVLink、prefix caching 开启的条件下：

| 阶段 | 预计时间 |
|---|---:|
| 服务启动与三题 smoke | 0.2–0.4 h |
| frozen main generation | 1.2–2.0 h |
| interval-64 simple@32 bank | 2.0–3.2 h |
| teacher-forced entropy + event-only补 probe | 0.5–1.0 h |
| CPU sweep/select/evaluate（可与 GPU 重叠） | 0.3–0.8 h |
| **流水线总墙钟** | **4.5–7.0 h** |

32B BF16 使用 2×A100-80GB tensor parallel；其余卡运行独立 7B/8B replica。这个
估计包含约 10–15% 的重试余量，但必须先用每模型三题 smoke 校准实际吞吐和平均
event 数。A100-40GB 上 32B 需约 4 卡且并发下降，预计 6.5–9.5 h。若还要加入
CGRS/TALE 等会重新生成轨迹的完整 related-work 复现，应单独
排期，不能算进上述时间。

服务端最大上下文按模型配置冻结：Qwen3-8B 为 40,960（容纳 32,768 输出及 prompt
余量），三个 DeepSeek distill 模型为 49,152。Qwen3 不使用 YaRN 或额外 RoPE
scaling，避免为了统一 server flag 改变模型行为。

多 replica 执行时，`run_matrix.py` 支持按完整 environment 分片，并允许覆盖服务
地址；同一 environment 的 main/dense/adaptive 不会被拆开。例如四个同模型 replica
分别使用 `--shard-index 0..3 --shard-count 4 --url http://localhost:1800X/v1`。
development 阶段建议 4 卡服务 DeepSeek-7B、4 卡服务 Qwen3-8B；规则冻结后再重排
confirmation，其中 32B 占 2×A100-80GB。

## 7. 验证

```bash
python -m unittest \
  benchmark.FalseConsensus.governor_v2.tests.test_governor_v2 -v
```

测试覆盖精确/可复现切分、小数据集策略、统一规则格式、规则 ID 唯一性、七维
one-at-a-time 与 \(2^7\) factorial、probe 端点策略、滑动 switch window、
probe token 成本，以及开发/确认矩阵的角色隔离。

服务器启动和中断恢复步骤见 `VAST_RUNBOOK.md`；从空机器完成 8×A100 全流程、
三点 Pareto 冻结、报告和 GitHub 发布的 agent goal 见
`A100_8GPU_AGENT_GOAL.md`。32B 模型正式运行预注册为 2×A100-80GB、tensor
parallel 2；量化或 CPU offload 结果不能作为等价确认实验。
