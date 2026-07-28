# DEER Fast-Path-Only 配对回放

日期：2026-07-28

状态：Train/Dev CPU 回放完成；Test 未读取

## 协议

本实验只改变原 `deer_frozen` 的一个决策：

```text
if confidence > 0.995 and parsed_trial_answer is non-empty:
    deliver parsed_trial_answer
    omit the formal DEER readout
else:
    preserve the original DEER result
```

Branch-and-Commit 未启用，主生成轨迹未改变。所有 accuracy 使用项目的严格数学
等价判分；公平 token 成本包含主序列和所有辅助生成 output tokens，prompt/prefill
tokens 单独记录。

## 宏平均结果

宏平均先在每个 benchmark 内汇总，再对 MATH500、AMC23、AIME24 等权平均。

| Split | 模型 | 原 DEER 准确率 | Fast 准确率 | Δacc | 原 DEER token 节省 | Fast token 节省 | Δsaving |
|---|---|---:|---:|---:|---:|---:|---:|
| Train | Qwen3-8B | 79.10% | 79.75% | +0.65pp | 17.17% | 20.21% | +3.04pp |
| Train | DeepSeek-7B | 67.55% | 68.96% | +1.41pp | 23.61% | 25.51% | +1.90pp |
| Dev | Qwen3-8B | 86.22% | 85.89% | -0.33pp | 16.29% | 18.69% | +2.39pp |
| Dev | DeepSeek-7B | 74.93% | 76.37% | +1.44pp | 20.16% | 22.17% | +2.01pp |

## Dev 配对诊断

- 684 条 Dev 轨迹中，340 条的 raw confidence 超过 0.995；
- 5 条 trial answer 为空，按 validity gate 回退原 readout；
- 实际 fast commit 335 条，占全部 Dev 的 48.98%；
- 16 条由原 readout 错误变为 trial answer 正确；
- 6 条由原 readout 正确变为 trial answer 错误；
- 避免 131,199 个 readout output tokens；
- 另避免 361,079 个 readout prompt/prefill tokens。

逐模型配对结果：

| 模型 | Fast commits | 错→对 | 对→错 | Pooled Δacc (95% CI) | 相对原 DEER 生成成本下降 (95% CI) |
|---|---:|---:|---:|---:|---:|
| Qwen3-8B | 161 | 0 | 3 | -0.88pp [-2.05, 0.00] | 5.39% [4.04, 6.93] |
| DeepSeek-7B | 174 | 16 | 3 | +3.80pp [0.29, 7.31] | 4.92% [2.99, 8.18] |

Qwen3-8B Dev 存在小幅 accuracy/token trade-off；DeepSeek-7B 同时改善准确率和
生成成本。因此 fast path 是有支持的独立组件，但不能声称对每个模型都严格支配
原 DEER。

## 复现信息

- Source commit：`e458a0742eacecca5e5af550b0323d5041cd2262`
- Protocol：`governor-v2-preregistered-2026-07-27.10`
- Split manifest SHA-256：`3d30cd624dd9cd637b5d3f40e030247d225114db6074c6b2d26a1351d676e9a6`
- DEER config SHA-256：`21c78cafc9e5babfc8cae7ee09513dbc0cc561a00d364aa29212673207529d25`
- 机器可读结果：`summary.json`

## 限制

这是对现有冻结 DEER trial/readout 的配对回放，不是新的在线生成实验；没有模拟
Branch-and-Commit，也没有读取 Test。
