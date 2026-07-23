# False Consensus — Stage 2-5 report

- problems logged: **100**
- overall accuracy: **80.0%**, finished naturally within budget: 68.0%

## Stage 2 · Agreement vs Accuracy

Cumulative share (plan.md definition, all probes of the trajectory):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  21 |        0.334 |      0.476 |
| 0.5-0.6 |  18 |        0.543 |      0.722 |
| 0.6-0.7 |   6 |        0.625 |      1.000 |
| 0.7-0.8 |  19 |        0.748 |      0.842 |
| 0.8-0.9 |   9 |        0.852 |      0.889 |
| 0.9-<1  |   4 |        0.914 |      1.000 |
| =1.0    |  23 |        1.000 |      1.000 |

Window share (last 5 probes — what a Governor actually sees):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  13 |        0.388 |      0.462 |
| 0.5-0.6 |   1 |        0.500 |      0.000 |
| 0.6-0.7 |  10 |        0.600 |      0.600 |
| 0.7-0.8 |   1 |        0.750 |      0.000 |
| 0.8-0.9 |   3 |        0.800 |      0.333 |
| =1.0    |  68 |        1.000 |      0.926 |

- cumulative share=1: 23 problems, accuracy 100.0% → false consensus 0
- window share=1: 68 problems, window-answer accuracy 91.2% → **false consensus 6 (8.8% of unanimous)**

## Stage 3 · False consensus cases

Exported 28 cases: [4, 9, 11, 14, 18, 19, 22, 23, 25, 33, 34, 36, 39, 43, 46, 58, 59, 64, 68, 73, 74, 75, 76, 89, 90, 92, 95, 96]

## Stage 4 · Trajectory

- consensus at <512 tokens: n=37, accuracy=89.2%
- consensus at 512-1024 tokens: n=21, accuracy=90.5%
- consensus at 1024-1536 tokens: n=18, accuracy=88.9%
- consensus at 1536-2048 tokens: n=7, accuracy=71.4%
- consensus at >2048 tokens: n=4, accuracy=0.0%
- never reached window share ≥ 0.8: 13

Recovery: 35 problems held a 3-probe consensus that differed from their final answer (20 of them ended correct): [2, 4, 9, 11, 14, 15, 17, 18, 19, 21, 22, 23, 25, 34, 36, 41, 43, 46, 58, 59, 62, 64, 68, 73, 74, 75, 76, 80, 82, 89, 90, 92, 94, 95, 96]
Initial belief: probe1 correct in 30/100; of the 70 problems with wrong probe1, **52 (74.3%) recovered to a correct final answer**.

## Stage 5 · Consensus reliability + Governor simulation

- CR(cumulative share=1) = 1.000
- CR(window share=1) = 0.912
- Consensus Calibration Error: cumulative = 0.109, window = 0.090

Governor early-stop simulation (stop when last 3 probes agree, certain, non-empty):
- would stop on 84/100 problems, stopped-answer accuracy **67.9%** (vs their final accuracy 84.5%)
- avg tokens saved on stopped problems: 1238
- stops on a WRONG answer (the cost of false consensus): 27 problems [4, 9, 11, 14, 18, 19, 22, 23, 25, 33, 34, 36, 39, 43, 58, 59, 64, 68, 73, 74, 75, 76, 89, 90, 92, 95, 96]