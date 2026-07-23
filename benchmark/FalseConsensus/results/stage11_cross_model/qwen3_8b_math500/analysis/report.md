# False Consensus — Stage 2-5 report

- problems logged: **500**
- overall accuracy: **78.2%**, finished naturally within budget: 35.0%

## Stage 2 · Agreement vs Accuracy

Cumulative share (plan.md definition, all probes of the trajectory):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  70 |        0.378 |      0.514 |
| 0.5-0.6 |  58 |        0.538 |      0.655 |
| 0.6-0.7 |  51 |        0.651 |      0.804 |
| 0.7-0.8 |  80 |        0.748 |      0.800 |
| 0.8-0.9 |  81 |        0.848 |      0.877 |
| 0.9-<1  |  64 |        0.941 |      0.891 |
| =1.0    |  96 |        1.000 |      0.875 |

Window share (last 5 probes — what a Governor actually sees):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  14 |        0.356 |      0.214 |
| 0.5-0.6 |   5 |        0.500 |      0.400 |
| 0.6-0.7 |  30 |        0.613 |      0.467 |
| 0.7-0.8 |   7 |        0.750 |      0.429 |
| 0.8-0.9 |  43 |        0.800 |      0.581 |
| =1.0    | 372 |        1.000 |      0.901 |

- cumulative share=1: 88 problems, accuracy 92.0% → false consensus 7
- window share=1: 372 problems, window-answer accuracy 89.0% → **false consensus 41 (11.0% of unanimous)**

## Stage 3 · False consensus cases

Exported 80 cases: [4, 7, 14, 17, 18, 21, 25, 33, 36, 46, 60, 64, 67, 71, 78, 84, 95, 96, 100, 109, 114, 120, 128, 130, 134, 144, 145, 154, 155, 168, 171, 188, 190, 197, 204, 205, 213, 217, 219, 231, 235, 236, 240, 257, 264, 266, 284, 286, 302, 308, 312, 324, 327, 332, 337, 338, 340, 341, 358, 364, 369, 371, 379, 382, 392, 403, 419, 422, 432, 439, 454, 456, 460, 466, 467, 478, 484, 493, 495, 498]

## Stage 4 · Trajectory

- consensus at <512 tokens: n=197, accuracy=78.7%
- consensus at 512-1024 tokens: n=136, accuracy=86.8%
- consensus at 1024-1536 tokens: n=82, accuracy=81.7%
- consensus at 1536-2048 tokens: n=39, accuracy=76.9%
- consensus at >2048 tokens: n=20, accuracy=55.0%
- never reached window share ≥ 0.8: 26

Recovery: 161 problems held a 3-probe consensus that differed from their final answer (108 of them ended correct): [2, 4, 11, 19, 21, 26, 29, 30, 33, 34, 36, 39, 43, 46, 50, 51, 60, 62, 64, 67, 75, 78, 80, 84, 85, 90, 95, 96, 101, 104, 107, 109, 114, 119, 120, 123, 124, 125, 129, 130, 134, 138, 144, 145, 150, 152, 153, 155, 162, 163, 164, 166, 170, 171, 175, 177, 180, 181, 184, 186, 187, 188, 189, 190, 194, 197, 205, 209, 210, 213, 217, 219, 220, 221, 224, 228, 231, 234, 235, 238, 241, 244, 245, 247, 253, 256, 271, 272, 277, 284, 287, 292, 295, 296, 299, 301, 302, 304, 305, 306, 308, 309, 312, 314, 315, 317, 320, 328, 331, 332, 335, 337, 338, 349, 351, 352, 358, 360, 361, 362, 365, 369, 371, 372, 376, 377, 379, 382, 386, 390, 391, 394, 398, 400, 401, 403, 407, 415, 423, 434, 436, 439, 452, 454, 458, 460, 461, 466, 473, 476, 482, 483, 484, 485, 489, 493, 494, 495, 496, 498, 499]
Initial belief: probe1 correct in 129/500; of the 371 problems with wrong probe1, **268 (72.2%) recovered to a correct final answer**.

## Stage 5 · Consensus reliability + Governor simulation

- CR(cumulative share=1) = 0.920
- CR(window share=1) = 0.890
- Consensus Calibration Error: cumulative = 0.092, window = 0.118

Governor early-stop simulation (stop when last 3 probes agree, certain, non-empty):
- would stop on 340/500 problems, stopped-answer accuracy **83.5%** (vs their final accuracy 89.7%)
- avg tokens saved on stopped problems: 1306
- stops on a WRONG answer (the cost of false consensus): 56 problems [4, 18, 21, 36, 46, 60, 64, 67, 78, 84, 95, 96, 100, 109, 114, 120, 130, 134, 144, 145, 168, 171, 188, 190, 197, 205, 213, 217, 219, 231, 257, 264, 266, 284, 308, 312, 337, 338, 358, 364, 369, 371, 379, 382, 403, 419, 454, 456, 460, 466, 467, 478, 484, 493, 495, 498]