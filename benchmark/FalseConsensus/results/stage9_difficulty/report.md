# Stage 9 (partial) — Difficulty-controlled mechanism analysis

Deferred: Analysis 3 (matched comparison), Analysis 4 (recovery probability model), and `probe_validity` as a regression feature (needs Stage 6 human annotations, which don't exist yet — Analysis 2 should be re-run once `audit/annotations.csv` lands).

## Analysis 1 · Stratified consensus-time vs accuracy by MATH level

|   level | consensus_time_bin   |   accuracy |   n |
|--------:|:---------------------|-----------:|----:|
|       1 | <512                 |      0.944 |  18 |
|       1 | 512-1024             |      1.000 |  14 |
|       1 | 1024-1536            |      0.667 |   3 |
|       2 | <512                 |      0.927 |  41 |
|       2 | 512-1024             |      0.963 |  27 |
|       2 | 1024-1536            |      1.000 |  11 |
|       3 | <512                 |      0.917 |  36 |
|       3 | 512-1024             |      0.914 |  35 |
|       3 | 1024-1536            |      0.875 |  16 |
|       3 | 1536-2048            |      1.000 |   3 |
|       4 | <512                 |      0.828 |  29 |
|       4 | 512-1024             |      0.919 |  37 |
|       4 | 1024-1536            |      0.900 |  30 |
|       4 | 1536-2048            |      0.778 |   9 |
|       4 | >2048                |      0.500 |   8 |
|       5 | <512                 |      0.650 |  20 |
|       5 | 512-1024             |      0.650 |  40 |
|       5 | 1024-1536            |      0.824 |  17 |
|       5 | 1536-2048            |      0.750 |  24 |
|       5 | >2048                |      0.615 |  13 |

## Analysis 2 · Logistic regression, P(final correct)

5-fold CV accuracy: 84.2% +/- 3.5% (vanilla base rate: 81.2%)

| feature                        |   coef |   odds_ratio |
|:-------------------------------|-------:|-------------:|
| hit_token_cap_False            |  1.603 |        4.968 |
| subject_Number Theory          |  1.364 |        3.912 |
| subject_Algebra                |  0.825 |        2.283 |
| consensus_time                 |  0.173 |        1.189 |
| num_switches                   |  0.168 |        1.184 |
| subject_Counting & Probability |  0.068 |        1.070 |
| subject_Intermediate Algebra   | -0.193 |        0.824 |
| subject_Prealgebra             | -0.261 |        0.770 |
| level                          | -0.360 |        0.698 |
| avg_entropy                    | -0.486 |        0.615 |
| subject_Precalculus            | -0.869 |        0.419 |
| subject_Geometry               | -0.934 |        0.393 |
| hit_token_cap_True             | -1.603 |        0.201 |

## Stage 9.4 · Terminality / Correctness / Safe-stop probability (plan.md §7.4)

| share_bin   |   n_probes |   terminality_T |   correctness_C |   safe_stop_S |
|:------------|-----------:|----------------:|----------------:|--------------:|
| <0.5        |       2696 |           0.232 |           0.189 |         0.174 |
| 0.5-0.6     |       1377 |           0.415 |           0.368 |         0.348 |
| 0.6-0.7     |       1058 |           0.603 |           0.515 |         0.500 |
| 0.7-0.8     |        741 |           0.737 |           0.656 |         0.642 |
| 0.8-0.9     |        684 |           0.750 |           0.633 |         0.621 |
| 0.9-<1      |        232 |           0.707 |           0.409 |         0.401 |
| =1.0        |       1951 |           0.602 |           0.557 |         0.540 |

Interpretation check: if T (terminality) and C (correctness) diverge meaningfully across bins (e.g. high C but low T at moderate share), that supports plan.md's core claim that agreement alone isn't enough — safe-stop needs both correctness and terminality, not just share.