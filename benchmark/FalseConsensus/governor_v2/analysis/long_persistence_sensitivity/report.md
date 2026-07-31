# Long strict-consensus persistence sensitivity

Post-hoc sensitivity only; the preregistered 17,712-rule sweep is unchanged. Added strict latest-answer persistence windows `10/12/16/20/25/30` and replayed them on the same development train+dev environments.

## Integrity

- Incremental rules: **15,552**
- Incremental metric rows: **559,872**
- Combined rules: **33,264**
- Original / expanded frontier size: **93 / 103**
- New long-window rules on expanded frontier: **18**

## Window summary

| w | rules | new frontier | min worst-model drop | q20 saving there | min drop with q20 saving > 0 | q20 saving |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 2,592 | 3 | 8.31 pp | 7.26% | 8.31 pp | 7.26% |
| 12 | 2,592 | 4 | 6.93 pp | 5.78% | 6.93 pp | 5.78% |
| 16 | 2,592 | 4 | 4.15 pp | 3.05% | 4.15 pp | 3.05% |
| 20 | 2,592 | 3 | 3.81 pp | 1.09% | 3.81 pp | 1.09% |
| 25 | 2,592 | 1 | 3.81 pp | -1.33% | 5.31 pp | 2.74% |
| 30 | 2,592 | 3 | 1.96 pp | -2.11% | 3.93 pp | 0.86% |

## Frozen gate check

| scope | conservative | balanced | token-efficient |
|---|---:|---:|---:|
| incremental long-window rules | 0 | 0 | 0 |
| combined sweep | 0 | 0 | 0 |

Primary Pareto axes follow the frozen selector: minimize worst train/dev per-model and per-benchmark accuracy drop while maximizing dev q20 token saving.
