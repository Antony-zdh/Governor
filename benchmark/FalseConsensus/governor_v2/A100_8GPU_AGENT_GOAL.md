# Goal：在 8×A100-80GB 上完整执行 Governor v2、冻结三个 Pareto 策略并发布全部结果

你就运行在这台 8×A100-80GB 实验机上，并直接负责本机的全部实验。不存在需要
SSH 登录、控制另一台机器、驱动远程 tmux agent 或把任务转交给其他 agent 的步骤。
你的终点不是“启动作业”，而是完成
环境搭建、模型获取、smoke、development collection、Pareto sweep/selection、
confirmation、三套规则的全维消融、统计分析、Markdown/PDF 报告、原始数据归档和
GitHub 上传，并验证 GitHub 资产可访问且校验和一致。持续监视本机 tmux、GPU、日志和输出；
可恢复的故障要主动修复并续跑。只有全部验收项通过后才能宣布完成。

本 goal 所在 Git commit 由协调者在启动时提供为 `TARGET_COMMIT`。必须记录并固定该
commit；如果协调者没有给出 hash，先向其索取，不能悄悄使用一个不明确的 HEAD。

## 1. 科学边界：不可事后更改

唯一配置来源：

- `benchmark/FalseConsensus/governor_v2/protocol.json`
- `benchmark/FalseConsensus/governor_v2/generated/split_manifest.json`
- `benchmark/FalseConsensus/governor_v2/generated/development_matrix.jsonl`
- `benchmark/FalseConsensus/governor_v2/generated/confirmation_matrix_base64.jsonl`
- 本文件及同目录 `README.md`

预期协议为 `governor-v2-preregistered-2026-07-27.10`。若版本不同，停止并报告。

不可变设置：

- active benchmarks：MATH500、AMC23、AIME24；GSM8K 禁用。
- 题目级 split：
  MATH500=300/100/100，AMC23=24/8/8，AIME24=18/6/6。
- development models：
  `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`、`Qwen/Qwen3-8B`，
  seeds 42/43/44，只可读取 train+dev。
- confirmation：
  两个 development models 用 seeds 45/46/47；
  `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` 和
  `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` 只用 seed 45；
  全部只读取 test。
- capture cap：MATH500=16,384，AMC23=16,384，AIME24=32,768。
  5% 仅是预先选 cap 的设计目标，不是事后通过线。无论实现的 truncation rate
  是多少都如实报告，绝不据此升 cap、删题或重采样。
- sampling：temperature 0.6、top-p 0.95；主 seed 由矩阵固定。
- probe：frozen main trajectory；dense simple@32 从 token 64 起每 64 token；
  adaptive bank 使用预注册 event/entropy 设置。不得补 32-token offset bank。
- 正式模型均用 BF16。32B 必须 2×A100-80GB、tensor parallel 2。不得用量化、
  CPU offload、换模型或缩短 cap 冒充正式结果。
- test、Llama-8B、32B 不能参与 sweep、筛选、门槛修改或 cap 修改。
- test collection 必须发生在 `frozen_rules.json` 已写出并记录 SHA-256 之后。
  不得查看 test 后重选规则。

本轮必须从 development 的真正三目标非支配前沿选出三个互异 rule ID：

1. `conservative`：逐模型/逐 benchmark accuracy drop 分别不超过
   1.5/2.0 pp，至少 80% development 环境正节省；
2. `balanced`：不超过 2.5/3.0 pp，至少 80% 环境正节省；
3. `token_efficient`：不超过 4.0/5.0 pp，至少 70% 环境正节省。

主要排序量是 dev 环境总 decode-token saving 的第 20 百分位；另外两个 Pareto
目标是最小化最差 split-by-model 和 split-by-benchmark accuracy drop。
`select` 必须返回三个不同 ID。若某 profile 无互异合格点，任务不是成功：保存完整
前沿和诊断，通知协调者；不得放宽门槛、重复 rule ID 或利用 test 决策。

## 2. 建立可审计、可恢复的工作区

不要假设机器已有 Git、Python、vLLM、Hugging Face 模型、Pandoc、LaTeX、`gh`
或任何 Python 包。先检查，再安装缺失项。推荐目录：

```bash
export GOV_WORK=/workspace/governor-v2
export GOV_REPO="$GOV_WORK/Governor"
export GOV_ARTIFACTS="$GOV_WORK/artifacts"
export HF_HOME="$GOV_WORK/huggingface"
export XDG_CACHE_HOME="$GOV_WORK/cache"
mkdir -p "$GOV_WORK" "$GOV_ARTIFACTS" "$HF_HOME" "$XDG_CACHE_HOME"
```

若 `/workspace` 不是容量最大的持久盘，改用实际持久盘并记录路径。开始前保存：

```bash
date -Is
uname -a
nvidia-smi -L
nvidia-smi --query-gpu=index,name,memory.total,driver_version \
  --format=csv,noheader
nvidia-smi topo -m
free -h
df -h
```

硬门禁：

- 恰有 8 张可独占的 A100，每张约 80GB，不能处于 MIG 小分片模式；
- 系统 RAM 建议至少 128GB；
- 工作盘建议至少 500GB 可用，且在模型、结果和压缩包共存时持续保留余量；
- 有稳定外网，或模型已在一个所有 server 共享的本地 cache；
- 正式作业期间无其他进程争抢 GPU。

若不满足，先报告具体差异和重新估算，不要自动改变科学配置。

把所有长任务放入本机命名清楚的 tmux session；tmux 仅用于本机作业持久化，不是
用来连接或控制其他 agent。日志写到
`$GOV_ARTIFACTS/logs/`，同时维护 `STATUS.md`，记录开始/结束时间、PID、GPU、
端口、命令、return code、重试和异常。不要删除半成品。每 10–15 分钟检查：

- GPU utilization/memory；
- server 健康；
- 日志是否继续增长；
- 新 trajectory/probe 文件是否产生；
- 磁盘余量。

如果 15 分钟无输出且 GPU 空闲，主动诊断，而不是继续等待。服务或 runner 重启后从
已有原子 JSON 续跑；设置不一致时写入新目录并保留旧目录供审计。

## 3. 获取代码和基础设施

若 repo 不存在：

```bash
git clone https://github.com/Antony-zdh/Governor.git "$GOV_REPO"
```

若本机已经有 repo，直接在该目录核对 commit，不要重复 clone。无需配置 SSH server、
SSH 端口或远程登录。随后：

```bash
cd "$GOV_REPO"
git fetch --all --tags --prune
git checkout --detach "$TARGET_COMMIT"
test "$(git rev-parse HEAD)" = "$TARGET_COMMIT"
git status --short
```

工作树必须干净。把初始 commit、remote、submodule 状态写入环境清单。不要 `git pull`
到另一个提交，也不要在 collection 中途切换代码。

优先使用 Python 3.10 或 3.11 的独立 venv：

```bash
python3 -m venv "$GOV_WORK/venv"
source "$GOV_WORK/venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install vllm
python -m pip install -e "$GOV_REPO"
python -m pip install pandas scipy statsmodels matplotlib seaborn pyarrow \
  huggingface_hub
python -m pip check
```

让 vLLM 安装它兼容的 PyTorch/CUDA wheels，不要先随意 pin 另一套 Torch。若最新版
vLLM 与当前 driver/model 不兼容，在独立新 venv 中选择官方兼容版本并记录理由、
版本和完整 `pip freeze`；不得在同一环境反复覆盖导致不可复现。保存：

```bash
python - <<'PY'
import torch, transformers, vllm, openai
print("torch", torch.__version__, "cuda", torch.version.cuda)
print("cuda_available", torch.cuda.is_available(), "gpu_count", torch.cuda.device_count())
print("transformers", transformers.__version__)
print("vllm", vllm.__version__)
print("openai", openai.__version__)
PY
python -m pip freeze > "$GOV_ARTIFACTS/environment/pip-freeze.txt"
```

缺少系统工具时，root/apt 环境安装 `git git-lfs curl jq tmux zstd pandoc
texlive-xetex fonts-noto-cjk gh`；无 root 时用已有 Conda/Mamba 或用户目录的官方
二进制。不得因为 PDF 工具缺失而省略 PDF。

检查 GitHub CLI：

```bash
gh auth status
git ls-remote origin HEAD
```

认证缺失不会阻止 GPU collection，但必须尽早通知协调者，以免最后才发现无法上传。
任何 token 只能放在环境/credential store，严禁写进 repo、日志或报告。

## 4. 一次下载四个模型，共享同一 cache

模型均按 protocol ID 获取，不得改 revision 或用同名量化仓库：

```bash
hf download deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
hf download Qwen/Qwen3-8B
hf download deepseek-ai/DeepSeek-R1-Distill-Llama-8B
hf download deepseek-ai/DeepSeek-R1-Distill-Qwen-32B
```

公开下载失败时先区分网络、磁盘、Hub rate limit、许可和版本问题；只有确实 gated
才请求 `HF_TOKEN`。下载后记录每个 snapshot 路径、revision/commit、目录大小，
并验证 tokenizer/config/weight shard 齐全。所有 vLLM replicas 共用这个 cache，
不复制四份模型。

## 5. 本机协议门禁

在任何 GPU 正式任务前：

```bash
cd "$GOV_REPO"
python benchmark/FalseConsensus/governor_v2/prepare_rules.py expand
python -m unittest \
  benchmark.FalseConsensus.governor_v2.tests.test_governor_v2 -v
python benchmark/FalseConsensus/governor_v2/preflight.py
git diff --check
```

`preflight.py` 在服务器上必须不带 `--skip-model-template-check`。预期：

- 17 tests 通过；
- 17,712 个唯一候选规则；
- development/confirmation/small-confirmation matrices 为 54/72/63 行；
- split 为 300/100/100、24/8/8、18/6/6；
- 状态 `READY_FOR_GPU_SMOKE`。

记录 protocol、split manifest、candidate rules 和三份 matrix 的 SHA-256。若生成出的
ignored `candidate_rules.jsonl` 不是 17,712 条或 hash 在运行中变化，停止。

## 6. vLLM 服务和严格隔离的 smoke

先运行 `vllm serve --help`，核对当前版本的参数名。每个服务必须：

- `--dtype bfloat16`
- `--max-model-len` 使用 protocol 的模型级上限：Qwen3-8B 为 40,960，其余为
  49,152；Qwen3 不启用 YaRN/额外 RoPE scaling
- `--served-model-name` 与 protocol model ID 完全一致
- 开启 prefix caching
- 支持 OpenAI completions、`echo=True` prompt logprobs、top-20 logprobs
- 小模型单卡；32B `--tensor-parallel-size 2`

典型小模型命令：

```bash
CUDA_VISIBLE_DEVICES=0 vllm serve "$MODEL_ID" \
  --host 127.0.0.1 --port 18000 \
  --served-model-name "$MODEL_ID" \
  --dtype bfloat16 --max-model-len "$MAX_MODEL_LEN" \
  --enable-prefix-caching --gpu-memory-utilization 0.90 \
  --max-logprobs 20
```

典型 32B 命令：

```bash
CUDA_VISIBLE_DEVICES=0,1 vllm serve \
  deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --host 127.0.0.1 --port 18000 \
  --served-model-name deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --dtype bfloat16 --tensor-parallel-size 2 \
  --max-model-len 49152 --enable-prefix-caching \
  --gpu-memory-utilization 0.90 --max-logprobs 20
```

若当前 vLLM 没有某个非关键同名 flag，按 `--help` 使用等价官方配置并记录。不得省略
BF16、protocol 指定的模型级 context、prompt logprobs 或 32B TP=2。健康检查
`/v1/models`。

每个模型必须先做 3 题 smoke：MATH500、AMC23、AIME24 的 **train 各一题**。
即使是 held-out 模型也只用 train 做 smoke，绝不能提前请求 test。对每个 benchmark
从 `generated/problem_ids/<bench>__train.txt` 取第一个 ID，直接调用
`collect_main.py`，令 `--start=ID --end=ID+1`，保留对应
`--problem-ids-file`，使用正式 benchmark cap，并把输出写到
`$GOV_ARTIFACTS/smoke/<model>/<bench>/`，绝不能写入正式 results root。
然后依次对该单题运行 `dense_probe.py` 和 `adaptive_probe.py`。

smoke 必须验证：

- 每模型三条 main JSON 均能解析、模型模板正确、finish reason/token accounting 合法；
- main manifest 不含 API key；
- dense probe positions 从 64 开始且间隔 64；
- adaptive entropy 请求返回 prompt top-logprobs，event 字段和 entropy 数值有限；
- adaptive 与 dense 重合的位置被复用而非重复请求；
- recorded token count 与 tokenizer re-encode 无无法解释的系统偏差；
- AIME 的 32,768 `max_tokens` 请求不因 context 配置立即失败；
- 32B 确实跨两卡加载，未量化、未 offload。

smoke 失败时不得批量运行。smoke 数据只用于工程验收，永不进入 sweep、confirmation
或论文数字。

## 7. Development collection：先完成后冻结规则

正式结果根目录保持 protocol 默认：
`benchmark/FalseConsensus/results/governor_v2`。

### 7.1 八卡并行布局

在 GPU 0–3 启动四个 DeepSeek-7B replicas（端口 18000–18003），GPU 4–7 启动
四个 Qwen3-8B replicas（端口 18004–18007）；每个服务单卡。为避免八个进程同时
读 cache 造成启动假死，可以先后启动并通过健康检查，但正式 collection 两个模型
应并行占满八卡。

DeepSeek 的四个 runner 使用 `--shard-index 0..3 --shard-count 4`：

```bash
python benchmark/FalseConsensus/governor_v2/run_matrix.py \
  --matrix benchmark/FalseConsensus/governor_v2/generated/development_matrix.jsonl \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  --shard-index "$I" --shard-count 4 \
  --url "http://127.0.0.1:$PORT/v1" --execute
```

Qwen 的四个 runner 同样使用 `--shard-index 0..3 --shard-count 4`：

```bash
python benchmark/FalseConsensus/governor_v2/run_matrix.py \
  --matrix benchmark/FalseConsensus/governor_v2/generated/development_matrix.jsonl \
  --model Qwen/Qwen3-8B \
  --shard-index "$I" --shard-count 4 \
  --url "http://127.0.0.1:$PORT/v1" --execute
```

八个 shard runner 必须并行且模型内互不重叠；每个 environment 内仍严格 main →
dense → adaptive。两个模型都完成并审计后关闭八个服务。若单模型明显成为长尾，
只可在另一模型全部结束、其输出已验证后，把释放的 GPU 启成同模型额外 replicas，
并用一份明确、无重叠的剩余 environment 清单重新分片，不能让两个 runner 写同一
environment。

### 7.2 执行并发的安全调整

worker 数只是执行并发，不是科学变量。若 32K entropy scoring 导致 vLLM preemption
或显存压力，可降低 server `max-num-seqs` 或制作一份仅改变 `--workers` 的运行时
matrix 副本；必须保存 diff 和理由，不能改变模型、seed、prompt、cap、sampling、
题目或 probe 参数。

### 7.3 Development 完整性

预期 18 个 environment：每模型 3 seeds × 3 benchmarks。每个 environment 的题数：

- MATH500 train+dev：400；
- AMC23 train+dev：32；
- AIME24 train+dev：24。

总计 2,736 条 development main trajectories。逐 environment 验证：

- `run_manifest.json` 只有允许的 phase/role/splits；
- main、dense、adaptive 各有与题数相同的 per-problem JSON；
- problem ID 集精确等于相应 `train_dev.txt`，无 test ID、无重复、无遗漏；
- 每个 JSON 可解析，target/problem/model/seed/cap 与 manifest 一致；
- dense/adaptive probe manifest 完整；无 NaN/Inf、负 token、越界 position；
- 记录自然结束数、cap 数、realized cap rate、主/probe tokens、请求与 wall time；
- 保存失败清单；所有可重试失败补齐后再进入 sweep。

为此编写一个可复用的验证脚本并随最终结果提交；不要只靠人工 `ls | wc`。

## 8. Pareto sweep、三点冻结和 hash 门禁

Development 全部通过后，才在 CPU 上做离线 sweep。建议 8 个进程分片；若 RAM 不足
降到 4，不改变结果：

```bash
python benchmark/FalseConsensus/governor_v2/replay_rules.py sweep \
  --phase development \
  --rules benchmark/FalseConsensus/governor_v2/generated/candidate_rules.jsonl \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
  --results-root benchmark/FalseConsensus/results/governor_v2 \
  --shard-index "$I" --shard-count 8 \
  --output "$GOV_ARTIFACTS/sweep/sweep_$I.jsonl"
```

等待所有 shard return code=0 后：

```bash
python benchmark/FalseConsensus/governor_v2/replay_rules.py select \
  --rules benchmark/FalseConsensus/governor_v2/generated/candidate_rules.jsonl \
  --metrics "$GOV_ARTIFACTS"/sweep/sweep_*.jsonl \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
  --output "$GOV_ARTIFACTS/frozen_rules.json"
sha256sum "$GOV_ARTIFACTS/frozen_rules.json"
```

选择器应自动拒绝：

- 任何 development 以外 phase、train/dev 以外 split 或 held-out model；
- 未知 rule ID；
- 重复 `(rule, split, model, benchmark, seed, budget)`；
- 任一规则没有完整 36 个 development metric rows；
- 少于三个互异合格 Pareto 点。

人工复核 `frozen_rules.json`：

- schema `governor-v2-frozen-rules-2`；
- candidate count=17,712；
- 三个 selected rule ID 互异；
- `pareto_frontier` 非空，三条规则都在前沿；
- protocol/split/candidate/sweep SHA-256 与实际文件一致；
- 每条 selected rule 都含七个统一维度；
- 每条规则都生成 one-at-a-time 和完整 \(2^7\) factorial confirmation ablations。

输出一份 development Pareto 图和 CSV：所有 candidate、非支配前沿、三个 selected
点、三组 accuracy gate 都清楚标注。记录 selection 时间；冻结后不得编辑 protocol、
split、candidate、sweep 或 `frozen_rules.json`。

## 9. Confirmation：冻结后一次性运行 test

先在状态文件中记录 freeze 时间与 hash，再启动完整 72-stage confirmation matrix。
推荐同时使用全部 8 卡：

- GPU 0–1：32B，一个 TP=2 server；
- GPU 2–3：DeepSeek-7B 两个单卡 replicas；
- GPU 4–5：Qwen3-8B 两个单卡 replicas；
- GPU 6–7：Llama-8B 两个单卡 replicas。

启动 7 个 server 后：

- DeepSeek-7B：两个 runner，shard 0/2、1/2；
- Qwen3-8B：两个 runner，shard 0/2、1/2；
- Llama-8B：两个 runner，shard 0/2、1/2；
- 32B：一个 runner，shard 0/1。

命令形式：

```bash
python benchmark/FalseConsensus/governor_v2/run_matrix.py \
  --matrix benchmark/FalseConsensus/governor_v2/generated/confirmation_matrix_base64.jsonl \
  --model "$MODEL_ID" \
  --shard-index "$I" --shard-count "$N" \
  --url "http://127.0.0.1:$PORT/v1" --execute
```

预期 24 个 confirmation environments、912 条 main：

- DeepSeek-7B：342；
- Qwen3-8B：342；
- Llama-8B：114；
- 32B：114。

逐 environment 按 test ID 文件做与 development 相同的机器检查，并额外验证：

- phase=`confirmation`、split 只能是 `test`；
- seeds/role 与 protocol 精确一致；
- 所有输出创建时间晚于 frozen manifest；
- 任何 confirmation 结果都未被传给 `select`。

全部补齐后执行 frozen-rule evaluation：

```bash
python benchmark/FalseConsensus/governor_v2/replay_rules.py evaluate \
  --frozen "$GOV_ARTIFACTS/frozen_rules.json" \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
  --results-root benchmark/FalseConsensus/results/governor_v2 \
  --output "$GOV_ARTIFACTS/confirmation_metrics.jsonl"
```

该命令必须通过 protocol/split hash 门禁。确认三个 selected rules 及其全部唯一消融
规则均被评估；不得只测试 conservative/balanced 而漏掉 token-efficient。

## 10. 统计分析与报告

分析必须由可重复运行的脚本生成，脚本、输入清单和随机 bootstrap seed 一并提交。
禁止手工抄表。至少产生 CSV/JSON 和图：

1. 每 model × benchmark × seed × budget 的 baseline 与三策略：
   accuracy、paired accuracy difference、main decode、probe decode、probe prompt、
   total decode、saving fraction、stop rate、cap rate、probe calls、wall time。
2. 宏平均与分层结果；MATH/AMC/AIME 不按题数 micro-pool 冒充跨 benchmark 总结。
3. 配对 problem-level bootstrap 95% CI（固定并记录 seed），accuracy 同时给合适的
   binomial/paired区间；AMC/AIME 小样本必须显式展示宽区间。
4. development Pareto 与 untouched confirmation risk–compute Pareto；三个 selected
   点和 full-generation baseline 清楚标注。
5. cap/right-censoring：各环境 point estimate、区间和在不同 evaluation budget
   下的敏感性；不把截断输出当自然完成。
6. adaptive probing：各 trigger 数量、位置、dense reuse、event-only 请求、
   entropy-scoring GPU/wall time、probe decode 与 prompt-prefill cost。
7. 三个 parent rule 各自七维 one-at-a-time 和 \(2^7\) factorial；报告 reference
   replacement 的真实含义，不称为字面删除。
8. 泛化：development models 新 seeds、Llama 架构、32B 规模分别总结；不基于
   held-out 结果调参。
9. 失败、重试、缺失（最终应为零）、环境/版本和总 GPU-hours。

Primary token saving 按 protocol 使用 main decode + probe decode；probe prompt
tokens、teacher-forced scoring、wall time/GPU-hours必须另外报告，不能把 probing
说成免费。不要在本轮结果没有 related-work 同协议数据时声称超过 SOTA。

模仿既有
`benchmark/FalseConsensus/report/report_final_eval_multiseed_2026-07-26.md`
的紧凑风格，写：

- `benchmark/FalseConsensus/report/report_governor_v2_<date>.md`
- `benchmark/FalseConsensus/report/False_Consensus_Governor_v2_<date>.pdf`

建议结构：Executive Summary、协议与泄漏边界、数据完整性、Pareto selection、
confirmation 主结果、adaptive probing、七维消融、架构/规模泛化、cap 与成本、
局限性、可复现性清单。正文注重细节解释和表图可读性，但避免流水账。

必须由 Pandoc 转 PDF，例如：

```bash
pandoc report.md -o report.pdf --pdf-engine=xelatex \
  -V CJKmainfont="Noto Sans CJK SC" -V geometry:margin=1in
```

用 `pdfinfo`、`pdftotext` 和 `pdftoppm`/等价工具渲染每页做 QA：无缺图、空白页、
截断表格、乱码、越界或不可读字号。PDF 与 Markdown 中数字必须由最终 CSV 生成且一致。

## 11. 全部结果上传 GitHub

不要把数万 raw JSON 直接塞进普通 Git history，也不能只上传摘要而丢原始数据。
采用“两层发布”：

1. 专用 results branch/PR：提交分析脚本、验证脚本、环境清单、SHA manifest、
   frozen rules、aggregate CSV/JSON、图、Markdown、PDF、运行/异常总结和 raw archive
   inventory；
2. GitHub Release assets：上传全部 raw main/dense/adaptive JSON、run/probe manifests、
   sweep shards、confirmation metrics、服务/runner 日志和 GPU accounting 的压缩包。

在不改动原始结果的前提下，按 phase/model 或其他可审计边界制作确定性
`.tar.zst`。单个 asset 保守控制在 1.8GB 以下；若超过则分片。不要归档模型权重、
HF cache、venv、临时 socket 或任何 credential。生成：

- `SHA256SUMS`：每个 archive；
- `raw_file_inventory.csv/json`：每个原始文件相对路径、大小、SHA-256、所属
  phase/model/benchmark/seed/stage；
- `release_manifest.json`：TARGET_COMMIT、protocol/split/frozen hashes、archive 与
  文件总数/总字节数、环境版本、运行时间。

先随机解压检查并运行 JSON/manifest validator，再上传。创建清楚的 results branch，
提交时明确列出未纳入普通 Git 的 raw 数据由哪个 release asset 承载。推送 branch，
打开 PR；除非协调者明确授权，不自行 merge main。

创建 tag/release 并上传全部 assets。上传后用 `gh release view --json assets` 对比
本机清单；至少随机下载一个 asset 到本机新目录并校验 SHA-256。检查 GitHub 上：

- branch commit 可见；
- PR 可打开；
- Markdown/PDF/图/汇总数据存在；
- release 的 asset 数量、名称、大小与本机清单一致；
- 所有 raw 文件都能由 inventory 映射到某个已上传 archive；
- 没有 secret。

若 GitHub 单文件/配额限制变化，先查询当前 `gh`/API 返回，继续分片；不要以限制为由
省略数据。GitHub 认证或仓库写权限确实缺失时，保留校验完成的本机 archives，向协调者
请求最小所需权限并继续等待，不能把“本机已打包”称作上传完成。

## 12. 最终验收与汇报格式

只有以下全部成立才完成 goal：

- 环境与四模型 revision 可复现；
- 17 tests、full preflight、四模型三题 smoke 通过；
- 2,736 development + 912 confirmation main 全部齐全；
- dense/adaptive banks 与 manifests 全部齐全；
- 17,712-rule sweep 无漏 shard/重复/污染；
- 三个 selected Pareto rule ID 互异并已冻结；
- 三策略及其七维/全 factorial 消融在 confirmation test 上完成；
- aggregate 数据、图、MD、Pandoc PDF 通过一致性和视觉 QA；
- 所有原始/中间/最终结果和日志均进入 GitHub branch/PR 或 Release asset；
- release 上传后的数量与 SHA-256 复核通过。

最终消息必须列出：

- TARGET_COMMIT、results branch/commit、PR URL、release URL/tag；
- protocol/split/candidate/frozen SHA-256；
- 四模型 revision 与软件版本；
- 实际墙钟/GPU-hours、重试与异常；
- expected/observed 各阶段计数；
- 三个 strategy 名称、rule ID、七维摘要；
- confirmation 的核心 accuracy/token-saving/CI；
- report MD/PDF、aggregate 数据、inventory、SHA256SUMS 的路径；
- 未解决问题（应为空；若不为空，不能标记 goal complete）。

时间目标为模型下载完成后约 8–10 小时；硬件/网络/实际思维长度可能使其延长。
完整性、泄漏边界和可审计性优先于赶时。不要通过少跑 seed、少跑模型、跳过消融、
查看 test 后重选或不上传 raw data 来满足 timebox。
