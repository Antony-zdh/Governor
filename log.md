# 工作日志（False Consensus Project）

倒序记录。约定：每次实验/代码变更记一条，包含动机、做法、结果、坑。

---

## 2026-07-27 · Governor v2 development collection 完成（18/18 环境）+ sweep 启动

- **采集验收通过**：2 模型 × 3 benchmark × 3 seeds = 18 环境，main/dense/adaptive
  文件数与题数精确匹配（MATH500 400、AMC23 32、AIME24 24），manifest 齐全，
  零失败。数据在 `results/governor_v2/`（188MB）。
- 执行拓扑几经调整（共享机 GPU 竞争）：Qwen3-8B 单卡先毕业（轨迹短probe少）；
  7B 先 1 卡 → 2 卡分片 → 其他用户退场后 6 卡并行（每 runner 带 5 次重试），
  期间 GPU1 上的 vLLM 被外力关停一次（runner 重试机制 + 逐题原子续跑兜住）。
- **判分 flag 修正落地**：`fix_final_correct.py` 实际执行，2,736 条轨迹修正 62 条
  （集中在 grading 补丁前采集的两个 MATH500 seed42 环境，~7%），审计在
  `results/governor_v2/final_correct_fix_audit.json`。
- 采集完成后 GPU 全部释放；**17,712 规则 × 8 shard CPU sweep 进行中**（96 核，
  tmux sweep_0..7）。下一步：select 冻结三个 Pareto 操作点 → confirmation。
- 推送约定：每个里程碑 commit+push 一次（采集数据 → sweep 产物 → frozen rules →
  confirmation），原始数据归档在 repo 的 `results/governor_v2/`。

---

## 2026-07-26 · Governor v2 development collection 启动（8×A100 服务器）+ 两个采集代码 bug 修复

### 环境与门禁

- 服务器 `34.182.235.113`：全新 clone `~/Governor_v2`，TARGET_COMMIT=`70a5576`；
  venv 复用 `~/fc-venv`（vllm 0.25.1）；Qwen3-8B 已下载。17 单元测试通过、
  17,712 条候选规则展开、preflight `READY_FOR_GPU_SMOKE`。
- GPU 竞争激烈（共享机）：一度只剩 GPU1 可用；GPU0 释放后被我们抢下。
  当前拓扑：GPU1 = 7B 服务(:18000)，GPU0 = Qwen3-8B 服务(:18003)。
  两模型 smoke（3 题 main→dense→adaptive）均通过，熵打分 echo=True 可用。

### 修复 bug 1：collect_main 断点续跑必炸

traj 的 `run_settings` 含每题派生的 `main_seed`，续跑校验却与全局 settings 做
全等比较 → 第一次 resume 就抛 "incompatible run settings"。修复：比较时弹出
`main_seed`（其余字段仍全量校验）。

### 修复 bug 2：v2 判分拿未 strip 的 target 喂 math_equal（系统性误判）

`collect_main` 的 `final_correct` 和 `replay_rules.answers_equal` 都直接
`math_equal(answer, raw_target)`：`\left(...\right)`、`\text{...}`、`x\in`
前缀等格式全部误判为错（两个模型 smoke 的 P0 均中招，答案正确被标 False）。
这会污染 baseline 准确率与全部规则选择。修复：

- 新增 `governor_v2/grading.py::robust_answers_equal`（raw/stripped/deprefix/
  text-unwrap 多形态匹配，移植自 Stage 2-5 analyze.py 的修正逻辑）；
- `collect_main` 与 `replay_rules` 统一走该函数；replay 的 baseline 改为从
  `final_answer` 现场重算，不信任采集时的 flag；
- 新增 `fix_final_correct.py`：对已采 traj 批量重算 flag（带审计输出，幂等），
  在采集完成后执行；
- 注意：sweep/select 必须在装有 dynasor 的服务器上跑（本地无 dynasor 时
  replay 会静默退化到弱数值判分）。

### 状态

7B（GPU1）与 Qwen3-8B（GPU0）各自的 9 环境 development 采集进行中
（各 27 个任务：main→dense→adaptive）。后续：采集完 → fix_final_correct →
CPU sweep（17,712 规则×8 shard，服务器上跑）→ dev 选三点冻结 → confirmation
（需再凑 2 张空卡给 32B TP2）。

---

## 2026-07-24 · 下一阶段 roadmap 讨论 + paired re-probe 2×2 实验设计（仅 plan，未跑）

和 teammate 对齐了下一阶段五步，写进 plan.md §19；重点把第 1 步的实验设计定死，
写进 **plan.md §6.6**。目标：拆开 probe 后缀消融里 certaindex 的 confound——
"早停准确率损失从 16.4pp 降到 1.3pp"到底来自**更真实读出状态**还是**只是更保守
（触发更少更晚）**。

- 设计要点：**单轨迹基 2×2 析因**（timing × readout），四格全部锁在 simple 的 500
  条轨迹上。关键论证：probe 不影响主轨迹（独立 forward pass），所以 simple/certaindex
  两次 run 的轨迹差异纯是 run 噪声、不是处理效应——若把某格建在 certaindex 自己的
  轨迹上会把噪声混进来、破坏正交。
- 硬要求：**密集 re-probe**（simple 轨迹每个 checkpoint 都补 certaindex probe，
  ~8,739 个），才能在 simple 轨迹上求出 certaindex 规则的停机位置（格③④的 timing）；
  只在 simple 停机点补一次是不够的。复用 Stage 8 `run_probe_variants.py` 的
  token 切片重构（`encode(full_text)[:token_position]`），is_certain / math_equal
  口径对齐 logging_run.py。
- 判据：格②（simple 时点 + certaindex 读出）≫ 69.2% → 纯读出增益、且不必停更晚
  （最优）；≈ 69.2% → 增益来自 timing，再用 continuation-match + "105 个额外停机点"
  分析区分"忠实追踪收敛"还是"钝的高门槛"。可选 2×2×2（第二次对称 re-probe）隔离
  run 噪声。
- 方法细节已定死进 plan §6.6.4/6.6.7：**复用现有 500 条主轨迹（`stage1_logging`）、
  不重跑主 reasoning**；一次 re-probe 网格 `probe_suffix{simple,certaindex} ×
  probe_tokens{10,32}` 解决"选 probe + box 预算防 incomplete"两问题；32 档用
  stop 序列 `\]` 防 probe 成本炸（现状每 probe 恒用满，flat-64 会吃光 Pareto）；
  probe 输入**必须带 chat prompt**（Stage 8 的 `run_probe_variants.py` 漏了，
  会复现不出 simple 答案）；is_certain/obtain_answer/seed=42 逐字对齐 logging_run.py；
  **`simple@10` 必须先复现 Stage 1 probes.csv（≳95%）作为重构忠实度的黄金校验**。
- 待写脚本：`probe_compare/reprobe_paired.py`（改编 run_probe_variants.py）+
  `analyze_2x2.py`；产出 `results/probe_paired_2x2/`。
- **本轮:更新 plan/log 后 push，启动 vast-5090 GPU + tmux agent 实现并跑起来。**
- 补充(同日):roadmap 第 3 步"晚共识不可靠的因果验证"也定稿进 plan §7.5 ——
  方案不是跨题分层而是 **within-problem K-rollout**(同题 K≥8 次 + max budget 12k，
  难度按构造锁死),主分析 within–between 分解(mixed-effects + Mundlak group-mean
  centering),正式补 Stage 9 deferred 的 Analysis 3/4;并行支线、非关键路径。
  难度指标用经验 pass rate(独立),**忌用轨迹派生量(长度/entropy/switches)当难度**
  (会吸收掉要测的效应)。这条属设计,尚未跑。
- 补充(同日):第 4/5 步的排期与判据也写进 plan §8.2a / §8.3.0。要点:规则型
  Governor++(第4步)≈ 第2步 sweep(获胜配置本身就是规则),不用干等,v0 现在就能
  用 Stage 7 Conservative + Stage 6 validity filter 拼出;**何时训 calibrator(第5步)
  的三条判据**:规则撞天花板 + 缺口像难度自适应/多信号交互造成 + 轻量同特征
  calibrator 在 held-out+Qwen 上确实赢过最优规则,三条同时满足才训,否则发规则。

---

## 2026-07-24 · Stage 11 跨模型 + Stage 12 跨数据集 + probe suffix ablation（远程 vast.ai GPU，已合入 main）

`vast-5090`（vast.ai instance `45605832`，1x RTX 5090）上的远程 Claude Code
agent 依次跑完三组实验，本地 `git fetch` + `--ff-only merge`
（`5626955` → `799e827`）干净合入，无冲突。磁盘只有 24G，DeepSeek-7B 权重
删除后腾出空间下载 Qwen3-8B（用户在 `AskUserQuestion` 中确认后才执行删除，
未自行推断同意）。

- **Stage 11（`results/stage11_cross_model/qwen3_8b_math500/`）**：
  Qwen3-8B 在 MATH500 全 500 题上，overall accuracy **78.2%**（vs Stage 1
  DeepSeek-7B 同数据集 81.2%），finished naturally 35.0%。window share=1
  372 题、window-answer accuracy 89.0%、false consensus 41 题（11.0%）；
  Governor 模拟早停 340/500，stopped-answer accuracy 83.5%（vs 该子集
  final accuracy 89.7%，注意这是子集内的口径，不是整体准确率——见下方坑）。
- **Stage 12（`results/stage12_cross_dataset/`）**：DeepSeek-7B 在
  AMC23（40题）overall accuracy **60.0%**，finished naturally 37.5%；
  AIME24（30题）overall accuracy **26.7%**，finished naturally 0.0%（全部
  超预算截断）。两个数据集样本量小、方差大，AIME24 上 cumulative
  share=1 甚至从未出现（CR(cumulative)=nan）。
- **Probe suffix ablation（`results/probe_suffix_ablation/deepseek7b_math500_certaindex/`）**：
  同模型同数据集（DeepSeek-7B / MATH500 500题），换一种 probe 后缀
  wording（"certaindex" 风格），overall accuracy **79.6%**，finished
  naturally 60.8%（远高于 Stage 1 的 61.8%……几乎持平）。相比 Stage 1
  simple probe 的 81.2%，低约 1.6pp——说明 probe 措辞的影响是温和的，
  不是决定性因素。
- **坑（本次真正花时间的地方）**：远程 agent 口头汇报"final accuracy"时，
  实际报的是 `analyze.py` Stage 5 Governor 模拟里 `stopped` 子集的
  `final_correct.mean()`（分母只有触发早停的题），而不是 `overall_acc`
  （分母是全部题，report.md 里"overall accuracy"那一行）。两个都是
  合法指标但分母不同，口头汇报没说清楚导致我一度以为四组实验准确率
  都在 88-90% 这么高。通过直接读 `analyze.py` 源码（L379/L426/L472-473）
  和四份 report.md 独立核实，远程 agent 自己也独立发现并纠正了同样的
  问题，两边核对结果完全一致。以后引用这批数据只用上面列出的
  overall accuracy 数字，早停子集准确率（89.7%/74.2%/53.3%/90.0%）
  如果要用必须明确标注"仅统计 Governor 触发早停的子集"。
- vast.ai 实例流程：安装了本地 `vastai` CLI（venv，因为系统 Python 3.9
  跑不了这个包的 3.10+ `match` 语法），配置了 API key + 2FA
  session，之后可以自己开关这台 GPU 实例（只能 `stop`，绝不能
  `destroy`——会丢光权重/结果/repo 状态）。三组实验确认全部跑完、
  分析完、提交推送成功后，本次已用 `vastai stop instance 45605832`
  停止实例（数据完整保留）。

---

## 2026-07-23 · Stage 8 分析完成 + Stage 7 规则×Stage 8 probe 交叉验证

远端 agent 又推了一版新 commit，产出 `compare_probes.py`（§6.4 全部指标）：
P0 empty 10.0%/stop-acc 58.9%；P1_32/P1_64 empty 降到 0.6%/0.3%、
stop 更频繁但 stop-acc 略低（56.7%/57.1%）；P2/P3 几乎不空的时候
（stop_rate 仅 8-9%）反而 stop-acc 很高（87.5%/88.9%，ready-precision
64.8-67.3%）——说明 P2/P3 在"愿意给出明确答案"这件事上很挑剔，
但一旦给出就相当可信；P4 基本不可用（empty 99.9%）。已 fast-forward
合入 main（无冲突）。

用户接着问：Stage 7 找到的最优规则（Conservative/Balanced 两个可用操作点）
能不能也拿新 probe 测一下？写了 `probe_compare/test_stage7_rules.py`：
规则本身完全不变（`consec_p8_mt1024_cert1` / `consec_p6_mt1024_cert0`），
只把喂给规则的 probe 信号从 P0 换成 P1_32/P1_64/P2/P3/P4，在 Stage 8 的
同一 100 题子集上对比（P0 也在这 100 题上重新跑了一遍作为公平基线，
不能直接借用 Stage 7 report.md 里 n=500 的数字）。`is_certain` 对
P1-P4 用和 logging_run.py 完全相同的 UNCERTAIN_WORDS 检测（在各自
raw_output 上做），而不是偷懒复用 parse_ok——两者衡量的不是一回事。

- **结果：套用新 probe 对这两条规则没有正向帮助，多数情况下更差**。
  P1_32/P1_64 确实触发更频繁一点，但每次 probe 调用本身贵 3-6 倍
  （32/64 vs 10 tokens），省下的 token 抵不过 probe 自己的开销，
  总 token 反而涨了 255-932；准确率基本打平（±0-2pp，噪声范围内）。
  P2/P3/P4 更糟：>90% 空答案率导致"连续 N 次非空"这个门槛几乎满足不了，
  规则触发率崩到 0-2%，等于退化回几乎跑满全程。
- **结论**：Stage 7 的 consecutive 类规则是围绕 P0 的短/廉价 probe 调出来的
  最优点，直接换成"更贵但更可靠"的 probe 并不会自动变好——**规则设计和
  probe 设计需要联合优化**，不能简单替换其中一个。这对 Stage 10
  Governor++ 是个直接的设计约束：不能先固定规则形状再挑 probe，
  或者反过来，两者要一起搜索。
- 产出：`results/stage8_probe_compare/{comparison_report.md,
  comparison_table.csv, fig_compare.png, stage7_rules_x_stage8_probes.csv,
  stage7_rules_x_stage8_probes_report.md}`，`probe_compare/{compare_probes.py,
  test_stage7_rules.py}`。

---

## 2026-07-23 · Stage 6 Round 1 标注分析（100/296，`analyze_audit.py`）

用户决定不标满 296 例，标到 100 个就停下先出结果、推进后续 stage
（案例文件顺序是打散的，前 100 个自然覆盖了全部 6 组，10-23 例/组，
非精确配额但足够看方向）。plan.md §4.5 Round 1 设计假设两名独立标注者
算 Cohen's kappa——实际只有用户一人标注，`analyze_audit.py` 如实报告
不含 kappa，不编造第二人数据。

- **整体 probe validity rate 只有 39.0%**（95% CI [30%, 49%]，n=100）——
  也就是说这 10-token boxed probe 有六成左右的时候并不真实反映模型当时的
  belief。这个数字比之前 31 例草稿分析时看到的趋势更极端、也更可信（n更大）。
- **single_letter 类型 validity rate = 0%**（n=25！）——单字母答案几乎
  100% 是格式伪影，不是真实的选择题作答。强烈支持 Stage 3 就发现的
  "非选择题输出 B/D 字母" 假象。
- **validity 随 local consensus share 强烈单调上升**：share=1.0（前后
  probe 完全一致）时 81.3% 有效，share 0-0.5 时只有 6.5% 有效——
  这是本轮最重要的发现之一：**局部一致性本身确实是 validity 的强预测因子，
  但门槛效应非常陡（0.5→1.0 之间跳变），不是线性关系**，
  为 Stage 10 Governor++ 的 rule 设计提供了直接依据（不能只看
  "是否一致"，要看"是否完全一致"）。
- forced-guess rate（tentative_guess）25.0%，artifact rate
  （format_artifact）26.0%；`supported_wrong` 只标了 1 例，太少无法算
  `P(correct|supported_wrong)`。
- §4.7 判断标准（限定在 probe≠final 的 56 例）：情况 A（forced guess，
  37.5%）和情况 C（format artifact，37.5%）并列最高，情况 B
  （supported_wrong 后 recover，1.8%）几乎不存在——初步支持"论文重点应
  从错误 belief 转向 forced extraction + format artifact 导致的过早停止"，
  但 n 还小，留到 Round 3（若标注量再增加）复核。
- 复查了此前标记的疑似错标 `41_15`：probe=17 实际等于 reference_answer
  （真答案），只是模型后来漂移到错误的最终答案 15——用户的
  `supported_correct` 标签是对的，我之前的 flag（比较 probe vs final
  而非 probe vs reference）是我的误判，不是用户的问题。
- 产出：`audit/{audit_report.md, annotations_enriched.csv, analyze_audit.py}`。

---

## 2026-07-23 · Stage 8 GPU 数据采集（远程 agent 完成，已合入 main）

`benchmark/FalseConsensus/probe_compare/`。offline 部分（`select_subset.py`，
100 题分层子集，1737 个已有 checkpoint）和 GPU 部分（`run_probe_variants.py`，
5 种 probe 设计 P1_32/P1_64/P2/P3/P4）都是本地先写好、`--dry-run` 验证过
管线正确性，再打包成一份自包含的中文 prompt 交给远程 GPU agent 去跑
（服务器本地没有 GPU）。

- 远程 agent 用同一 commit（`450eb3d`）+ 同一模型
  （DeepSeek-R1-Distill-Qwen-7B，vLLM）跑通了全部 8685 次调用
  （1737 checkpoint × 5 设计），100/100 题、0 错误、约 5 分钟。
- 中途卡了一次：远程 push 到 GitHub 返回 403——远端 `.env` 里的
  fine-grained PAT 没给 `Contents: Read and write` 权限。用户在 GitHub
  上补了权限后重新 push，本地 `git fetch` + `--ff-only merge` 直接干净
  合并（无冲突），并用 `probe_variants.csv` 的真实行数/分组统计核对过
  和远程报告完全一致，确认数据没有被篡改或截断。
- **真实 parse_ok 率**（原设计目标是测"格式遵循率"）：P1_32 99.4% /
  P1_64 99.7% / P2 10.4% / P3 11.6% / P4 0.1%。样例显示 P2/P3/P4 这类
  "打标签"式指令 probe 基本被模型无视——模型继续正常写推理过程而不是
  输出 `<status>` 标签；P4（独立抽取式 query）几乎必定重新触发完整
  `<think>` 推理而不是照要求回答 UNFINISHED。只有 P1（沿用原 boxed
  续写格式、只是加长 token 预算）保持近乎完美的格式遵循率。
- 这本身就是一个有信息量的负结果：结构化/打标签式 probe 设计在这个
  模型上不可行，改进 probe 有效性的方向应该是"更长的同格式续写"
  而非"换一种指令格式"。
- 产出：`results/stage8_probe_compare/{probe_variants.csv, variant_traj/*.json}`
  （8685 行 + 100 个逐题 JSON）。`compare_probes.py`（§6.4 全部指标：
  empty rate / truncation rate / artifact rate / valid-answer rate /
  readiness precision / calibration error 等）尚未产出，正由远端 agent
  编写。

---

## 2026-07-23 · Stage 9（部分）离线难度分析——在等 Stage 6 人工标注期间先做

`benchmark/FalseConsensus/difficulty/analyze_difficulty.py`。只用现有数据
（MATH level/subject、entropy、answer switches、是否触碰 token 上限），
**不依赖 Stage 6 标注结果**，`probe_validity` 特征留待标注完成后补上重跑。
跳过了 Analysis 3（难度匹配对比）和 Analysis 4（recovery 概率模型）——
这两个需要更多设计时间，没有仓促做低质量版本。

- Analysis 1（分层）：level 5 的题在各 consensus_time bin 准确率明显低于
  level 1-2（如 level5 <512 tok 时准确率仅 65% vs level1 94.4%），
  初步支持"迟共识更不可靠"部分是准确率随难度下降的混杂，而非纯粹的机制效应。
- Analysis 2（逻辑回归，5折CV准确率 84.2%）：`hit_token_cap`（触碰token上限）
  和 `level` 是最强的负向特征（碰到 cap 的题 odds ratio 0.20），
  `subject`（Geometry/Precalculus 明显更难）次之。
- Stage 9.4（Terminality/Correctness/Safe-stop 概率，plan.md §7.4 核心新指标）：
  **反直觉发现**——share=1.0（完全一致）这一档的 T=0.60, C=0.56，
  反而低于 0.7-0.8 档（T=0.74, C=0.66）！说明"完全一致"里混了大量
  probe 数很少就凑巧全一致的轨迹（早期/trivial 一致），
  直接支持 plan.md 的核心论点：单看 agreement 不够，安全停止需要同时
  看 correctness 和 terminality。
- 产出：`results/stage9_difficulty/{report.md, analysis1_stratified.csv,
  analysis2_logistic_coefs.csv, stage9_4_probabilities.csv,
  per_problem_with_difficulty.csv}`。

---

## 2026-07-23 · Stage 6 标注工具 + Stage 7 Pareto Sweep（真实结果）

### Stage 6（`benchmark/FalseConsensus/audit/`）——工具已就绪，标注待人工完成

- `sample_probe_audit.py`：按 plan.md §4.2 六组从 500 题日志抽样，
  probe_answer==final_answer / !=final_answer / 单字母 / 空 / 连续3次一致后变化 /
  连续3次一致后保持到底，去重后 **296 个不同 probe-level 案例**（落在
  初版目标 200–300 区间），每组配额 50 均已抽满。
- 每个案例的 reasoning prefix 用真实 tokenizer（`deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`）
  对 `full_text` 重新分词、按 `token_position` 精确切片重建——`traj/*.json`
  本身不存每个 checkpoint 的 prefix，只存最终 `full_text`，字符比例估算会不准，
  这是唯一精确的办法。
- `annotate.html`：本地单文件标注页面（双击打开，无需 server），案例数据内嵌
  为 JS 对象；7 个主标签（数字键 1-7）+ 5 个二元字段，进度条、`localStorage`
  自动保存/断点续标、Export CSV。**主标签不放任何 AI 预填**——按用户明确要求
  （"I will be the human in the loop"），这是真人工标注，不是 AI 辅助分类。
  已用 Node 跑通内嵌 JS 的加载/CASES 完整性检查，未发现语法/运行时错误。
- `annotate_guideline.md`：标注指南独立文档（与页面内嵌内容一致）。
- `analyze_audit.py`（计算 plan.md §4.6 指标 + kappa）**尚未编写**——等用户导出
  `annotations.csv` 后再做；本项目目前只有一名真实标注者，kappa 只能等未来
  真的有第二人标注才计算，不会编造第二人数据。

### Stage 7（`benchmark/FalseConsensus/replay/sweep_stop_rules.py`）—— 已跑完，真实数字

- 参数网格：按 plan.md §5.2 每个 rule family 抽有代表性的子集（而非全笛卡尔积，
  全笛卡尔积在 n=500 下组合爆炸且大多数无意义），共 **142 个配置**：
  vanilla / hard_cap(5) / consecutive(patience×min_tokens×certain, 40) /
  window_share(window×share×min_valid×min_tokens + validity_filter 变体 +
  history-aware max_switches 变体, 65) / entropy(3种模式, 30) /
  额外补的 production_bug 复现(1)。
- **Sanity check 通过**：`consec_p3_mt0_cert1`（3 次一致+确定+min_tokens=0）
  精确复现 `analyze.py` 已有 report.md 数字——触发 416/500，停机准确率 69.2%，
  与旧结果完全一致，说明新引擎实现无误。
- 选出的 3 个工作点（plan.md §5.7）：
  - **Conservative**（准确率降≤1pp）：8 连续一致+确定, min_tokens=1024 →
    81.0%（vanilla 81.2%），总生成 token 2085（主 1935+probe 150），覆盖 47.8%。
  - **Balanced**（≤3pp）：6 连续一致（不要求 certain）, min_tokens=1024 →
    78.8%，总 token 1793，覆盖 66.6%。
  - **Aggressive**（最大节省）：字面最优是 entropy≤0.5 规则，几乎立即停
    （token 138），但准确率只有 25%——**不是可用的原型，只是无约束目标的字面最优**；
    加 50% 准确率下限后最优变成 window=8/share≥0.6/min_valid=3
    （53.2%准确率，总 token 882），仍然掉了 28pp。**真正的发现是这批规则的
    Pareto 前沿在 Balanced 点之后断崖式下跌**——没有能在准确率>50%的前提下
    大幅省 token 的简单规则，说明想要更激进的工作点得靠更聪明的规则
    （validity filter / 难度感知，对应 Stage 8/9），而不是换个阈值。
  - **实际部署 bug baseline**（复现修复前 `should_early_exit`：window=2、
    无一致性检查）：准确率 27.8%，覆盖 99.8%，false-stop rate 72.3%——量化了
    "文档意图 vs 实际部署代码" 这个 gap 到底有多严重。
- **数据口径缺口**：`logging_run.py` 从未记录请求级延迟，`wall_clock` /
  `prefill_cost_estimate`（plan.md §5.5）拿不到，report 里明确标注为缺失，
  只报 token 口径的成本，不编造计时数字。
- 产出：`results/stage7_pareto/{sweep_results.csv, report.md,
  figureA_accuracy_vs_tokens.png, figureB_coverage_vs_falsestop.png,
  figureC_saving_vs_accdrop.png}`。

---

## 2026-07-23 · 修复 `should_early_exit` 死代码 bug（生产 server，不影响 FC 实验数据）

- **发现**：`dynasor/core/entropy.py` 里 `should_early_exit`（`dynasor-vllm`/`dynasor-sglang`
  两个 server 早停判断，`vllm_server.py:488`、`sglang_server.py:593` 调用，
  `certainty_window` 默认 2）最后一句 `return True` 缩进在三层一致性检查
  `if` 之外，导致只要 probe 数够、最新 probe 无犹豫词就**无条件早停**，一致性/
  非空/确定性检查全是死代码——从最初 certaindex 提交（`3030c97`）就存在，
  一直没被发现。
- **影响范围核查**：`benchmark/FalseConsensus/logging_run.py` 只 import
  `obtain_answer`，Stage 1 本来就是纯 logging、不调用早停；`analyze.py` 的
  early-stop 模拟是独立实现（`for t in range(bar-1, ...): all(a!="") and
  all(cert) and all(eq(...))`），未 import `should_early_exit`。**全仓库搜索
  确认 `benchmark/` 下无任何引用** → 不影响任何已有 FC 数据/分析结论
  （log.md 之前的记录、FINDINGS.md、report.md 数字均不受影响）。
- **修复**：`return True` → `return False`（无需改缩进，三层 if 不满足时会
  自然 fall through 到最后一行）。5 组手动 case 验证：一致+非空+确定 → True；
  不一致 / 答案不够 / 有犹豫词 / 空答案 → 均正确返回 False。
- **意义**：这是文档意图（"连续一致才停"）与生产代码实际行为的一个真实 gap，
  值得写进论文作为独立发现（"部署的早停机制此前从未真正检查过一致性"）；
  也提示 Stage 6/7 要同时报告"设计意图 baseline"和"代码实际实现 baseline"。

---

## 2026-07-22 · Stage 1–5 首轮完整实验（MATH500 × 500）

### 环境搭建

- 服务器 `34.182.235.113`（共享 8×A100-80G）。磁盘曾 100% 满，清理了自己的
  pip 缓存、系统 crash dump（13G）、30 天未用的 Docker 构建缓存，腾出 41G。
  未动任何其他用户数据。
- venv：`~/fc-venv`（vllm + dynasor 本仓库 editable install + pandas/matplotlib）。
- 模型：DeepSeek-R1-Distill-Qwen-7B（HF cache，15G）。注意新版 CLI 是
  `hf download`，`huggingface-cli` 已废弃。
- 启动：`bash ~/fc_launch.sh`（tmux 里起 vLLM（GPU 7, prefix caching, api-key
  token-abc123）+ logging 任务）。用完已关闭 vLLM 释放 GPU。

### Stage 1 Logging（`benchmark/FalseConsensus/logging_run.py`）

- 纯记录模式：每题单条轨迹，每 128 tokens 一个 probe（`**Final Answer**\n\n\[ \boxed{`，
  10 tokens），budget 3072，temp 0.6 / top_p 0.95 / seed 42，可断点续跑。
- 先跑 100 题验证（4.5 分钟），代码稳定后直接补到 500 题（约 21 分钟，16 并发）。
- 产出：`probes.csv` 8,739 行 + `traj/` 500 条完整轨迹 JSON。

### Stage 2–5 分析（`analyze.py`，两套 agreement 定义）

- cumulative share（plan 定义，全轨迹）与 window share（最后 5 probe，非空）。
- 关键数字（n=500）：总准确率 81.2%；cumulative share=1（非空）87 题 98.9% 正确
  （唯一真全程假共识 P456：24 probe 全答 `1`，正解 `-2,1`）；window share=1
  338 题 93.5% 正确（22 例假共识）；Dynasor 式早停模拟：416 题触发、停机答案
  69.2% vs 跑到底 85.6%（-16.4pp），平均省 1,321 tokens，128 题停在错误答案。
- Recovery：probe1 错的 375 题 76.3% 翻盘；145 题曾有与最终答案不同的假稳定共识。
- 共识形成越晚越不可信：<512 tokens 87.4% vs >2048 tokens 58.1%（与 plan 猜想相反）。

### Stage 3 分类（`classify_cases.py`）

- 前 100 题 28 个早停错误案例：A 数字坍缩 14 / D 推导遗漏 7 / E 格式伪影 6 /
  B 表达式坍缩 1 / C 符号 0。AI 辅助初分类，待人工复核；500 题共导出 134 例。
- 发现 probe 方法论伪影：非选择题稳定输出 "B"/"D" 字母（Type E，21%）；
  超长答案（向量/方程）10 token probe 装不下 → 空串假共识。

### 评估修正（都在 analyze.py，logging 原始数据不受影响）

1. `strip_string` 把 `\text{east}` 剥成空串 → P97 误判（对 raw/stripped/unwrap 三形态匹配）；
2. 空 probe"共识"计入完美一致 → P179/P408（一致性只认非空答案）；
3. `math_equal` 不认 `x\in[-2,7]` ≡ `[-2,7]` → P383（剥 `x\in` 前缀）。
   若不修正，全程假共识会被高估 4 倍（4 例 vs 1 例）。

### 产出

- `benchmark/FalseConsensus/`：logging_run.py / analyze.py / classify_cases.py /
  README.md / FINDINGS.md
- `results/stage1_logging/analysis/`（n=500）与 `analysis_n100/`（前 100 题存档）：
  Figure 1–5 + report.md + 案例导出
- `report/False_Consensus_Report_2026-07-22.pdf`（10 页完整报告，
  `pandoc report.md --pdf-engine=xelatex -V CJKmainfont=STSong -V CJKsansfont=STHeiti`）

### 下一步

- 人工复核 28 例分类，补全 134 例全量分类；
- Stage 6 Governor++：先在现有 probes.csv 上离线回放 stop 规则
  （答案形态过滤 / 共识时间上限 / 更大窗口 / 轨迹稳定性），画 accuracy–token Pareto；
- 多模型（Qwen / Llama distill）+ 多数据集（GSM8K / AIME24 / AMC23），脚本已参数化。
