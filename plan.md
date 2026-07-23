
# False Consensus Project Plan

**Project:** Understanding False Consensus in Adaptive Reasoning
**Goal:** 从 Governor Project 转向研究 *False Consensus*，即为什么模型能够稳定形成一致意见，却仍然给出错误答案。

---

# 进度（2026-07-22 更新）

| Stage | 状态 | 产出 |
|---|---|---|
| Stage 1 Logging | ✅ 完成（超额：500 题，非 100） | `benchmark/FalseConsensus/results/stage1_logging/`（probes.csv 8,739 行 + 500 条轨迹） |
| Stage 2 Agreement vs Accuracy | ✅ 完成 | Figure 1/1b/2 + 校准表（`analysis/report.md`） |
| Stage 3 False Consensus 分类 | ✅ 首轮完成 | 134 例导出；前 100 题 28 例已分类（`classify_cases.py`，待人工复核） |
| Stage 4 Trajectory | ✅ 完成 | 共识时间 / Recovery / Initial belief（Figure 4） |
| Stage 5 Consensus Reliability | ✅ 完成 | CR / CCE + Governor 早停模拟（Figure 5） |
| Stage 6 Governor++ | ⬜ 未开始 | 可先在现有 log 上离线回放 stop 规则 |

**核心结果**（DeepSeek-R1-Distill-Qwen-7B · MATH500×500 · budget 3072）：
全程一致 98.9% 可信（仅 1 例真假共识）；**窗口一致只有 93.5%（22 例假共识）**；
Dynasor 式早停损失 16.4 个百分点准确率（69.2% vs 85.6%，128 题停在错误答案）。
详见 `benchmark/FalseConsensus/FINDINGS.md` 与 `report/False_Consensus_Report_2026-07-22.pdf`。

**假设修正**：共识形成越**晚**越不可信（>2048 tokens 才形成的仅 58.1% 正确），
与下文 Stage 4"越早形成越容易错"的猜想方向相反。
另发现 probe 伪影两类：选项字母幻觉（Type E，占早停错误 21%）、超长答案空 probe。
日常工作记录见 `log.md`。

---

# 整体路线

整个项目分成五个阶段：

```
Stage 1
↓
Logging（记录所有Probe）

↓

Stage 2
↓
Agreement vs Accuracy

↓

Stage 3
↓
False Consensus Analysis

↓

Stage 4
↓
Consensus Reliability

↓

Stage 5
↓
Governor++
```

不要一开始改Governor。

先回答：

> Agreement到底是不是Correctness？

---

# Stage 1 Logging（第一周）

## 目标

建立一个完整的数据集。

Governor现在不要控制模型。

Governor只负责：

> Logging。

最后得到一个csv。

---

## Logging Mode

关闭：

- early stop
- upgrade
- Governor decision

保留：

每次probe。

例如

```
Question

↓

Probe1

↓

Probe2

↓

Probe3

↓

...

↓

Final Answer
```

全部记录。

---

## 每个Probe记录什么？

建议csv字段：

| 字段            | 含义                   |
| --------------- | ---------------------- |
| problem_id      | 题号                   |
| dataset         | MATH500                |
| token_position  | 当前token数            |
| probe_id        | 第几个probe            |
| probe_answer    | 当前答案               |
| share           | 当前最大答案比例       |
| entropy         | 当前normalized entropy |
| unique_answers  | 不同答案数量           |
| dominant_answer | 当前多数答案           |
| reasoning       | probe输出              |
| final_answer    | 最终答案               |
| final_correct   | 是否正确               |

例如：

```
problem_id=23

probe=1

answer=5

share=0.33

entropy=0.91
```

---

## 实验设置

先固定。

模型：

DeepSeek-R1

dataset：

MATH500

budget：

3072

temperature：

固定

window：

固定

probe interval：

固定

不要改参数。

---

## 第一批数据

先跑

100题。

不要500。

因为：

后面会调很多代码。

---

# Stage 2 Agreement vs Accuracy

这是整个项目最重要的实验。

---

## Experiment 1

统计：

```
Agreement

↓

Accuracy
```

定义：

```
Agreement

=

dominant answer share
```

例如：

```
AAAAAA

share=1
```

```
AAAABB

share=0.67
```

---

## 统计

画：

```
share

↓

accuracy
```

例如：

```
0.5

↓

35%

0.6

↓

48%

0.7

↓

61%

0.8

↓

70%

0.9

↓

75%

1.0

↓

72%
```

如果：

```
share=1

accuracy≠100%
```

False Consensus成立。

---

## Figure 1

画Calibration Curve。

横轴：

Agreement。

纵轴：

Accuracy。

论文第一张图。

---

## Figure 2

Histogram。

统计：

```
share

distribution
```

看看：

大量题是不是都到：

```
share=1
```

---

# Stage 3 False Consensus

## 找出所有：

```
share=1

AND

wrong
```

全部导出来。

例如：

```
Problem 13

share=1

wrong
```

保存。

---

## 分类

人工分类。

建议：

### Type A

数字坍缩

例如：

```
1

1

1

1
```

---

### Type B

表达式坍缩

```
[2,102)

[2,102)
```

---

### Type C

符号错误

例如：

```
>

>=
```

---

### Type D

推导遗漏

例如：

少讨论一个case。

---

### Type E

格式问题

---

统计：

```
Type

↓

Count
```

画Pie Chart。

---

# Stage 4 Trajectory Analysis

研究：

belief什么时候形成。

例如：

```
A

↓

A

↓

A

↓

A
```

还是：

```
A

↓

B

↓

A

↓

B
```

---

## 定义

Consensus Time。

例如：

第一次：

```
share>=0.8
```

出现的位置。

统计：

```
Consensus Time

↓

Accuracy
```

是不是：

越早形成：

越容易错？

---

## Recovery

统计：

```
share=1

↓

后来有没有翻盘？
```

例如：

```
AAAAAA

↓

BBBBBB
```

有没有？

比例多少？

---

## Initial Belief

统计：

Probe1。

如果：

```
Probe1

错
```

最后：

多少还能翻盘？

例如：

```
Probe1 Wrong

↓

Final Correct
```

统计。

---

# Stage 5 Consensus Reliability

不是研究：

Agreement。

而是：

Agreement什么时候可信。

---

## 定义

Consensus Reliability

```
CR

=

P(correct

|

share=s)
```

例如：

```
share=1

↓

0.71
```

---

## Calibration Error

例如：

```
Agreement

100%

Accuracy

72%
```

误差：

```
28%
```

定义：

Consensus Calibration Error。

---

## Figure

Calibration Curve。

---

# Stage 6 Governor++

现在才开始。

不是：

```
Stop

=

Agreement
```

改成：

```
Stop

=

Agreement

AND

Reliable
```

---

## Reliable可以来自：

- entropy history
- trajectory stability
- verifier score
- reasoning diversity
- uncertainty

任选。

---

# 实验二

Governor++

vs

Governor

vs

Vanilla

比较：

Accuracy

Token

---

# Ablation

分别去掉：

Agreement

Trajectory

Entropy

Verifier

看看：

谁贡献最大。

---

# 多模型

至少：

DeepSeek

Qwen

Llama

---

# 多数据集

MATH500

↓

GSM8K

↓

AIME24

↓

AMC23

---

# 最终Figure规划

Figure1

Agreement vs Accuracy

---

Figure2

Agreement Distribution

---

Figure3

False Consensus Examples

---

Figure4

Belief Trajectory

---

Figure5

Consensus Calibration Curve

---

Figure6

Governor++

---

# Table规划

Table1

不同模型False Consensus Rate

---

Table2

不同数据集False Consensus Rate

---

Table3

Governor++

Accuracy

Token

---

Table4

Ablation

---

# 每周计划

Week1

- Logging Mode
- 跑100题
- 检查CSV格式

Week2

- Agreement vs Accuracy
- Calibration Curve
- 跑500题

Week3

- False Consensus分类
- Belief Trajectory分析

Week4

- Consensus Reliability指标
- Calibration Error指标

Week5

- Governor++
- Ablation
- 多模型实验

Week6

- 多数据集实验
- 整理论文图表

Week7

- 写论文
- 补实验
- 修改Story
