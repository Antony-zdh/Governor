# simple@32 oracle upper bound

This is a **non-deployable diagnostic**, not a Governor rule. It uses the reference
label to submit the first valid, correct interval-64 simple@32 probe; if none exists,
it falls back to the observed full trajectory. Probe output tokens are charged, while
probe prompt/prefill tokens are excluded consistently with the paper's generated-token metric.

| Scope | Trajectories | Full strict acc. | Oracle strict acc. | Correct-probe coverage | Fallback | First-correct token P25 / median / P75 | Token saving (micro) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pooled | 3,420 | 76.55% | 80.56% | 77.75% | 22.25% | 64 / 512 / 1216 | 46.70% |

Strict full accuracy requires natural completion and a correct final answer. The
parallel observed-answer columns retain capped-but-correct answers as a sensitivity
check. All inputs are frozen seen-model trajectories (two models, three benchmarks,
seeds 42--47, Train/Dev/Test); no unseen-model result is required.
