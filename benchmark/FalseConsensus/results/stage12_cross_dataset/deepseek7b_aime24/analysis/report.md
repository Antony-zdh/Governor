# False Consensus — Stage 2-5 report

- problems logged: **30**
- overall accuracy: **26.7%**, finished naturally within budget: 0.0%

## Stage 2 · Agreement vs Accuracy

Cumulative share (plan.md definition, all probes of the trajectory):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  24 |        0.255 |      0.208 |
| 0.5-0.6 |   4 |        0.521 |      0.500 |
| 0.6-0.7 |   1 |        0.667 |      0.000 |
| 0.7-0.8 |   1 |        0.750 |      1.000 |

Window share (last 5 probes — what a Governor actually sees):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  15 |        0.293 |      0.000 |
| 0.6-0.7 |   1 |        0.600 |      0.000 |
| 0.7-0.8 |   1 |        0.750 |      0.000 |
| 0.8-0.9 |   4 |        0.800 |      0.250 |
| =1.0    |   9 |        1.000 |      0.778 |

- cumulative share=1: 0 problems, accuracy nan% → false consensus 0
- window share=1: 9 problems, window-answer accuracy 77.8% → **false consensus 2 (22.2% of unanimous)**

## Stage 3 · False consensus cases

Exported 11 cases: [3, 7, 8, 15, 16, 17, 20, 22, 23, 24, 25]

## Stage 4 · Trajectory

- consensus at <512 tokens: n=1, accuracy=100.0%
- consensus at 512-1024 tokens: n=0, accuracy=-
- consensus at 1024-1536 tokens: n=3, accuracy=33.3%
- consensus at 1536-2048 tokens: n=3, accuracy=66.7%
- consensus at >2048 tokens: n=11, accuracy=36.4%
- never reached window share ≥ 0.8: 12

Recovery: 12 problems held a 3-probe consensus that differed from their final answer (5 of them ended correct): [7, 8, 10, 11, 16, 19, 20, 21, 23, 24, 25, 29]
Initial belief: probe1 correct in 0/30; of the 30 problems with wrong probe1, **8 (26.7%) recovered to a correct final answer**.

## Stage 5 · Consensus reliability + Governor simulation

- CR(cumulative share=1) = nan
- CR(window share=1) = 0.778
- Consensus Calibration Error: cumulative = 0.071, window = 0.332

Governor early-stop simulation (stop when last 3 probes agree, certain, non-empty):
- would stop on 15/30 problems, stopped-answer accuracy **26.7%** (vs their final accuracy 53.3%)
- avg tokens saved on stopped problems: 1323
- stops on a WRONG answer (the cost of false consensus): 11 problems [3, 7, 8, 15, 16, 17, 20, 22, 23, 24, 25]