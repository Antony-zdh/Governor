# DEER-inspired Online Dev 实验报告

本轮为 seed 42 的 exploratory Dev 评估（加分项），不替代、也不回溯修改既有 Governor Pareto sweep。两个 BF16 模型在单张 RTX 5090 上依次在线服务，主推理从题目 prompt 在线生成，遇 `Wait` 转换且满足调度条件时现场 probe / 现场 verification branch，不拼接任何 frozen 轨迹的未来 suffix。

## 1. 方法与部署化定位

- **主方法 `deer_inspired_online_v1`**：1024 committed-main tokens 前只记录 `Wait` 不 probe；前 10 次实际 Stage-1 probe 保持 dense；之后进入 sparse（距上次实际 probe >=512 main tokens 才 probe）。Stage-1 confidence `>0.995` fast commit；`>0.97` 且距上次 branch >=512 进入 retained verification branch；branch 通过（Stage-2 `>0.99` 且两答案数学等价）则 commit，否则保留 verification reasoning、丢弃 Stage-2 并继续。
- **对照 `deer_online_reference`**：官方 DEER 在线 Wait-probe，从首个 `Wait` 起最多 10 次，confidence `>0.95` 后用 `prefix + "\n\n\n"` greedy readout（cap 4096）。无 fast path、无 verification branch。
- 两者共用同一 online engine、prompt、主采样（T=0.6, top_p=0.95）与 seed policy；**差异仅在触发调度与 branch 控制器**，报告据此区分方法差异。
- DeepSeek 用 `avg1`（算术平均，跳过首 token）；Qwen3 用 `avg2`（几何平均）且 confidence 仅当末 token 为 `</` 时有效（否则强制 0）。该 Qwen gate 同时适用于 Stage-1/Stage-2/reference。

## 2. 完整性审计

- 状态：`complete`；总结果数：456；方法计数：`{"deer_inspired_online_v1": 228, "deer_online_reference": 228}`。
- 每方法 228（2 模型 × 3 benchmark × seed 42，每模型 114 题），两方法合计 456；硬校验 seed=42、split=dev、单一 config hash、零 infrastructure error、all_generated_tokens 可逐行重算。

## 3. Benchmark 等权宏平均

| 方法 | 模型 | Macro Acc. | ΔAcc(vs full) | 公平 token saving | Main-only saving | Fast | Branch |
|---|---|---:|---:|---:|---:|---:|---:|
| deer_inspired_online_v1 | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 0.7267 | -0.0350 | 0.4178 | 0.4239 | 0.6222 | 0.1406 |
| deer_inspired_online_v1 | Qwen/Qwen3-8B | 0.8556 | +0.0278 | 0.4559 | 0.4732 | 0.7661 | 0.1572 |
| deer_inspired_online_v1 | all_models | 0.7911 | -0.0036 | 0.4369 | 0.4485 | 0.6942 | 0.1489 |
| deer_online_reference | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 0.7878 | +0.0261 | 0.3689 | 0.4573 | 0.0000 | 0.0000 |
| deer_online_reference | Qwen/Qwen3-8B | 0.7756 | -0.0522 | 0.1974 | 0.2767 | 0.0000 | 0.0000 |
| deer_online_reference | all_models | 0.7817 | -0.0131 | 0.2832 | 0.3670 | 0.0000 | 0.0000 |

## 4. 分环境结果（model × benchmark）

| 方法 | 模型 | Benchmark | n | Acc. | ΔAcc. | Fair saving | Main saving | 均生成token | Fast | Branch | Branch通过 | Capped | 均Stage-1 | P95 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| deer_inspired_online_v1 | Qwen3-8B | aime24 | 6 | 0.6667 | -0.1667 | 0.5614 | 0.5745 | 6932 | 0.8333 | 0.1667 | 0.1667 | 0.0000 | 12.17 | 29 |
| deer_inspired_online_v1 | Qwen3-8B | amc23 | 8 | 1.0000 | +0.2500 | 0.3779 | 0.4046 | 5587 | 0.8750 | 0.1250 | 0.1250 | 0.0000 | 12.62 | 22 |
| deer_inspired_online_v1 | Qwen3-8B | math500 | 100 | 0.9000 | +0.0000 | 0.4284 | 0.4404 | 2705 | 0.5900 | 0.1800 | 0.1700 | 0.0000 | 4.48 | 16 |
| deer_inspired_online_v1 | DeepSeek-7B | aime24 | 6 | 0.5000 | +0.0000 | 0.4144 | 0.4213 | 10530 | 0.6667 | 0.1667 | 0.1667 | 0.0000 | 20.33 | 51 |
| deer_inspired_online_v1 | DeepSeek-7B | amc23 | 8 | 0.7500 | -0.1250 | 0.5300 | 0.5359 | 4528 | 0.7500 | 0.1250 | 0.1250 | 0.1250 | 7.50 | 16 |
| deer_inspired_online_v1 | DeepSeek-7B | math500 | 100 | 0.9300 | +0.0200 | 0.3089 | 0.3144 | 2118 | 0.4500 | 0.1300 | 0.0900 | 0.0100 | 2.21 | 13 |
| deer_online_reference | Qwen3-8B | aime24 | 6 | 0.6667 | -0.1667 | 0.0796 | 0.1370 | 14555 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 8.00 | 10 |
| deer_online_reference | Qwen3-8B | amc23 | 8 | 0.7500 | +0.0000 | 0.0901 | 0.1508 | 9310 | 0.0000 | 0.0000 | 0.0000 | 0.2500 | 9.12 | 10 |
| deer_online_reference | Qwen3-8B | math500 | 100 | 0.9100 | +0.0100 | 0.4226 | 0.5424 | 3420 | 0.0000 | 0.0000 | 0.0000 | 0.0200 | 5.11 | 10 |
| deer_online_reference | DeepSeek-7B | aime24 | 6 | 0.8333 | +0.3333 | 0.3717 | 0.3992 | 9273 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 8.33 | 10 |
| deer_online_reference | DeepSeek-7B | amc23 | 8 | 0.7500 | -0.1250 | 0.3090 | 0.4385 | 5737 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 6.75 | 10 |
| deer_online_reference | DeepSeek-7B | math500 | 100 | 0.7800 | -0.1300 | 0.4260 | 0.5343 | 2188 | 0.0000 | 0.0000 | 0.0000 | 0.0300 | 2.84 | 10 |

## 5. Dev 汇总（pooled）

| 方法 | 模型 | n | Acc. | Fair saving | Main-only saving | Fast | Branch | Capped | 均Stage-1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deer_inspired_online_v1 | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 114 | 0.8947 | 0.3300 | 0.3355 | 0.4825 | 0.1316 | 0.0175 | 3.54 |
| deer_inspired_online_v1 | Qwen/Qwen3-8B | 114 | 0.8947 | 0.4319 | 0.4450 | 0.6228 | 0.1754 | 0.0000 | 5.46 |
| deer_inspired_online_v1 | all_models | 228 | 0.8947 | 0.3809 | 0.3903 | 0.5526 | 0.1535 | 0.0088 | 4.50 |
| deer_online_reference | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 114 | 0.7807 | 0.4150 | 0.5204 | 0.0000 | 0.0000 | 0.0263 | 3.40 |
| deer_online_reference | Qwen/Qwen3-8B | 114 | 0.8860 | 0.3812 | 0.4936 | 0.0000 | 0.0000 | 0.0351 | 5.54 |
| deer_online_reference | all_models | 228 | 0.8333 | 0.3981 | 0.5070 | 0.0000 | 0.0000 | 0.0307 | 4.47 |

## 6. Wait 调度器诊断（主方法）

- 观测 `Wait` 总数：3117；1024 前记录但不 probe 的 `Wait` 涉及题数：204/228。
- dense Stage-1 probe 总数：742；sparse probe 总数：283；512-gap 跳过总数：1327（不排队、不后延）。
- 平均 Stage-1 attempts：4.50；无隐藏 hard cap（reference 仍严格 <=10，主方法 sparse 可超过）。

## 7. 对比

| 对比 | 配对/路径 | counterfactual | ΔAcc | ΔToken |
|---|---|---|---:|---:|
| new_online_vs_online_reference | same online engine, same Dev IDs, seed 42 (paired) | strict | +0.0614 | -685.0 |
| new_online_vs_existing_full | online multi-request path vs single-request frozen main trajectory (paired by ID) | approximate (sampling path differs) | +0.0088 | -2535.7 |
| online_reference_vs_frozen_deer | online Wait-probe readout vs frozen-trajectory DEER replay (env-level, non-paired) | non-strict (frozen main text differs from online main) | +0.0292 | -622.4 |
| new_online_vs_fast_path_only_replay | fast-path-only frozen replay | n/a | n/a | n/a |

## 8. 配对不确定性

按 benchmark 分层、方法间逐题配对 10,000 次 bootstrap（seed 20260728），三 benchmark 等权。

- Accuracy difference（proposed−reference）mean=+0.0097，95% CI [-0.1050, +0.1256]。
- Token-saving advantage mean=+0.1532，95% CI [+0.0733, +0.2293]。

## 9. 限制与说明

- 在线 controller 的多请求采样路径与既有 single-request full baseline 不完全相同，故 vs-existing-full 为近似 counterfactual，已明确标记。
- 本轮仅 1 个 seed，不能估计 seed variance；AMC23(8)/AIME24(6) 样本很小，所有区间与结论均为 exploratory。
- 未读取 Test/confirmation；阈值、verification budget、prompt、采样与 cap 未依本轮结果改动。
- 原 Governor Pareto sweep 未改动；本轮为加分项。
- fast_path_only_replay 数据在当前 checkout 中不存在，对应对比项标记为 n/a。
- capped / invalid trial：主方法 capped 率 0.0088，invalid trial 率 0.2166。

## 10. 产物清单

- per-problem 结果：456 条；config_sha256=`fb238f6a78144a99…`；dtype=bfloat16。
- 各模型 pinned revision：DeepSeek `916b56a44061…`，Qwen3 `b968826d9c46…`。
- 各 aggregate 产物 SHA-256 见 `artifact_manifest.json`。