# DEER-Pro `C_cali` 本地回溯：可行性审计与 token-MAD 诊断

## 结论

- 审计覆盖 **2,736** 条 train/dev trajectory、**12,024** 次已保存 DEER trial；原 DEER 在 **1,993** 条 trajectory 上早停。
- 每个 transition 最多只有 **1** 个 answer-inducing prompt，而 DEER-Pro 的 `C_cali` 需要同一 transition 上 `N=4` 个不同 inducer。因此，现有日志**不能 faithful 地计算 `C_cali`**；这不是 CPU 算力问题，而是缺少三次反事实模型输出。
- 下表的 `token-MAD` 只是在单次 trial 内对 token probability 做 MAD 惩罚的诊断 surrogate。它回答“单次答案内部概率波动是否有筛选价值”，不能作为 DEER-Pro 复现结果。

DEER-Pro 论文定义：

$$C_{\mathrm{cali}}=C_{\mathrm{avg}}-\alpha C_{\mathrm{MAD}},\quad C_{\mathrm{MAD}}=\frac1N\sum_i|C_i-C_{\mathrm{avg}}|,$$

其中每个 $C_i$ 来自不同 answer-inducing prompt；论文设置 $N=4$、$\alpha=1$、阈值 $\lambda=0.95$。

## CPU-only token-MAD surrogate

若 surrogate 拒绝原 DEER 的首个 stop，本回溯让它退回完整答案，并只计入已经实际观测到的 trial output；由于没有继续生成后续 transition，这个 token saving 是**乐观上界/额外成本下界**。

| Split | α | Accuracy | ΔAcc vs full | Accept rate | Accepted acc. | Token saving* |
|---|---:|---:|---:|---:|---:|---:|
| dev | 0 | 85.23% | -3.65 pp | 71.05% | 88.48% | 29.37% |
| dev | 0.25 | 85.38% | -3.51 pp | 67.11% | 89.11% | 26.10% |
| dev | 0.5 | 85.67% | -3.22 pp | 65.06% | 89.89% | 24.51% |
| dev | 1 | 86.11% | -2.78 pp | 60.96% | 90.41% | 22.20% |
| dev | 2 | 85.82% | -3.07 pp | 57.75% | 90.63% | 19.83% |
| train | 0 | 84.31% | -4.14 pp | 73.44% | 89.91% | 28.62% |
| train | 0.25 | 84.65% | -3.80 pp | 69.05% | 90.76% | 25.72% |
| train | 0.5 | 84.89% | -3.56 pp | 66.28% | 91.18% | 24.14% |
| train | 1 | 85.28% | -3.17 pp | 63.45% | 91.86% | 22.61% |
| train | 2 | 85.48% | -2.97 pp | 59.41% | 92.29% | 20.33% |

\* surrogate 拒绝后的后续 probe 未观测，故不是可部署成本的精确估计。

## 解释边界

- `α=0` 精确还原当前 model-specific DEER threshold 决策，是一致性检查。
- `α>0` 只会比原 DEER 更保守；它不能发现原 collector 在首次拒绝后本应出现的更晚 stop。
- faithful `C_cali` 需要 GPU 为每个 transition 补齐另外 3 个 varied inducers；应另立 preregistered probe-only 实验，不能从本表外推。

## 产物

- `decision_rows.csv`：逐 trajectory、逐 α 的 paired 决策。
- `pooled_summary.csv`：split × model × benchmark 的 pooled 指标。
- `environment_summary.csv`：split × model × benchmark × seed 指标。
- `manifest.json`：输入覆盖、公式边界和输入 SHA-256。
