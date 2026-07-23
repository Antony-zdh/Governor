# False Consensus — Stage 2-5 report

- problems logged: **40**
- overall accuracy: **60.0%**, finished naturally within budget: 37.5%

## Stage 2 · Agreement vs Accuracy

Cumulative share (plan.md definition, all probes of the trajectory):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  16 |        0.288 |      0.375 |
| 0.5-0.6 |  11 |        0.555 |      0.818 |
| 0.6-0.7 |   3 |        0.644 |      1.000 |
| 0.7-0.8 |   1 |        0.750 |      0.000 |
| 0.8-0.9 |   3 |        0.831 |      0.667 |
| 0.9-<1  |   3 |        0.935 |      0.333 |
| =1.0    |   3 |        1.000 |      1.000 |

Window share (last 5 probes — what a Governor actually sees):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |   8 |        0.325 |      0.125 |
| 0.6-0.7 |   3 |        0.600 |      0.000 |
| 0.8-0.9 |   4 |        0.800 |      0.000 |
| =1.0    |  25 |        1.000 |      0.920 |

- cumulative share=1: 3 problems, accuracy 100.0% → false consensus 0
- window share=1: 25 problems, window-answer accuracy 92.0% → **false consensus 2 (8.0% of unanimous)**

## Stage 3 · False consensus cases

Exported 11 cases: [4, 5, 8, 13, 15, 20, 31, 32, 35, 36, 39]

## Stage 4 · Trajectory

- consensus at <512 tokens: n=9, accuracy=55.6%
- consensus at 512-1024 tokens: n=3, accuracy=66.7%
- consensus at 1024-1536 tokens: n=7, accuracy=85.7%
- consensus at 1536-2048 tokens: n=6, accuracy=100.0%
- consensus at >2048 tokens: n=7, accuracy=57.1%
- never reached window share ≥ 0.8: 8

Recovery: 10 problems held a 3-probe consensus that differed from their final answer (4 of them ended correct): [4, 5, 12, 20, 24, 27, 28, 35, 36, 39]
Initial belief: probe1 correct in 8/40; of the 32 problems with wrong probe1, **18 (56.2%) recovered to a correct final answer**.

## Stage 5 · Consensus reliability + Governor simulation

- CR(cumulative share=1) = 1.000
- CR(window share=1) = 0.920
- Consensus Calibration Error: cumulative = 0.210, window = 0.215

Governor early-stop simulation (stop when last 3 probes agree, certain, non-empty):
- would stop on 31/40 problems, stopped-answer accuracy **67.7%** (vs their final accuracy 74.2%)
- avg tokens saved on stopped problems: 1412
- stops on a WRONG answer (the cost of false consensus): 10 problems [4, 5, 8, 13, 15, 20, 31, 32, 35, 36]