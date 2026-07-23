# 工作日志（False Consensus Project）

倒序记录。约定：每次实验/代码变更记一条，包含动机、做法、结果、坑。

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
