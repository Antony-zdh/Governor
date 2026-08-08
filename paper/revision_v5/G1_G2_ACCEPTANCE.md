# G1 / G2 验收报告（本机独立复核，2026-08-08）

对象：`origin/v5-gpu-20260807`（`e74bf610` G1 → `e4407f23` G2 → `ce1e3b2c` log），
基于 `24d1e031`（不含第 2 轮的 `a4bc0333`）。

原则：**不采信远端 agent 的自述**。下面每一条都是在本机用**自己写的脚本**重算的；
凡是直接引用对方 `summary.json` 的地方都标注了。

---

## 一、通过的检查

### 分支卫生
- 基于 `24d1e031`，未合入 main，未 force-push。
- `git diff --name-status 24d1e031..ce1e3b2c` 中**没有任何 `D`（删除）**。
- **冻结数据未被触碰**：`dense_simple32/`、`main/`、`*/traj/`、`adaptive_simple32/`、
  `deer_confidence_bank_cap30/` 在 diff 中零出现。
- `paper/` 下唯一的差异是 `DEFECT_LOG.md`，且相对**它自己的 base** 为零差异
  （对 `v5-preprint` 显示 −151 行只是因为它没有我的 `a4bc0333`）。

### G1 覆盖与配对（自写脚本 `verify_g1.py`）
| 检查 | 结果 |
|---|---|
| 带 `dense_certaindex32` 的环境数 | 18 |
| 轨迹数 / probe 数 | 684 / 55,574 |
| **token_position 列表与配对 `dense_simple32` 不一致的轨迹** | **0** |
| 缺失配对 / 重复位置 / `probe_out_tokens>32` / error 行 | 0 / 0 / 0 / 0 |
| 每环境条数 | math500 100、amc23 8、aime24 6，全对 |

1:1 配对是 G1 全部设计的前提，独立核verified 通过。

### G1 可复现性（最强的一条）
把对方的 `compute_probe_wording_v5.py` 在**本机**用 **30 秒** grader 上限完整重跑，
输出与已提交结果 **逐字节相同**（`git status` / `git diff` 均为空）。
即：G1 的数字在另一台机器、另一个 grader 超时设置下完全复现。

### grader 4 秒硬杀的实际影响（对方只说「a handful」，未测量；我测了）
- 去重后 `eq()` 调用：**16,271**
- 超过 4 秒的：**1**（0.006%）
- 其中「真实判定为 True 而 4 秒回退返回 False」的：**0**

结论：这个偏差**没有改变任何一个数**。对方的说法方向正确，但当时是断言而非测量；现在有数了。

### G2 gate 结论（用我自己写的 gate 代码，不读对方 summary）
从 `replay_rows.jsonl.gz`（31,680 行 = 1,760 规则 × 18 环境）macro 重算：

```
gate clearers = {conservative: 0, balanced: 0, token_efficient: 0}
drop ≤1.0pp 中最大 saving = 3.9256%   (consensus_fixed__d2eecbffc489, drop 0.8104pp)
saving ≥10% 的最小 drop  = 3.7518 pp
saving ≥20% 的最小 drop  = 10.1811 pp
saving ≥30% 的最小 drop  = 13.4815 pp
```
与对方 `summary.json` **每一位都一致**。**G2 的核心结论（0/0/0）成立。**

### G2 位置来源（这是 G2 唯一真正重要的前提）
逐环境按 `probe_manifest.json` 里记录的 `deer_bank` 路径回查
`deer_confidence_bank_cap30/full/*/trials.jsonl.gz` 的嵌套 `trials[].token_position`：

- 659 个问题的 boundary 位置集合**全部是 DEER 自己记录位置的子集**，
  **不一致 0 个**，9,329 个 probe 全部落在 DEER 的边界上。
- 每问题最多 30 个位置，**cap-30 违规 0 次**。

即「只改变*读什么*、不改变*何时读*」这个设计确实做到了。

### 684 vs 659 的差额已查明
G1 有 684 条轨迹，G2 只有 659 个问题。差的 **25 个问题，DEER 自己记录的 trials 数就是 0**
——这些轨迹根本不存在推理边界，没有位置可探。**属于设计强制，不是覆盖缺陷。**

---

## 二、发现的问题

### F1（实质性）—— G1 的 headline 用了 pooled，而协议强制 macro

`probe_wording_v5.json` 里同时存在 `pooled` 和 `macro` 两套分箱数据，但
**`headlines` 块只序列化了 pooled 和 per-model，没有 macro 条目**
（脚本里 `macro_window()` 是存在的，第 467–468 行用了，却没进 headline）。
`report.md` 与最终报告引用的是 pooled。

CLAUDE.md 的协议强制条款：**「Macro, never pooled. 每个 headline 指标都对 18 个环境
macro 平均。Pooled 只能作为稳健性检查，永远不能替代。」**

我从 `per_position.csv` 按环境重算 macro（18 个环境等权）：

| 指标 | v3（论文现值） | **v5 macro（协议口径）** | v5 pooled（对方报告的） |
|---|---|---|---|
| first-tenth 分歧 | 53.51%（n=213） | **54.45%**（18 env，range 23.5–93.0） | 45.87%（n=4360） |
| final-third 分歧 | 10.47%（n=773） | **16.40%**（range 5.5–49.2） | 13.01%（n=14050） |
| overall 分歧 | 24.0% | **33.92%** | 24.59% |

按模型的 macro：DeepSeek-7B first-tenth **68.61%** / final-third **22.80%**；
Qwen3-8B **40.29%** / **9.99%**。

**这直接推翻了对方报告里的定性结论。** 对方写的是
「去掉长度选择后早期分歧*缩小*了（53.5%→45.9%），v3 的子样本高估了早期效应」。
按协议口径不是这样：

1. **v3 的 53.51% 几乎原样复现（54.45%）**——长度选择并没有高估早期效应。
2. **晚期分歧不是微升而是从 10.47% 升到 16.40%。**
3. 早期/晚期的落差因此**变大**（54.45 vs 16.40），§4.2 的论证比 v3 更强，不是更弱。

pooled 之所以偏低：math500 每环境 100 题、aime24 只有 6 题，而 pooling 还按 probe
位置数加权，长轨迹（aime24）贡献的位置数远多于短轨迹——正是协议禁止 pooled 做
headline 的原因。

**处理建议：** 让远端 agent（或本机）把 macro 补进 `headlines` 并重写 `report.md`
的定性判断；两套口径都报，**macro 作为 headline，pooled 作为稳健性检查**。
在此之前 **G1 的结论不要写进论文**。注意：这条对论文是**好消息**。

### F2（次要，需披露或补算）—— G2 的两条 frontier 不是同一个题集

`summary.json` 把 `frontier_boundary`（659 题）与
`frontier_committed_fixed_grid`（2.657 / 6.167 / 11.759 pp，来自完整 684 题的已提交 sweep）
并排比较，`report.md` **没有说明两者题集不同**，也没提 25 题的差额。

- 对 **headline 无影响**：0/0/0 是在 boundary 流自身上算的。
- 但那条「boundary 的安全角能省 3.93%，而已提交网格一条都没有」的**支撑性对比**
  跨了不同题集，而且被排除的 25 题恰好是 DEER 无法动作的那些——审稿人可以挑这个。

**处理建议：** 要么在 report 里加一句限定，要么把已提交网格**限制到同样 659 题**重算
（纯 CPU，用第 2 轮 C2 那套 replay 机器即可）。后者更干净。

---

## 三、第一轮验收结论

**G2 通过，可用。** 结论、数字、位置来源、cap 全部独立复现。

**G1 数据层通过，分析层需返工一次。** 采集本身（配对、覆盖、完整性）无懈可击，
且逐字节可复现；但 headline 用错了加权口径，导致报告里的定性结论与协议口径相反。
改的是分析脚本的一个输出块，不需要重跑 GPU。

---

# 四、返工复核（2026-08-08，`cbe1c8e3`）

F1/F2 已派回远端修复。**同样不采信自述**，逐条重算：

### 分支完整性
真 merge，非 rebase：`cbe1c8e3` → `e6f18494`（merge）→ `ce1e3b2c`/`e4407f23`/`e74bf610` 与
`28659fe1`/`a4bc0333` 两支并入。`ce1e3b2c`、`e74bf610`、`28659fe1` 全部仍是祖先，
**没有 force-push，没有历史重写**。（它报告里说 G1/G2 commit「rebased 到 6229d93d」是它自己看错了，
实际历史干净。）

### 改动范围
`per_position.csv` 相对 `e74bf610` **零差异**；`dense_simple32` / `dense_certaindex32` /
`boundary_simple32` / `main` / `traj` / DEER bank 在返工 diff 中**零出现**。纯分析层，属实。

### F1 复核 —— 通过
`headlines` 现有 `macro` / `macro_deepseek7b` / `macro_qwen3_8b`。与我的独立计算逐位一致：

```
macro           first_tenth 54.4495   final_third 16.3957   overall 33.9192
macro_deepseek7b            68.6115               22.7990              45.1988
macro_qwen3_8b              40.2875                9.9925              22.6396
```
本机 `unittest test_governor_v2` **29 tests OK**（新增 3 条 `ProbeWordingV5MacroTests`
钉住 54.45 / 16.40）。定性判断已改正。

### F2 复核 —— 通过，而且我补了它没做的那一步
它的 659 数字来自**新 replay**，而全 684 数字来自**已提交 sweep archive**——
两条不同代码路径。那么 2.657→2.662 的差究竟是「限制到 659」还是「换了代码路径」？
它没验证这一点。我验证了：把它的 `_dense659_problem_ids` 换成返回全部问题，
用**同一条 fresh-replay 路径**跑全 684：

```
fresh replay (684):  2.6574074074074083 / 6.166666666666668 / 11.75925925925926
committed archive :  2.6574074074074083 / 6.166666666666668 / 11.75925925925926
```
**16 位全同。** 两条路径等价，所以那个差确实来自 659 限制，不是伪迹。
（附带收获：这等于用一次独立 replay **重新验证了已提交的 sweep archive 本身**。）

再独立重跑 659 限制版：
```
problems 659  envs 18
2.6622383252818045 / 6.191943590494315 / 11.809251939686723   gates 0/0/0
```
与它的 `summary.json` **16 位全同**。

like-for-like（同 659 题）：boundary 安全角省 **3.93%**（已提交网格 ≤1pp 一条都没有），
但 10/20/30% 的省 token 门槛在 boundary 上代价更大（3.75 / 10.18 / 13.48pp
vs 2.66 / 6.19 / 11.81pp），**所以仍然 0/0/0**。G2 结论不受影响。
25 题的排除对 frontier 的影响可以忽略（2.657→2.662）。

### 两个不影响结论的小事
1. `replay_rows.jsonl.gz` 从 383KB 涨到 1.1MB。按 `rule_id` 排序后压缩局部性变差
   （旧顺序按环境分组）。我逐行比对过：**内容完全相同**，只是仓库体积。
2. `compute_boundary_consensus_v5.py` 的 worker 依赖 fork 继承全局变量
   （`_RULES659` / `_DENSE659_CACHE`），在 macOS 的 spawn 下直接 `KeyError`。
   Linux 上没问题，但**在别的机器上复现会崩**——考虑到这篇论文的卖点是完整复现，
   值得和 D6 一起修（显式传参或 initializer）。

## 五、最终验收结论

**G1、G2 全部通过，可以合并。** F1 的修正对论文是**好消息**：v3 的 53.51% 基本原样复现
（54.45%），晚期从 10.47% 升到 16.40%，早晚落差反而**变大**——§4.2 在去掉长度选择和
单环境局限后比 v3 更硬。
