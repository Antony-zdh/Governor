# Matched stopping-signal CPU contrast

This is a signal-only counterfactual, not a faithful end-to-end TJE run. All policies directly submit the same DEER trial answer and are charged the same main-prefix plus DEER trial-output tokens.

## Exact matching

- Trajectories: 3,420
- DEER trials: 45,217
- Exact DEER-Wait/TJE-Wait matches: 30,606 (67.69%)
- Trajectories with at least one match: 3,315 (96.93%)
- Join is exact on trajectory identity plus trigger_char_position; unmatched events are excluded and never interpolated.

## Representative Test operating points

| Aggregation | Signal | Parameter | Accuracy drop | Saving | Stop accuracy | False-stop | Harm/rescue | Coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| pooled | deer_confidence | 0.95 | 6.73 pp | 44.96% | 74.46% | 25.54% | 3.71 | 75.00% |
| environment_macro | deer_confidence | 0.95 | 2.56 pp | 30.54% | 89.34% | 10.66% | 3.71 | 55.50% |
| pooled | deer_confidence | 0.99 | 4.39 pp | 37.29% | 77.29% | 22.71% | 2.76 | 70.18% |
| environment_macro | deer_confidence | 0.99 | 1.67 pp | 25.79% | 90.63% | 9.37% | 2.76 | 52.16% |
| pooled | deer_confidence | 0.995 | 3.95 pp | 35.04% | 77.85% | 22.15% | 2.59 | 67.98% |
| environment_macro | deer_confidence | 0.995 | 1.50 pp | 24.11% | 90.90% | 9.10% | 2.59 | 49.81% |
| pooled | deer_confidence | 0.999 | 3.65 pp | 29.43% | 78.60% | 21.40% | 2.67 | 62.87% |
| environment_macro | deer_confidence | 0.999 | 1.39 pp | 19.69% | 90.79% | 9.21% | 2.67 | 43.75% |
| pooled | answer_persistence | 3 | 6.29 pp | 38.06% | 68.64% | 31.36% | 4.07 | 49.42% |
| environment_macro | answer_persistence | 3 | 8.48 pp | 35.06% | 57.40% | 42.60% | 11.90 | 47.40% |
| pooled | answer_persistence | 5 | 1.75 pp | 22.08% | 74.37% | 25.63% | 2.00 | 29.09% |
| environment_macro | answer_persistence | 5 | 1.54 pp | 21.48% | 59.58% | 40.42% | 3.31 | 30.16% |
| pooled | answer_persistence | 8 | 0.73 pp | 12.99% | 82.68% | 17.32% | 1.71 | 18.57% |
| environment_macro | answer_persistence | 8 | 0.28 pp | 11.21% | 77.71% | 22.29% | 1.71 | 20.35% |
| pooled | answer_persistence | 12 | 0.58 pp | 5.99% | 86.84% | 13.16% | 2.00 | 11.11% |
| environment_macro | answer_persistence | 12 | 0.22 pp | 4.20% | 85.74% | 14.26% | 2.00 | 10.67% |
| pooled | answer_persistence | 20 | -0.15 pp | -0.13% | 100.00% | 0.00% | 0.00 | 3.07% |
| environment_macro | answer_persistence | 20 | -0.06 pp | -0.80% | 100.00% | 0.00% | 0.00 | 2.44% |
| pooled | answer_persistence | 30 | 0.00 pp | -1.97% | 100.00% | 0.00% | inf | 0.15% |
| environment_macro | answer_persistence | 30 | 0.00 pp | -1.91% | 100.00% | 0.00% | inf | 0.06% |
| pooled | tje_confidence | 1 | 1.90 pp | 1.93% | 10.53% | 89.47% | inf | 2.78% |
| environment_macro | tje_confidence | 1 | 5.07 pp | 3.92% | 17.14% | 82.86% | inf | 6.28% |
| pooled | tje_confidence | 2 | 3.95 pp | 13.90% | 41.25% | 58.75% | 7.75 | 11.70% |
| environment_macro | tje_confidence | 2 | 8.23 pp | 16.07% | 43.74% | 56.26% | 38.04 | 17.44% |
| pooled | tje_confidence | 3 | 3.95 pp | 13.90% | 41.25% | 58.75% | 7.75 | 11.70% |
| environment_macro | tje_confidence | 3 | 8.23 pp | 16.07% | 43.74% | 56.26% | 38.04 | 17.44% |

## Interpretation limits

- TJE labels are real model outputs but only exact Wait-position matches are retained; this reduces opportunity coverage.
- TJE confidence-query output tokens are intentionally not charged because the experiment holds action/cost fixed to isolate the stopping signal.
- The comparison therefore supports a signal-level claim only; it does not replace the separately reported faithful/frozen baseline costs.

## Reproduce

```bash
MPLCONFIGDIR=/tmp/governor-mpl python -m benchmark.FalseConsensus.report.analyze_matched_signal_frontier
```
