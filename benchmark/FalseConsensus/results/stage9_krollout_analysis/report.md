# Stage 9 §7.5.3 — Why is late agreement unreliable?

Primary consensus: first last-5 window with at least 3 non-empty answers and mathematical-equivalence share ≥0.8. Consensus time is modeled on log2(tokens), so an odds ratio is the effect of doubling consensus time.

## Data and identification checks

- rollouts: **640** across **80** problems
- reached consensus: **591**; never: **49**
- relaxed share≥0.6 replication: **621** reached (the remote 621-row summary used this threshold despite labeling it ≥0.8)
- problems with within-problem consensus-time variation: **70/80**
- pass-rate vs problem mean consensus time: Spearman ρ=-0.602, p=3.48e-09

## Main within–between results (GEE, problem-clustered)

| Outcome | Within effect | Between/problem effect |
|---|---|---|
| Final correctness | OR 1.127 [0.906, 1.402], p=0.282, Δp=+1.9pp | OR 0.521 [0.323, 0.838], p=0.00725, Δp=-11.7pp |
| Consensus-answer correctness | OR 1.765 [1.255, 2.483], p=0.0011, Δp=+10.5pp | OR 0.447 [0.277, 0.722], p=0.001, Δp=-15.2pp |
| Terminality | OR 1.810 [1.297, 2.524], p=0.000476, Δp=+11.8pp | OR 0.721 [0.491, 1.057], p=0.0939, Δp=-7.0pp |

Random-intercept Bayesian GLMM estimates are stored alongside the GEE table in `model_results.csv`; agreement in direction is used as a robustness check.

## Root-cause result

- The pooled decline is primarily a **between-problem difficulty effect**: problems with later mean consensus have lower final accuracy.
- Within the same problem, later consensus does **not** predict lower final accuracy; the point estimate is slightly positive and non-significant.
- Within the same problem, later consensus is significantly more likely to be correct at the consensus point and more likely to be terminal. This reverses the naive pooled interpretation.
- The within relation is non-linear: very early consensus is often transient, the middle is safest, and extremely late trajectories weaken again.
- The main failure mode is therefore not 'late agreement is intrinsically unreliable'; it is **hard-problem mixing plus premature transient consensus**, amplified by token caps.

## Non-linearity check

| Outcome | Linear within term | Quadratic within term |
|---|---|---|
| Final correctness | OR 1.132 [0.944, 1.358], p=0.181, Δp=+1.9pp | OR 0.808 [0.681, 0.959], p=0.015 |
| Consensus-answer correctness | OR 2.653 [1.499, 4.696], p=0.000808, Δp=+15.1pp | OR 0.487 [0.299, 0.793], p=0.00381 |
| Terminality | OR 2.375 [1.562, 3.610], p=5.2e-05, Δp=+16.1pp | OR 0.604 [0.434, 0.842], p=0.00289 |

## Outcome decomposition

| Subset | N | Consensus accuracy | Terminality | Final accuracy | Cap | Recovery | Overthinking |
|---|---:|---:|---:|---:|---:|---:|---:|
| all_reached | 591 | 53.8% | 59.7% | 73.6% | 13.9% | 127 | 10 |
| natural_finish | 509 | 61.9% | 67.2% | 82.9% | 0.0% | 115 | 8 |
| math500 | 365 | 67.1% | 71.5% | 84.7% | 4.1% | 72 | 8 |
| aime24 | 226 | 32.3% | 40.7% | 55.8% | 29.6% | 55 | 2 |
| capped | 82 | 3.7% | 13.4% | 15.9% | 100.0% | 12 | 2 |
| never_consensus | 49 | N/A | N/A | 63.3% | 28.6% | 0 | 0 |

## Sensitivity: within effect on correctness

| Analysis | Within effect |
|---|---|
| natural_finish_final | OR 0.918 [0.729, 1.157], p=0.47, Δp=-1.2pp |
| math_final | OR 1.231 [0.765, 1.980], p=0.392, Δp=+2.1pp |
| aime_final | OR 1.053 [0.873, 1.271], p=0.588, Δp=+1.2pp |
| online_proxy_final | OR 1.052 [0.861, 1.287], p=0.619, Δp=+0.7pp |
| online_proxy_consensus | OR 1.624 [1.132, 2.329], p=0.0084, Δp=+8.6pp |
| schema_final_correct | OR 1.128 [0.906, 1.405], p=0.282, Δp=+1.9pp |
| schema_schema_consensus_correct | OR 1.742 [1.236, 2.455], p=0.00151, Δp=+10.3pp |
| schema_schema_terminal | OR 1.794 [1.268, 2.539], p=0.000957, Δp=+11.4pp |
| relaxed_final_correct | OR 0.984 [0.839, 1.155], p=0.846, Δp=-0.3pp |
| relaxed_relaxed_consensus_correct | OR 2.246 [1.570, 3.215], p=9.63e-06, Δp=+16.5pp |
| relaxed_relaxed_terminal | OR 2.157 [1.374, 3.385], p=0.000831, Δp=+16.0pp |

## Descriptive pooled curve

| CT bin | N | Consensus accuracy | Terminality | Final accuracy | Cap rate |
|---|---:|---:|---:|---:|---:|
| <512 | 140 | 66.4% | 68.6% | 83.6% | 5.0% |
| 512–1k | 129 | 65.9% | 68.2% | 86.0% | 8.5% |
| 1k–2k | 144 | 53.5% | 61.1% | 75.7% | 11.1% |
| 2k–4k | 104 | 41.3% | 48.1% | 62.5% | 23.1% |
| >4k | 74 | 27.0% | 41.9% | 44.6% | 32.4% |

## Descriptive within-problem curve

| Relative CT | N | Consensus accuracy | Terminality | Final accuracy | Cap rate |
|---|---:|---:|---:|---:|---:|
| earliest | 55 | 34.5% | 41.8% | 70.9% | 20.0% |
| early | 119 | 39.5% | 41.2% | 68.1% | 17.6% |
| middle | 177 | 68.9% | 73.4% | 81.4% | 7.9% |
| late | 94 | 45.7% | 55.3% | 68.1% | 17.0% |
| latest | 146 | 59.6% | 67.8% | 73.3% | 13.7% |

## Interpretation guardrails

- The within effect is observational: difficulty is locked by problem, but consensus time is not experimentally manipulated.
- Never-converged rollouts are excluded from conditional CT models and reported separately.
- AIME retains substantial token-cap censoring; natural-finish and MATH-only analyses are required before attributing a CT effect to trajectory dynamics.
- Do not divide logistic coefficients to claim a percentage decomposition; use odds ratios and average probability changes.
