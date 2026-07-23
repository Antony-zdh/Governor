# False Consensus — Stage 1–5 首轮结果（2026-07-22）

**设置**：DeepSeek-R1-Distill-Qwen-7B（vLLM, 1×A100-80G）· MATH500 全部 500 题 ·
budget 3072 · probe 间隔 128 tokens（每题最多 24 个 probe）· temperature 0.6 /
top_p 0.95 · probe = `**Final Answer**\n\n\[ \boxed{`（10 tokens）· seed 42。
Governor 全程只记录、不干预。

数据：`results/stage1_logging/`（probes.csv 每 probe 一行 + traj/ 全轨迹）。
前 100 题的分析存档在 `analysis_n100/`，全量 500 题在 `analysis/`。

---

## 核心结论（TL;DR）

1. **"Agreement 是不是 Correctness"——答案：不完全是，且取决于怎么定义 Agreement。**
   - **全轨迹一致（cumulative share=1，且非空答案）**：87 题里 98.9% 正确，真正的
     全程假共识只有 1 例（P456：漏根，24 个 probe 全部答 `1`，正确答案 `-2,1`）。
   - **窗口一致（最后 5 个 probe 一致——Governor 停机时真正看到的信号）**：
     338 题里只有 93.5% 正确，**22 例 false consensus（6.5%）**。
   - 所以：*完美的全程共识几乎可信；但 Governor 在线看到的"局部共识"不可信。*

2. **False consensus 的真正代价在早停**：模拟 Dynasor 式早停（连续 3 个 probe
   一致 + certain + 非空即停）：416/500 题会触发停机，停机答案准确率只有
   **69.2%**，而这些题继续推理到底能到 **85.6%** —— **16.4 个点的准确率损失**，
   换来平均节省 1321 tokens。128 题停在错误答案上。

3. **翻盘（Recovery）非常普遍，早停会杀死它**：
   - 145 题曾形成过与最终答案不同的 3-probe 共识，其中 95 题（65.5%）最终改对；
   - probe1 答错的 375 题中，**76.3% 最终翻盘答对**。
   - → "第一印象"和"局部共识"都远不是终局。

4. **共识形成得越晚越不可信**（与 plan 中"越早越容易错"的猜想相反）：
   <512 tokens 形成共识的题 87.4% 正确，>2048 tokens 才形成的只有 58.1%。
   直觉：难题收敛慢、且收敛质量差；早收敛多为简单题。

5. **校准误差（CCE）**：cumulative 0.149 / window 0.080。窗口 share 在
   0.8–0.9 段严重高估可信度（share 0.8 → accuracy 只有 47.2%，n=36）。

## Stage 3 分类（前 100 题的 28 个早停错误案例，AI 辅助初分类，待人工复核）

| Type | 数量 | 说明 |
|---|---|---|
| A 数字坍缩 | 14 (50%) | 稳定收敛到错误数字（算术/推导滑坡） |
| D 推导遗漏 | 7 (25%) | 漏根/漏 case/未验根/审错题 |
| E 格式/选项幻觉 | 6 (21%) | 非选择题却稳定输出 "B"/"D" 等字母 —— probe 机制本身的伪影 |
| B 表达式坍缩 | 1 (4%) | 表达式错误化简 |
| C 符号错误 | 0 | 本批未出现 |

明细在 `classify_cases.py` 的 `CLASSIFICATION` 字典（含每案理由），改完直接重跑出 pie。
**注意 Type E**：≈1/5 的"假共识"其实是 probe 格式伪影而非模型信念——这本身是
对 probe-based agreement 方法论的一个发现，Governor++ 应过滤字母型答案。

## 数据质量备注（影响复现，已在 analyze.py 修正）

- `strip_string` 会把 `\text{east}` 剥成空串 → 上游 evaluator 会误判（P97）；
- 答案太长（向量/方程）时 10-token probe 输出为空 → 空串"共识"是假象（P179、P408），
  cumulative 一致性统计已排除空答案主导的题；
- `x\in[-2,7]` vs `[-2,7]` 这类前缀差异 math_equal 不认（P383），已加规则。

## 对 Governor++（Stage 6）的直接启示

Stop = Agreement AND Reliable，其中 Reliable 至少应包含：
1. **共识形成时间**（>2048 tokens 才形成的共识基本不可信）；
2. **答案形态过滤**（字母/空串等 probe 伪影不算共识）；
3. **窗口大小/门槛自适应**（3-probe 窗口太激进：69.2% vs 85.6%）；
4. **历史稳定性**（曾多次换答案的轨迹，局部一致也不可靠——145 题有过"假稳定"）。

## 复现

```bash
# 服务器 ~/Governor，venv 在 ~/fc-venv，模型已在 HF cache
bash ~/fc_launch.sh        # 起 vLLM + 重跑 logging（自动跳过已完成题目）
python analyze.py --input results/stage1_logging
python classify_cases.py results/stage1_logging/analysis_n100
```

## 下一步（对应 plan Week 3+）

- 人工复核 28 例分类；对 500 题的 134 例导出（`false_consensus_cases.md`）做全量分类；
- Stage 6 Governor++ 原型：在相同 log 上离线回放不同 stop 规则（数据已足够，无需重跑模型）；
- 多模型（Qwen、Llama distill）与 GSM8K/AIME24/AMC23 复制本流程（脚本已参数化）。
