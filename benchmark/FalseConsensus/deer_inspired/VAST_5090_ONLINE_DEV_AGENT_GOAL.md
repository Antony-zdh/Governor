# GOAL：在单张 Vast RTX 5090 上完成 BF16 Online DEER-inspired Dev 实验

你就是运行在 Vast RTX 5090 实例上的主执行 agent。你直接负责本机代码、模型服务、
实验、监控、恢复、分析和交付；不存在 SSH 到另一台机器、控制远程 tmux agent，
或把任务交给另一个 agent 的步骤。不要在启动作业后提前结束。只有在线实验完整、
验收通过、报告和原始数据可复现且已经持久化后，任务才算完成。

本任务不是冻结轨迹 replay。仓库已经包含 deployment-style online controller、
reference、配置、CPU 测试、汇总和报告入口。你必须先 pull 最新 main、审查并复验
这些实现，然后执行真正的 deployment-style online 实验：从题目 prompt 开始在线
生成主推理；达到 1024 个 committed-main
tokens 后，遇到符合调度条件的 `Wait` 时现场 probe，现场生成 verification branch；
branch 通过则提交答案；失败时保留 verification reasoning 作为有价值的在线思考，
只丢弃 Stage-2 trial answer，并从保留的 verification context 继续。禁止把既有
frozen trajectory 的未来 suffix 拼接到在线输出中。

## 0. 自主执行与不阻塞原则

负责人不会持续在线。除真正无法由本机 agent 解决的硬阻塞外，不要中途询问用户。
采用可审计、可恢复、最保守的方案持续推进：

1. 先检查，再安装；全部依赖放在独立 venv，不污染系统环境。
2. 普通错误按“代码/参数 → 依赖/版本 → 服务 → 显存 → 网络/磁盘”定位。
3. 请求失败使用相同 prompt、seed 和参数重试，不能通过换 seed 获得成功样本。
4. OOM 时只降低 vLLM `max-num-seqs`、collector workers 或并发；不得改模型、
   BF16、cap、prompt、threshold、seed、采样参数或题目。
5. 每题使用原子 JSON，可断点续跑；不要删除有效结果或用覆盖掩盖设置变化。
6. 长任务必须在本机 tmux 中运行并写日志；每 10–15 分钟主动检查 GPU、进度、
   服务健康和磁盘。
7. 将进度、异常和恢复写入独立 runtime `STATUS.md`，但不要为了汇报而暂停。

只有以下情况可形成最终 blocker：RTX 5090 不可用；BF16 两个公开模型经多种官方
方式仍无法获取；磁盘不足且无其他持久盘；当前 driver/CUDA 无法运行任何支持
Blackwell 的正式 vLLM；或 GitHub 无写权限导致最终结果无法推送。即使发生 blocker，
也要先完成所有不依赖该条件的代码、测试、清单和分析准备，只提交一次包含证据和
唯一解除动作的 blocker。

## 1. 科学定位与隔离边界

本实验是论文的独立 DEER-inspired 加分项，不替代、重选或追溯修改已有 Governor
Pareto sweep。

必须遵守：

- 不修改现有 Pareto candidate pool、筛选门槛、frozen rules、Train/Dev Pareto
  图、候选保留/淘汰状态或原 Governor 报告结论；
- 新实现放在 `benchmark/FalseConsensus/deer_inspired/`；
- 新结果放在
  `benchmark/FalseConsensus/results/deer_inspired/online_dev/`；
- runtime、模型 cache、venv 和临时文件不能写入上述结果目录，也不能提交进 Git；
- 不修改或覆盖：
  - `benchmark/FalseConsensus/results/governor_v2/`
  - `benchmark/FalseConsensus/results/related_work/full/`
  - `benchmark/FalseConsensus/results/stage10_rule_funnel_v2/`
  - 现有 Pareto figures/results；
- 已有 frozen DEER、fast-path-only replay 和 Governor Pareto 结果只作为只读比较；
- 本轮只做 exploratory Dev evaluation，不根据结果修改阈值或再 sweep；
- 禁止读取或调用 Test/confirmation，禁止使用 seeds 45/46/47；
- 禁止读取 Train 题目进行本轮 online collection。

如果仓库中存在以下只读背景文件，先完整阅读；若起始 commit 尚未包含它们，则以本
GOAL 的冻结规则为准，不要因此停下来询问：

- `benchmark/FalseConsensus/report/deer_inspired_branch_and_commit_design_2026-07-28.md`
- `benchmark/FalseConsensus/results/deer_inspired/fast_path_only_replay/report.md`
- `benchmark/FalseConsensus/results/deer_inspired/fast_path_only_replay/summary.json`
- `benchmark/FalseConsensus/related_work/deer.py`
- `benchmark/FalseConsensus/related_work/configs/deer.json`
- `benchmark/FalseConsensus/governor_v2/protocol.json`
- `benchmark/FalseConsensus/governor_v2/generated/split_manifest.json`

## 2. 固定实验范围

协议版本预期：

```text
governor-v2-preregistered-2026-07-27.10
```

模型及精确 revision：

```text
deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
916b56a44061fd5cd7d6a8fb632557ed4f724f60

Qwen/Qwen3-8B
b968826d9c46dd6066d109eabc6255188de91218
```

正式模型必须使用原始 BF16 权重：

- 不得使用 AWQ、GPTQ、FP8、INT8、bitsandbytes、GGUF、MLX 或其他量化版本；
- 不得 CPU offload；
- 不得换同名社区模型；
- 两个模型在单张 5090 上依次服务，不要求同时驻留。

正式实验只使用一个 development seed：

```text
42
```

seed 42 是本轮唯一 formal seed。43/44 不进入 formal collection、aggregate 或结果
选择；45/46/47 仍属于不可读取的 Test/confirmation。formal runner 收到
`base_seed != 42` 必须立即失败。

仅使用 Dev problem-level split：

| Benchmark | 每个 seed 的 Dev 题数 | 生成 cap |
|---|---:|---:|
| MATH500 | 100 | 16,384 |
| AMC23 | 8 | 16,384 |
| AIME24 | 6 | 32,768 |

每个模型共 `100+8+6 = 114` 条；两个模型共 228 条/方法。两个方法总计 456 条。

必须硬校验：

- 每个 model × benchmark × seed 的 problem ID 与 split manifest 完全一致；
- formal collector 接收到任何非 Dev ID 时立即失败；
- 每方法总数不等于 228、或两个方法合计不等于 456 时不能开始正式汇总；
- GSM8K、Llama-8B、32B、Train、Test 全部不在本任务范围。

## 3. 必须运行的两个 Online 方法

### 3.1 主方法：`deer_inspired_online_v1`

这是本任务最优先、必须完成的方法。

冻结参数：

```json
{
  "trigger": "exact DEER Wait transition",
  "minimum_committed_main_tokens": 1024,
  "dense_stage1_attempts": 10,
  "post_dense_min_probe_gap_tokens": 512,
  "max_stage1_attempts": null,
  "main_temperature": 0.6,
  "main_top_p": 0.95,
  "trial_temperature": 0.0,
  "trial_top_p": 1.0,
  "trial_output_cap": 20,
  "qwen_require_think_close_all_trials": true,
  "branch_threshold_strict": 0.97,
  "fast_threshold_strict": 0.995,
  "verification_cue_template": "\\nCandidate answer: \\\\boxed{<ANSWER_A>}\\nI will quickly verify within 64 tokens whether this answer satisfies every requirement of the problem.",
  "verification_budget": 64,
  "verification_min_gap_tokens": 512,
  "qwen_verification_stop_before_think_close": true,
  "verification_temperature": 0.6,
  "verification_top_p": 0.95,
  "commit_threshold_strict": 0.99,
  "confirmation_depth": 2,
  "require_answer_equivalence": true,
  "formal_readout_after_commit": false
}
```

所有比较使用严格 `>`，不能偷偷改成 `>=`。

Stage-1 trial probe 必须忠实复用 pinned DEER 的 answer inducer、20-token cap、
greedy sampling、logprob 提取和模型对应的聚合方式：

- prefix 末尾追加：

  ```text
  \n**Final Answer**\n\boxed
  ```

- 输出 cap 20，greedy，`logprobs=1`；
- 跳过第一个生成 token 后计算 confidence；
- DeepSeek 使用 `avg1`：token max probability 的算术平均；
- Qwen3 使用 `avg2`：token max probability 的几何平均；只有最后生成 token
  精确解码为 `</think>` 时 confidence 才有效，否则强制为 0；
- DeepSeek 使用官方 boxed-close stop tokens；Qwen3 使用官方
  `stop=["</think>"]`；
- 两个模型的 trial 都必须包含完整、平衡、非空的 `\boxed{...}`。Qwen3 还必须在
  20-token cap 内完成 `</think>`；缺少该 token 时即使 boxed answer 和 answer-token
  confidence 看似有效也不能 fast、不能 branch；
- 该 Qwen gate 同时适用于 Stage-1 和 Stage-2；
- 语义必须与 `related_work/deer.py` 及 pinned upstream commit
  `c9dd19fbffa27f841cfe47502d015b63811b4d1b` 一致；
- 保存完整 trial text、解析答案、逐 token logprob、confidence、finish reason、
  prompt/output tokens、latency 和 retry。

### 3.2 对照：`deer_online_reference`

当前仓库里的主 DEER 结果是 frozen-trajectory reproduction。为了判断部署化本身和
新控制器的影响，必须在相同 Dev ID、模型、seed、主采样和 online engine 上运行一个
online reference：

- 同样在 `Wait` 处在线触发，保持官方最多 10 次；
- DEER threshold 严格 `confidence > 0.95`；
- trial 设置和模型分支与官方 DEER 相同；
- Qwen3 reference 必须保留相同的官方 `avg2 + </think>` gate；
- 达到 threshold 后使用原 DEER formal readout：

  ```text
  clean prefix + "\n</think>\n\n"
  ```

- readout cap 4096，greedy；
- 只有明确完成的 boxed answer 才有效，截断、空答案或无效格式按错误交付；
- 不启用 fast path，不启用 verification branch。

这不是阈值 sweep，也不允许增加 `.95/.97` 之外的新 operating point。若时间受限，
先完整完成主方法，再完成 online reference；最终验收要求二者都完成。

## 4. Online Controller 的精确定义

### 4.1 主推理必须在线生成

每题从原始问题和项目现有 chat template 开始，不能读取 frozen `full_text` 作为主
生成内容。主推理使用：

```text
temperature = 0.6
top_p = 0.95
main_seed = base_seed + problem_id
```

两个 online 方法必须共用同一个主生成 engine、prompt、stop 语义和 seed policy。
所有请求必须使用独立派生 seed，不能意外消耗其他 request role 的 seed。Stage-1 和
Stage-2 trial 始终是旁路，不污染 main；verification reasoning 则按本协议有意合并
进主上下文，因此 branch 失败后的后续路径允许、也预期与 reference 不同。

建议稳定派生 seed：

```text
stable_hash(protocol, model, benchmark, base_seed, problem_id,
            candidate_id, request_role) modulo valid seed range
```

其中 `request_role` 至少区分：

```text
main, stage1_trial, verification_reasoning, stage2_trial, reference_readout
```

实际 seed 必须逐 request 记录。

### 4.2 `Wait` 触发、min-token 和稀疏调度

只使用官方 DEER 的 case-insensitive whole-word exact `Wait` transition，不加入
therefore/thus/hence、entropy 或其他 marker。

online main request 应在生成 `Wait` 时暂停，并明确知道 stop 是 `Wait` 而不是 EOS。
可以使用 vLLM 的 `include_stop_str_in_output`，但必须通过测试证明：

- clean prefix 恰好位于触发 `Wait` 之前；
- `Wait` 不会重复提交或丢失；
- probe/branch 输出从不混入 clean prefix；
- 继续推理时只提交一次 `Wait`；
- prompt token 和 completion token 计数没有双计；
- 达到 cap 时 native main segments 与已保留 verification outputs 的累计模型生成
  token 不超过对应 benchmark cap。

主方法的触发调度严格定义如下：

1. `committed_main_tokens < 1024`：检测并记录 `Wait`，但不 probe、不排队；提交
   `Wait` 一次并继续。自然完整回答仍可在 1024 前正常结束。
2. 从 1024 起，前 10 次**实际 Stage-1 probe attempts**保持 dense：每个自然
   `Wait` 都 probe。1024 前跳过的 `Wait` 不计入这 10 次。
3. 第 10 次实际 attempt 之后进入 sparse mode，不设 Stage-1 总次数上限。仅当当前
   `Wait` 的 committed-main token position 满足
   `position - last_actual_stage1_probe_position >= 512` 时才 probe。
4. sparse mode 中距离不足的 `Wait` 只记录
   `skip_reason=post_dense_gap_lt_512`，提交一次并继续；不累计、不开延迟 probe。
5. 512 距离按 committed-main output token position 计算，不含任何 trial、
   verification、controller cue、readout 或 prompt token；不得用字符距离近似。
   这是为了让 trigger schedule 只由自然主推理进度决定。
6. 成功 commit、自然结束或达到 benchmark cap 才终止调度。不得重新引入隐藏的
   10 次或其他 hard maximum。

`deer_online_reference` 不使用这一调度；它必须保持官方“从第一个 Wait 开始、最多
10 次”的行为。报告中必须把 reference 与主方法的 trigger schedule 差异列为方法
差异，不能归因于 branch controller 一项。

### 4.3 主方法状态机

在第 `i` 个 `Wait` 前保存 `clean_prefix`，运行 Stage-1 probe 得到：

```text
(answer_a, confidence_a, validity_a)
```

`validity_a` 至少要求：

- parsed answer 非空；
- answer inducer 后存在完整、平衡的 `\boxed{...}`；
- trial 没有 request error；
- 对被纳入 confidence 的每个 answer token 都有完整 logprob；
- finish reason 合法，且不是因 cap 截断了 boxed answer；
- Qwen3 最后生成 token 必须精确为 `</think>`；
- validity 不能读取 target、ground truth 或 correctness。

严格按以下顺序：

```text
if not validity_a:
    discard Stage-1 output
    commit exactly one "Wait"
    continue online main generation

elif confidence_a > 0.995:
    FAST COMMIT answer_a
    stop the problem

elif confidence_a > 0.97:
    if no prior verification branch
       OR current_main_position - last_verification_branch_position >= 512:
        enter retained verification branch
    else:
        record skip_reason=verification_gap_lt_512
        discard Stage-1 output
        commit exactly one "Wait"
        continue online main generation

else:
    discard Stage-1 output
    commit exactly one "Wait"
    continue online main generation
```

### 4.4 Verification branch

branch 从 `clean_prefix` 创建，并把 Stage-1 的候选答案作为**不可信候选**显式提供。
这里有意选择 candidate-conditioned outcome verification，而不是重新审查整段推理：

严格来说，这已不是“失败即全部回滚”的纯 disposable branch，而是 retained
verification branch：verification reasoning 总是 merge，Stage-2 probe 仍是
disposable。实现、manifest 和报告必须使用这一准确描述。

```text
branch_prefix =
    original_chat_prompt
    + clean_prefix
    + "\nCandidate answer: \boxed{<ANSWER_A>}"
    + "\nI will quickly verify within 64 tokens whether this answer satisfies every "
      "requirement of the problem."
```

`<ANSWER_A>` 必须替换为 Stage-1 的 raw parsed answer，不能包含 target/ground truth；
同时记录替换前 template、替换后 cue 和其 token 数。使用主模型采样设置生成最多
64 个 verification tokens。verification 只核对候选答案是否满足题目要求，不要求
重做整题，也不把自然语言 `verified` 当作信号。cue 和 verification reasoning 在
生成成功后即作为 committed verification segment 合并进主上下文；无论 Stage-2
最终 pass/fail，都不回滚这部分。

Qwen3 的 verification reasoning request 使用 `stop=["</think>"]`，且不得把该
stop string 写入 branch context；否则随后 Stage-2 会落在已闭合的 thinking phase
之外。Stage-2 trial 才负责生成 boxed answer 并以 `</think>` 完成 gate。即使
verification request 因该 stop 提前结束，实际产生的 token 和 stop reason 仍完整
计费、记录。

两次实际 verification branch 至少间隔 512 个 committed-main tokens。该 cooldown
从 branch 被实际创建的位置开始计算，无论 branch pass/fail；被 cooldown 跳过的
Stage-1 候选不能排队。`c1>0.995` 的 valid fast path 优先于此 cooldown，仍可立即
commit。512-gap 只限制昂贵 branch，不改变 Stage-1 Wait scheduler，也不设置 branch
总次数上限。

然后在 verification reasoning 后追加相同 DEER answer inducer，运行 Stage-2 probe，
得到：

```text
(answer_b, confidence_b, validity_b)
```

`validity_b` 使用与 Stage-1 相同的非空、balanced boxed、完整 logprobs、合法
finish reason 和模型特定规则；Qwen3 必须在 Stage-2 trial 最后生成
`</think>`。缺少 gate 时不能通过数学等价检查“补救”为 commit。

只有以下条件全部满足才 commit：

```text
validity_b
AND confidence_b > 0.99
AND robust_math_equivalent(answer_a, answer_b)
```

通过：

- 交付 `answer_b`；
- 不再生成 formal readout；
- committed verification reasoning 和两次 probe 都作为已花费成本记录。

失败：

- 保留 candidate cue 和 verification reasoning；
- 丢弃 Stage-2 answer inducer 与 Stage-2 trial output 的上下文影响，但其
  output/prompt token、latency 和调用次数仍计入公平成本；
- 从 `original_chat_prompt + clean_prefix + candidate cue + verification reasoning`
  继续 online main，不回到 `clean_prefix`，也不自动追加 `Wait`；
- 清空候选，继续 online main；
- 下一个自然 `Wait` 交给 4.2 的 dense/sparse scheduler 判定；
- 不设置 stage-1 attempt 总数上限。

如果 verification request 本身在 exact retries 后仍失败、没有可保留的有效输出，
才回到 `clean_prefix`、提交一次 `Wait` 并继续；这属于基础设施失败恢复，不是正常
branch-fail 语义。

禁止通过检测普通文本里的 `"verified"` 直接提交。自然语言 marker 只能作为日志，
不是 commit 条件。

### 4.5 自然结束与 cap

若 main 在触发 `Wait` 之前自然结束：

- 使用项目现有 answer extractor 解析完整输出；
- 按严格数学判分；
- 不再补 probe/readout。

生成 cap 使用：

```text
committed_reasoning_model_tokens =
    native_committed_main_output_tokens
    + retained_verification_output_tokens
```

controller-inserted cue 不属于模型生成 cap，但必须计入实际 context-window budgeting；
Stage-1/Stage-2/readout 是辅助成本，不消耗 main generation cap。若累计
`committed_reasoning_model_tokens` 到 cap：

- 标记 `capped/right_censored=true`；
- 没有有效已提交答案则交付空答案并计错；
- 不得事后增加 cap、补用 frozen future answer 或重采样“直到答对”。

## 5. 公平成本与逐题记录

每个 per-problem JSON 必须完整记录身份、状态转换和全部调用。至少包含：

- schema/protocol/method/config hash；
- model ID、40-hex revision、dtype、server command；
- benchmark、seed、problem ID、split；
- problem、target、chat-template hash；
- 所有 main segments 的 text、seed、finish/stop reason、prompt/output tokens、latency；
- 每个 Stage-1 trial 的完整 logprobs 和重算 confidence；
- 每个 observed `Wait` 的 committed-main token position、是否 probe、dense/sparse
  mode、距上次实际 probe 的 token gap 和 skip reason；
- 每个 verification branch 的 cue、reasoning text、seed、64-token cap、实际 token；
- 每个 Stage-2 trial 的完整 logprobs、答案、confidence；
- 两答案的 raw 值、normalized 值、数学等价结果；
- fast/branch/continue/commit/fail 的明确状态和 candidate ID；
- verification segment 是否合并、合并后的 main-context hash；
- discarded Stage-1/Stage-2 trial 也必须完整保留；
- delivered answer、正确性、自然结束/capped；
- 所有 retry/error。

公平生成成本：

```text
all_generated_tokens =
    committed_main_output_tokens
    + every_stage1_trial_output_token
    + every_verification_reasoning_output_token
    + every_stage2_trial_output_token
    + reference_readout_output_tokens
```

其中 reference readout 只存在于 `deer_online_reference`。

verification reasoning 即使已合并进 main context，也只能在上述公式中计数一次，
不得同时算入 `committed_main_output_tokens` 和
`every_verification_reasoning_output_token`。另报告：

```text
committed_reasoning_context_tokens =
    committed_main_output_tokens
    + retained_verification_output_tokens
    + controller_inserted_candidate_cue_tokens
```

该视图反映实际保留的推理上下文长度；controller cue tokens 不能伪装成免费。Stage-2
失败输出仍必须计费，但不进入 committed context。prompt/prefill tokens 不加入
`all_generated_tokens`，但单独完整报告：

```text
all_prompt_tokens =
    every_main_prompt_token
    + every_trial_prompt_token
    + every_verification_prompt_token
    + every_readout_prompt_token
```

另外报告：

- main-only token saving；
- fair all-generated-token saving；
- prompt/prefill volume；
- wall-clock latency；
- auxiliary calls；
- fast rate；
- branch enter/pass/fail rate；
- verification-gap skip rate；
- average stage-1 attempts；
- 1024 前跳过的 `Wait` 数、dense attempts、sparse-mode probes、512-gap skip 数；
- Stage-1 attempts 的均值、P50/P90/P95/max，按 model × benchmark 分解；
- invalid trial rate；
- capped rate。

token saving 的 paired full baseline 使用同一 model × benchmark × seed × problem ID 的
既有完整 main trajectory。由于 online controller 的多请求采样路径可能与既有
single-request baseline 不完全相同，报告必须明确这一限制，不能声称 counterfactual
完全相同。

## 6. 建立本机可恢复工作区

Git 和 tmux 预计已经存在；不要假设 vLLM、模型、Python 环境、Pandoc 或 LaTeX
存在。

先确定容量最大的持久盘。推荐：

```bash
export GOV_WORK=/workspace/deer-online-dev
export GOV_ARTIFACTS="$GOV_WORK/artifacts"
export HF_HOME="$GOV_WORK/huggingface"
export XDG_CACHE_HOME="$GOV_WORK/cache"
mkdir -p "$GOV_WORK" "$GOV_ARTIFACTS" "$HF_HOME" "$XDG_CACHE_HOME"
```

若 `/workspace` 不是持久盘或空间不足，选择实际持久盘并在环境清单记录。不要使用
未验证的临时根目录存放唯一结果。

保存：

```bash
date -Is
uname -a
nvidia-smi -L
nvidia-smi --query-gpu=index,name,memory.total,memory.free,driver_version \
  --format=csv,noheader
free -h
df -h
git --version
tmux -V
```

硬件门禁：

- 正式 GPU 必须是单张可用 RTX 5090，显存约 32GB；
- GPU 不能处于错误状态；
- 正式运行期间不得与无关进程争抢显存；
- 建议持久盘至少保留 80GB；
- 若发现无关 GPU 进程，不杀、不 reset，记录并等待/完成 CPU 准备。

## 7. Git 工作区与版本固定

优先使用启动时已有 repo；不存在才 clone。若已有工作树不干净，不要 reset 或删除
用户文件；从固定 commit 创建独立 worktree。

```bash
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  export GOV_REPO="$(git rev-parse --show-toplevel)"
elif [ -d "$GOV_WORK/Governor/.git" ]; then
  export GOV_REPO="$GOV_WORK/Governor"
else
  git clone https://github.com/Antony-zdh/Governor.git "$GOV_WORK/Governor"
  export GOV_REPO="$GOV_WORK/Governor"
fi

cd "$GOV_REPO"
git fetch --all --tags --prune
export TARGET_COMMIT="${TARGET_COMMIT:-$(git rev-parse HEAD)}"
git cat-file -e "$TARGET_COMMIT^{commit}"
```

记录 `TARGET_COMMIT` 后，本轮 collection 中途不得切换。创建专用分支，例如：

```text
deer-inspired-online-dev-vast-20260728
```

如果当前 repo 不适合直接建分支，创建 clean worktree。不要 merge main，不改写其他
branch，不 force-push。

正式 collection 前记录：

- `git rev-parse HEAD`
- `git status --short`
- `git remote -v`（不得输出 credential）
- protocol/config/split manifest SHA-256
- input dataset hashes
- source code tree hash

## 8. Python、vLLM 与 BF16 模型

优先 Python 3.10/3.11 独立 venv。Blackwell 需要兼容的 driver、CUDA、PyTorch 和
vLLM；先检查现有环境，缺失才安装。

```bash
python3 -m venv "$GOV_WORK/venv"
source "$GOV_WORK/venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel
```

让 vLLM 安装其兼容的 PyTorch/CUDA wheel。若默认 wheel 不支持 RTX 5090，在新的
编号 venv 中采用 vLLM 官方支持 Blackwell 的安装方式；不要在同一个 venv 反复覆盖
造成不可审计环境。不得通过量化绕过兼容问题。

至少安装：

```text
vllm
openai
transformers
huggingface_hub
numpy
pandas
scipy
statsmodels
matplotlib
seaborn
sympy
latex2sympy2
word2number
pytest
```

项目按现有方式加入 Python path 或 editable install。保存 `pip freeze`、torch/CUDA、
vLLM、transformers、openai 版本和 GPU capability。

下载精确 revision，支持断点续传：

```bash
hf download deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  --revision 916b56a44061fd5cd7d6a8fb632557ed4f724f60

hf download Qwen/Qwen3-8B \
  --revision b968826d9c46dd6066d109eabc6255188de91218
```

记录 snapshot path、revision、文件数、目录大小和 config/tokenizer/weight shard
完整性。

每次只服务一个模型。建议从以下保守设置开始，并根据实际 vLLM 参数名调整：

```text
--dtype bfloat16
--max-model-len 34816
--gpu-memory-utilization 0.90
--max-num-seqs 4
--enable-prefix-caching
```

必须使用 snapshot 的精确路径并提供正式 model ID 作为 served name。OOM 时先把
`max-num-seqs` 和 collector workers 降到 2 或 1；不能改变 BF16 或 cap。AIME 的
32,768 generation cap 加 prompt/branch 后必须经过精确 tokenizer context-budget
检查，不能让 request 靠 context overflow 失败。

## 9. 已有实现的验收与必要修复

pull 后应已存在：

```text
benchmark/FalseConsensus/deer_inspired/
  __init__.py
  online_controller.py
  online_reference.py
  common.py
  aggregate.py
  report.py
  configs/
    online_dev_v1.json
  tests/

benchmark/FalseConsensus/results/deer_inspired/online_dev/
  runtime/
  deer_inspired_online_v1/
  deer_online_reference/
  aggregate/
```

可以复用 `related_work/common.py`、DEER confidence/parser、Governor chat template、
split loader、grader和metrics，但不能修改 frozen DEER 的语义来让新方法通过。

不要另起一套实现或退回 frozen replay。先运行 §9.1 和 §10 的门禁；若发现真实缺陷，
在当前模块中做最小、可测试、协议兼容的修复并提交。已有实现必须具备：

- per-problem 原子写入；
- identity/config hash 检查；
- 完整结果自动 skip，损坏/不完整结果隔离为 `.corrupt`，不能静默覆盖；
- retry exact request；
- model/server readiness check；
- `--problem-ids` 或等价 smoke 子集；
- formal mode 硬锁 Dev IDs；
- formal mode 禁止 force threshold、force branch、量化和 Test；
- progress manifest：expected/observed/missing/error；
- restart 后结果数量和 config 一致；
- 所有分段/分支 token accounting 可由原始记录重新计算。

### 9.1 必须覆盖的单元测试

至少测试：

1. `0.97`、`0.995` 和 `0.99` 边界全部使用严格 `>`；
2. 无效 Stage-1 answer 不 fast、不 branch；
3. `c1 > .995` fast 优先于 branch；
4. `.97 < c1 <= .995` 进入 branch；
5. `c2 > .99` 但答案不等价时失败；
6. 答案等价但 `c2 <= .99` 时失败；
7. `.97<c1<=.995` 但距上次 branch 小于 512 main tokens 时不进入 branch；
8. `c1>.995` fast path 不受 verification cooldown 阻挡；
9. verification cue 精确包含 raw `answer_a`，但不包含 target/ground truth；
10. Qwen verification 若生成 `</think>`，该 stop 不进入 branch context，随后
    Stage-2 仍处于正确 thinking boundary；
11. verification 修正出不等价 `answer_b` 时不能 commit；
12. branch 失败后 cue+verification reasoning 留在主 prefix，Stage-2 inducer/output
    不进入；
13. branch 成功后不生成 formal readout；
14. discarded Stage-2 output 仍计入公平成本，retained verification 不双计；
15. `Wait` 恰好提交一次；
16. 1024 token 前的 `Wait` 被记录但不 probe，也不计入 dense 10 attempts；
17. 第 1–10 次实际 attempt dense，第 11 次起只有 gap `>=512` 才 probe；
18. sparse skip 不排队，后续距离从最后一次**实际 probe**计算；
19. 主方法没有 Stage-1 hard maximum，reference 仍严格最多 10 次；
20. cap 跨多 main segments 正确累计；
21. Qwen3 主方法完整 boxed answer 但无 `</think>` 时 Stage-1 validity 为 false；
22. Qwen3 Stage-2 缺少 `</think>` 时即使答案等价、`c2>.99` 也不能 commit；
23. Qwen3 reference 保留官方 `</think>` confidence gate；
24. DeepSeek avg1 与 Qwen avg2 手算 fixture；
25. prompt/completion 边界 `\boxed` + `{12}` 正确解析；
26. unbalanced/截断 boxed answer 即使 confidence 高也无效；
27. resume 不重复请求完整题目；
28. formal Dev guard 拒绝 Train/Test ID；
29. 两方法的 main seed schedule 一致，branch seed 不污染 main seed。

运行所有已有 related-work tests 和新 tests；不得通过 skip 或降低断言“修复”失败。

## 10. GPU Smoke 门禁

正式运行前，每个模型完成以下 smoke：

1. BF16 endpoint `/v1/models` 和一条简单 completion；
2. 手工重算一个 Stage-1 confidence，与 collector 记录误差不超过 `1e-9`；
3. natural-end case；
4. low-confidence continue case；
5. fast-commit case；
6. branch-pass case；
7. branch-fail-retain-verification-and-discard-stage2 case；
8. cap/context-budget case；
9. 进程中断后 resume case。
10. 主方法真实 Qwen trial 在不生成 `</think>`、但 boxed answer 和 logprobs 完整时
    被 validity 拒绝；
11. 构造超过 10 次 Wait 的在线 smoke，证明第 11 次后执行 512-token sparse
    scheduler，且不存在隐藏 hard cap。

可以在独立 `runtime/smoke/` 中使用 force mode 构造状态分支，但：

- force 参数不能进入 formal config；
- formal runner 检测到 force 参数必须失败；
- smoke 结果不能混入正式 aggregate；
- 至少一个 branch smoke 应来自真实模型调用和真实 logprobs。

已有 frozen 数据中下列 Dev cases 曾出现 `.97 < c <= .995`，可以优先尝试真实 branch
smoke；online 路径可能不同，所以不能把“不再触发”当作错误：

```text
Qwen3-8B: MATH500 seed 42 problem 1
DeepSeek-7B: AMC23 seed 42 problem 10
```

smoke 后运行：

```bash
python -m compileall benchmark/FalseConsensus/deer_inspired
pytest -q benchmark/FalseConsensus/deer_inspired/tests
pytest -q benchmark/FalseConsensus/related_work/tests
git diff --check
```

只有 smoke、tests、context budgeting 和 BF16 manifest 全部通过，才能开始正式
228题/方法。

## 11. 正式执行顺序与监控

为减少模型重复加载，按模型运行：

1. 启动 DeepSeek BF16 server；
2. DeepSeek `deer_inspired_online_v1` 的 3 个 seed-42 benchmark 环境；
3. DeepSeek `deer_online_reference` 的 3 个 seed-42 benchmark 环境；
4. 验证114+114条、关闭自己启动的 DeepSeek server；
5. 启动 Qwen3 BF16 server；
6. Qwen3 `deer_inspired_online_v1` 的 3 个 seed-42 benchmark 环境；
7. Qwen3 `deer_online_reference` 的 3 个 seed-42 benchmark 环境；
8. 验证114+114条、关闭自己启动的 Qwen3 server；
9. 全量 aggregate、bootstrap、报告和审计。

若 online reference 比预期慢，不能改变方法。主方法优先完成，但最终继续直到 reference
也完整。

将 server、runner、monitor 放在不同 tmux window。每 10–15 分钟检查：

- `nvidia-smi` utilization、显存、温度和功耗；
- endpoint health；
- 每方法/模型/benchmark/seed 完成数；
- 最近结果和日志更新时间；
- error/retry/context overflow；
- 磁盘余量。

若 15 分钟无新结果且 GPU 空闲，立即诊断。若 GPU 持续繁忙而单题很长，检查当前
请求、cap和日志后继续，不要误杀。只管理自己启动的 PID，禁止使用广泛 `pkill`
或 reset GPU。

开始正式主方法10题后，用实测题/分钟、平均主token和branch rate更新 ETA 到
`runtime/STATUS.md`，但不中断任务。

## 12. 完整性审计

每个方法必须恰有：

```text
2 models × 3 benchmarks × 1 seed = 6 environments
228 per-problem outcomes
```

两个方法合计456条。逐项审计：

- 无重复 identity；
- 无 Train/Test IDs；
- 无缺题；
- model revision、dtype、config hash 一致；
- 没有量化或 CPU offload；
- 每条有终态：natural / fast / branch_commit / reference_readout / capped；
- 所有 branch 有 pass/fail 和完整成本；
- 所有 confidence 可从 logprobs 重算；
- all-generated token 可从底层调用重算；
- prompt token 单独可重算；
- request error、context overflow、null finish 均为0；若发生过且成功重试，retry
  历史仍保留；
- 不因答案错误删除或重跑样本；
- capped 样本保留并计入准确率；
- formal config hash 从第一题到最后一题不变。

生成机器可读 audit JSON，任何硬验收失败则返回非零。

## 13. 汇总、统计与报告

输出至少：

```text
benchmark/FalseConsensus/results/deer_inspired/online_dev/aggregate/
  per_problem.csv
  environment_metrics.csv
  dev_pooled.csv
  dev_macro.csv
  paired_comparisons.csv
  bootstrap.json
  audit.json
  summary.json
  report.md
  report.pdf
  artifact_manifest.json
```

统计口径：

- 每个 model × benchmark × seed；
- 本轮固定 seed 42，不做跨-seed pooled 或 seed variance 估计；
- benchmark 等权 macro，避免 MATH500 样本数主导；
- 10,000 次 paired stratified problem bootstrap：在每个 benchmark 内对相同 problem
  ID 的方法配对行有放回重采样，再对三个 benchmark 等权 macro；固定 bootstrap
  seed `20260728`；
- 比较：
  1. 新 online 方法 vs online DEER reference；
  2. 新 online 方法 vs existing full generation；
  3. online DEER reference vs frozen DEER；
  4. 新 online 方法 vs fast-path-only frozen replay；
- 非完全同路径的比较必须明确标记，不伪装严格 counterfactual。

报告至少解释：

- deployment-style online 与 frozen replay 的区别；
- fast、branch、verification pass/fail 的流程；
- accuracy、Δaccuracy、main-only saving、公平 saving、prompt volume、latency；
- model × benchmark 细分；
- confidence/正确率分桶；
- fast rate、branch enter/pass/fail、attempt 数；
- min-token 和 Wait scheduler 的 observed/probed/skipped 数、gap 分布及 probe 税；
- branch 成本是否被早停收益覆盖；
- Qwen/DeepSeek 的差异，以及缺少/生成 `</think>` 的 trial correctness 对比；
- capped/invalid/retry 诊断；
- paired uncertainty；
- 单 seed 不能估计 seed variance，AMC23/AIME24 样本很小，区间与结论必须标记为
  exploratory；
- 这只是 exploratory Dev，加分项而非原 Governor Pareto 替代品；
- 没有读取 Test，也没有根据结果改变阈值。

Markdown 用中文，结构清晰、解释充分但篇幅简洁。使用 Pandoc 生成 PDF，中文字体优先
Noto CJK；渲染后检查页数、文本可提取、表格没有明显截断。PDF 工具暂缺时自动安装
或使用用户目录工具，不得省略 PDF。

## 14. 产物持久化与 GitHub

不要提交模型、venv、HF cache、临时下载、巨大 server log 或 secret。必要时更新
`.gitignore`，但不能忽略正式 per-problem 数据、aggregate、报告、config、manifest、
audit 和必要日志。

至少形成两个可恢复 checkpoint：

1. online controller + tests + smoke/config；
2. 完整 raw results + aggregate + Markdown/PDF + audit。

每次 commit 前检查：

```bash
git status --short
git diff --check
git diff --cached --stat
```

只提交本任务文件，不卷入起始工作树中的无关修改。推送专用 branch；不 force-push，
不 merge main。若单文件超过 GitHub 限制，优先将正式 JSONL/CSV 做可复现的 zstd
压缩并保留 manifest/hash；不得静默丢弃 raw data。

最终重新 clone 或创建 clean worktree，从推送 commit 验证：

- tests；
- audit；
- artifact inventory/hash；
- report.md；
- report.pdf 可读取；
- raw row counts；
- 无 Test identity；
- GitHub branch 上 commit 可达。

GitHub 认证失败时完成本地 commits、bundle/压缩归档和 SHA-256，再形成一次性权限
blocker；不要因此丢失实验。

## 15. 时间预算与完成定义

北京时间目标完成时间：

```text
2026-07-29 00:00 Asia/Shanghai
```

该时间是加速目标，不是允许产出不完整结果的截止线。立即并行推进不争抢 GPU 的任务：

- 在独立 tmux window 同时做依赖/代码检查与两个模型的断点下载；
- 下载期间完成 controller、tests、manifest 和 smoke fixtures；
- 第一个模型 ready 后立即 smoke 并 collection，另一个模型继续下载；
- 第一模型运行期间准备 aggregate/report 模板；
- 不等待人工状态确认，不因跨过 0 点停止健康任务；
- 不得为赶时间删除 online reference、benchmark、Qwen gate、tests/audit，或改变任何
  冻结参数。

单张 5090、单 seed 的计划：

- 环境、模型下载与代码复验（并行）：0.5–1.5小时；
- GPU smoke：0.25–0.5小时；
- 主 online 方法：1.3–2.5小时；
- online DEER reference：0.7–1.5小时；
- aggregate、bootstrap、PDF、audit、push：0.5–1小时；
- 无重大兼容问题时总计约3–5.5小时。用前10题实测更新 ETA。

若明显更快，继续完成全部验收；若更慢，保持可恢复运行直到完成，不要停下来询问是否
继续。

任务只有同时满足以下条件才完成：

- BF16 两模型、三 benchmark、seed 42、Dev-only；
- `deer_inspired_online_v1` 228/228；
- `deer_online_reference` 228/228；
- 真正 online main/probe/branch，没有 frozen future suffix；
- thresholds、verification budget、prompt、sampling 和 caps 未事后改变；
- 原 Pareto sweep 未改；
- 全部 unit/GPU smoke/integrity tests 通过；
- raw data、aggregate、paired bootstrap、中文MD/PDF、audit和manifest齐全；
- Test 未读取；
- 结果在专用 Git branch 持久化并经过 clean-worktree复验。

最终回复必须给出：

1. pushed branch、commit SHA 和结果路径；
2. 两方法完整性计数；
3. 主结论：每模型及宏平均 accuracy/token saving；
4. fast/branch/pass/fail/capped 关键比例；
5. 与 online reference、frozen DEER、fast-only replay 的对比；
6. 实际 GPU/总 wall time；
7. tests/audit/PDF/GitHub 验收证据；
8. 所有仍存在的限制。

不要只回复“已启动”“正在 tmux 中运行”或“远端 agent 说完成”。持续执行、监控、
恢复和验收，直到上述终态真正成立。
