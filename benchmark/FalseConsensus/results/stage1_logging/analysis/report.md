# False Consensus — Stage 2-5 report

- problems logged: **500**
- overall accuracy: **81.2%**, finished naturally within budget: 61.8%

## Stage 2 · Agreement vs Accuracy

Cumulative share (plan.md definition, all probes of the trajectory):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    | 113 |        0.349 |      0.558 |
| 0.5-0.6 |  61 |        0.538 |      0.770 |
| 0.6-0.7 |  55 |        0.643 |      0.891 |
| 0.7-0.8 |  87 |        0.747 |      0.862 |
| 0.8-0.9 |  60 |        0.845 |      0.950 |
| 0.9-<1  |  29 |        0.923 |      0.793 |
| =1.0    |  95 |        1.000 |      0.968 |

Window share (last 5 probes — what a Governor actually sees):

| bin     |   n |   mean_share |   accuracy |
|:--------|----:|-------------:|-----------:|
| <0.5    |  40 |        0.376 |      0.275 |
| 0.5-0.6 |   2 |        0.500 |      0.000 |
| 0.6-0.7 |  45 |        0.604 |      0.667 |
| 0.7-0.8 |   8 |        0.750 |      0.750 |
| 0.8-0.9 |  36 |        0.800 |      0.472 |
| =1.0    | 338 |        1.000 |      0.947 |

- cumulative share=1: 87 problems, accuracy 98.9% → false consensus 1
- window share=1: 338 problems, window-answer accuracy 93.5% → **false consensus 22 (6.5% of unanimous)**

## Stage 3 · False consensus cases

Exported 134 cases: [4, 9, 11, 14, 18, 19, 22, 23, 25, 33, 34, 36, 39, 43, 46, 58, 59, 64, 68, 73, 74, 75, 76, 89, 90, 92, 95, 96, 100, 101, 103, 110, 119, 124, 127, 129, 130, 140, 145, 146, 149, 150, 152, 153, 155, 156, 157, 162, 163, 164, 165, 171, 173, 177, 188, 190, 194, 202, 204, 209, 210, 212, 213, 214, 220, 224, 230, 232, 235, 236, 237, 238, 240, 247, 249, 253, 256, 257, 258, 266, 274, 284, 286, 287, 292, 294, 301, 303, 305, 308, 316, 317, 320, 323, 328, 331, 332, 334, 340, 344, 355, 357, 361, 366, 368, 369, 372, 376, 378, 381, 382, 388, 393, 394, 400, 401, 409, 416, 432, 439, 445, 446, 456, 467, 470, 478, 481, 483, 486, 491, 494, 496, 497, 498]

## Stage 4 · Trajectory

- consensus at <512 tokens: n=143, accuracy=87.4%
- consensus at 512-1024 tokens: n=112, accuracy=84.8%
- consensus at 1024-1536 tokens: n=106, accuracy=89.6%
- consensus at 1536-2048 tokens: n=43, accuracy=79.1%
- consensus at >2048 tokens: n=31, accuracy=58.1%
- never reached window share ≥ 0.8: 65

Recovery: 145 problems held a 3-probe consensus that differed from their final answer (95 of them ended correct): [2, 4, 9, 11, 14, 15, 17, 18, 19, 21, 22, 23, 25, 34, 36, 41, 43, 46, 58, 59, 62, 64, 68, 73, 74, 75, 76, 80, 82, 89, 90, 92, 94, 95, 96, 100, 101, 106, 119, 124, 127, 129, 130, 138, 140, 145, 146, 149, 150, 152, 155, 156, 157, 162, 163, 164, 165, 166, 173, 177, 181, 190, 194, 202, 209, 210, 212, 213, 214, 219, 220, 222, 224, 228, 230, 232, 235, 236, 237, 238, 240, 242, 247, 249, 253, 256, 258, 266, 274, 277, 285, 286, 287, 292, 294, 295, 303, 305, 306, 315, 316, 320, 323, 324, 328, 330, 331, 332, 334, 335, 337, 340, 341, 344, 351, 352, 355, 357, 360, 361, 362, 366, 368, 372, 376, 378, 382, 388, 393, 394, 400, 409, 414, 416, 417, 432, 446, 460, 478, 483, 486, 490, 491, 494, 496]
Initial belief: probe1 correct in 125/500; of the 375 problems with wrong probe1, **286 (76.3%) recovered to a correct final answer**.

## Stage 5 · Consensus reliability + Governor simulation

- CR(cumulative share=1) = 0.989
- CR(window share=1) = 0.935
- Consensus Calibration Error: cumulative = 0.149, window = 0.080

Governor early-stop simulation (stop when last 3 probes agree, certain, non-empty):
- would stop on 416/500 problems, stopped-answer accuracy **69.2%** (vs their final accuracy 85.6%)
- avg tokens saved on stopped problems: 1321
- stops on a WRONG answer (the cost of false consensus): 128 problems [4, 9, 11, 14, 18, 19, 22, 23, 25, 33, 34, 36, 39, 43, 58, 59, 64, 68, 73, 74, 75, 76, 89, 90, 92, 95, 96, 100, 101, 103, 110, 124, 127, 129, 130, 140, 145, 146, 149, 150, 152, 153, 155, 156, 162, 163, 164, 165, 171, 173, 177, 188, 190, 194, 202, 204, 209, 210, 212, 213, 214, 220, 230, 232, 235, 236, 237, 238, 240, 247, 249, 253, 256, 257, 258, 274, 284, 286, 287, 292, 294, 301, 303, 305, 308, 316, 317, 320, 323, 328, 331, 332, 334, 340, 344, 355, 357, 361, 366, 368, 369, 372, 376, 378, 381, 382, 388, 393, 394, 400, 401, 409, 416, 432, 445, 446, 456, 467, 470, 478, 481, 483, 486, 491, 494, 496, 497, 498]