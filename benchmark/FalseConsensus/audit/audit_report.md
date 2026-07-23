# Stage 6 -- Probe Validity Audit report (Round 1, n=100)

**标注方法说明**：plan.md SS4.5 的 Round 1 设计假设两名独立标注者以计算 Cohen's kappa；实际只有用户一人标注（见 log.md 说明），因此本报告不含 kappa/raw agreement 指标（不编造第二人的数据），仅报告单一标注者结果。已标注 100/296 个案例，覆盖全部 6 个抽样组（每组 10-23 例，非均匀，因为标注是按案例文件顺序做到 100 个就停止，而不是按组配额精确切分）。

## 主标签分布

label
supported_correct           37
supported_wrong              1
tentative_guess             25
incomplete_answer           10
format_artifact             26
inconsistent_with_prefix     0
ambiguous                    1


## 1. Probe validity rate（整体）

- `valid_as_current_answer` = True 的比例：**39.0%** (95% CI [30.0%, 49.0%], n=100)

## 2. Validity by token position

position_bin  n  validity_rate  ci95_lo  ci95_hi
        <512 10       0.200000 0.000000 0.500000
    512-1024 26       0.384615 0.192308 0.576923
   1024-2048 34       0.470588 0.294118 0.647059
       >2048 30       0.366667 0.200000 0.533333


## 3. Validity by answer type

  answer_type  n  validity_rate  ci95_lo  ci95_hi
        empty 10       0.200000 0.000000 0.500000
        other 65       0.569231 0.446154 0.692308
single_letter 25       0.000000 0.000000 0.000000


## 4. Validity by local consensus strength

(local_share = 当前 probe 前后 context_probes 中与当前答案一致的比例，作为逐案例 consensus strength 的代理指标，因为原始 case 记录没有直接存 cumulative/window share 字段)

  share_bin  n  validity_rate  ci95_lo  ci95_hi
  0 (无邻居一致)  8       0.125000 0.000000 0.375000
      0-0.5 31       0.064516 0.000000 0.161290
0.5-1 (不含1) 29       0.344828 0.172414 0.517241
 1.0 (完全一致) 32       0.812500 0.656250 0.937500


## 5. Validity by final correctness

 final_correct  n  validity_rate  ci95_lo  ci95_hi
         False 28       0.142857 0.035714 0.285714
          True 72       0.486111 0.375000 0.597569


## 6. Forced-guess rate（tentative_guess 占比）

- 25.0% (n=100)

## 7. Artifact rate（format_artifact 占比）

- 26.0% (n=100)

## 8. P(final correct | supported_wrong)

- 0.0% (n=1)

## 9. P(final correct | tentative_guess)

- 52.0% (n=25)

## SS4.7 关键判断标准（限定在 probe 与 final 不一致的案例，n=56）

- 情况 A 相关（tentative_guess 占比）：37.5%
- 情况 B 相关（supported_wrong 占比）：1.8%，其中最终 recover 到正确答案的：0.0%
- 情况 C 相关（format_artifact 占比）：37.5%

**初步结论**：三者中 情况A 占比最高（37.5%），但 n 较小（尤其在再细分到某个 answer_type/position 时），结论应视为方向性而非最终定论，建议 Stage 6 Round 3 扩大样本后复核。