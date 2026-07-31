# Expanded Governor freeze and Test evaluation

Selection was frozen from Train/Dev before this command read Test. The 15,552 long-window rules are explicitly post-hoc sensitivity candidates.

| Profile | Rule | Source | Aggregation | Accuracy drop | Saving | Stop accuracy | False-stop | Harm/rescue |
|---|---|---|---|---:|---:|---:|---:|---:|
| safe | `latest_persistence_fixed_maturity__255bbc0b19c5` | post_hoc_long_persistence | pooled | -0.15 pp | 6.20% | 82.61% | 17.39% | 0.80 |
| safe | `latest_persistence_fixed_maturity__255bbc0b19c5` | post_hoc_long_persistence | environment_macro | 0.18 pp | 6.19% | 84.61% | 15.39% | 1.19 |
| balanced_knee | `latest_persistence_fixed_maturity__e734f384418c` | post_hoc_long_persistence | pooled | 0.73 pp | 18.96% | 79.84% | 20.16% | 1.83 |
| balanced_knee | `latest_persistence_fixed_maturity__e734f384418c` | post_hoc_long_persistence | environment_macro | 0.51 pp | 17.12% | 80.31% | 19.69% | 1.52 |
| token_efficient | `latest_persistence_fixed_maturity__45b50fd6f010` | preregistered | pooled | 2.49 pp | 24.15% | 76.43% | 23.57% | 4.40 |
| token_efficient | `latest_persistence_fixed_maturity__45b50fd6f010` | preregistered | environment_macro | 1.18 pp | 21.32% | 78.18% | 21.82% | 2.28 |

No selected point passed the original conservative preregistered gates; these three points are transparent representative operating points, not a claim that the original selection protocol succeeded.

## Reproduce

```bash
python -m benchmark.FalseConsensus.governor_v2.analysis.freeze_extended_candidates freeze
python -m benchmark.FalseConsensus.governor_v2.analysis.freeze_extended_candidates evaluate
```
