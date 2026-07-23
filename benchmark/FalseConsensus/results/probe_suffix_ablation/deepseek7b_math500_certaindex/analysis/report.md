# False Consensus — Stage 2-5 report

- problems logged: **500**
- overall accuracy: **79.6%**, finished naturally within budget: 60.8%

## Stage 2 · Agreement vs Accuracy

Cumulative share (plan.md definition, all probes of the trajectory):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    | 105 |        0.343 |      0.648 |
| 0.5-0.6 |  66 |        0.548 |      0.652 |
| 0.6-0.7 |  68 |        0.643 |      0.868 |
| 0.7-0.8 |  74 |        0.747 |      0.797 |
| 0.8-0.9 |  54 |        0.851 |      0.852 |
| 0.9-<1  |  31 |        0.926 |      0.935 |
| =1.0    | 102 |        1.000 |      0.922 |

Window share (last 5 probes — what a Governor actually sees):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  43 |        0.353 |      0.442 |
| 0.5-0.6 |   5 |        0.500 |      0.800 |
| 0.6-0.7 |  41 |        0.605 |      0.610 |
| 0.7-0.8 |  10 |        0.750 |      0.800 |
| 0.8-0.9 |  35 |        0.800 |      0.571 |
| =1.0    | 336 |        1.000 |      0.902 |

- cumulative share=1: 94 problems, accuracy 93.6% → false consensus 6
- window share=1: 336 problems, window-answer accuracy 89.6% → **false consensus 35 (10.4% of unanimous)**

## Stage 3 · False consensus cases

Exported 57 cases: [17, 18, 20, 21, 22, 25, 36, 39, 48, 60, 68, 82, 94, 103, 110, 145, 147, 154, 157, 165, 194, 202, 214, 217, 224, 228, 232, 240, 242, 246, 257, 264, 284, 292, 301, 306, 308, 317, 320, 324, 328, 332, 349, 352, 369, 376, 379, 381, 394, 400, 403, 422, 445, 456, 467, 481, 497]

## Stage 4 · Trajectory

- consensus at <512 tokens: n=150, accuracy=86.7%
- consensus at 512-1024 tokens: n=130, accuracy=79.2%
- consensus at 1024-1536 tokens: n=95, accuracy=83.2%
- consensus at 1536-2048 tokens: n=39, accuracy=79.5%
- consensus at >2048 tokens: n=25, accuracy=52.0%
- never reached window share ≥ 0.8: 61

Recovery: 160 problems held a 3-probe consensus that differed from their final answer (111 of them ended correct): [4, 11, 15, 19, 21, 22, 23, 24, 33, 36, 43, 46, 48, 52, 60, 62, 64, 68, 71, 73, 74, 75, 78, 80, 84, 85, 87, 90, 97, 100, 101, 104, 109, 110, 112, 114, 119, 123, 124, 125, 128, 129, 138, 143, 144, 145, 146, 150, 152, 153, 154, 155, 156, 157, 162, 165, 166, 168, 170, 171, 173, 175, 177, 188, 190, 194, 204, 208, 212, 213, 215, 217, 219, 220, 222, 224, 230, 231, 237, 239, 240, 241, 244, 245, 247, 248, 249, 253, 256, 260, 264, 266, 272, 273, 274, 280, 284, 286, 292, 294, 295, 296, 297, 305, 306, 309, 311, 315, 318, 322, 324, 326, 328, 331, 337, 341, 344, 349, 352, 355, 360, 362, 365, 369, 371, 372, 376, 378, 382, 389, 390, 391, 393, 394, 398, 401, 403, 409, 414, 415, 417, 420, 421, 422, 429, 432, 439, 446, 451, 460, 462, 464, 465, 466, 475, 478, 483, 491, 496, 498]
Initial belief: probe1 correct in 134/500; of the 366 problems with wrong probe1, **273 (74.6%) recovered to a correct final answer**.

## Stage 5 · Consensus reliability + Governor simulation

- CR(cumulative share=1) = 0.936
- CR(window share=1) = 0.896
- Consensus Calibration Error: cumulative = 0.132, window = 0.100

Governor early-stop simulation (stop when last 3 probes agree, certain, non-empty):
- would stop on 311/500 problems, stopped-answer accuracy **88.7%** (vs their final accuracy 90.0%)
- avg tokens saved on stopped problems: 683
- stops on a WRONG answer (the cost of false consensus): 35 problems [20, 21, 22, 25, 36, 39, 60, 68, 94, 103, 110, 145, 147, 154, 194, 214, 217, 224, 246, 257, 264, 284, 292, 301, 308, 324, 328, 332, 352, 369, 376, 394, 403, 456, 467]