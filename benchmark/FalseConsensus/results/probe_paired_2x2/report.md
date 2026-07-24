# Paired re-probe 2×2 follow-up

This is an offline analysis of the paired `simple@10` and `certaindex@10` streams. No model calls were made.

## Headline 2×2

| Timing | Readout | N | Accuracy | Commit rate | Continuation match | Mean stop tokens |
|---|---|---:|---:|---:|---:|---:|
| simple | simple | 416 | 69.2% | 100.0% | 73.3% | 956 |
| simple | certaindex | 416 | 70.2% | 43.3% | 73.8% | 956 |
| certaindex | simple | 311 | 89.1% | 98.4% | 94.2% | 1477 |
| certaindex | certaindex | 311 | 89.7% | 100.0% | 94.5% | 1477 |

- descriptive readout main effect: **+0.80 pp**
- descriptive timing main effect: **+19.68 pp**
- timing share of absolute main effects: **96.1%**

The headline timing rows have different problem sets (416 vs 311), so their contrast includes both later timing and trigger-set selection. It is not by itself a fully paired timing estimate.

## Common-trigger paired sensitivity

Both timing rules trigger on **306** problems. Restricting all four cells to those same problems gives:

| Timing | Readout | N | Accuracy | Commit rate | Continuation match | Mean stop tokens |
|---|---|---:|---:|---:|---:|---:|
| simple | simple | 306 | 81.0% | 100.0% | 84.3% | 886 |
| simple | certaindex | 306 | 81.7% | 48.7% | 84.3% | 886 |
| certaindex | simple | 306 | 90.2% | 98.7% | 95.4% | 1480 |
| certaindex | certaindex | 306 | 90.8% | 100.0% | 95.8% | 1480 |

- paired readout main effect: **+0.65 pp**
- paired timing main effect: **+9.15 pp**
- timing share of absolute paired main effects: **93.3%**

The paired result preserves the main qualitative conclusion: readout wording contributes little, while waiting for the certaindex timing point is associated with substantially higher correctness.

## Trigger-set overlap

- simple triggers: **416**
- certaindex triggers: **311**
- both trigger: **306**
- simple-only: **110**
- certaindex-only: **5**
- net trigger-count difference: **105**

Therefore, the often quoted `416 - 311 = 105` is a net count difference, not the size of the simple-only set. The refusal analysis contains **110** problems.

## Simple-only continuation analysis

- simple stop differs from the trajectory's final answer: **63/110 (57.3%)**
- simple stopped answer is reference-correct: **40/110 (36.4%)**
- full trajectory ends reference-correct: **70/110 (63.6%)**

| Category | N | Share | Interpretation |
|---|---:|---:|---|
| recovery | 35 | 31.8% | refusal protects a wrong→correct recovery |
| overthinking | 5 | 4.5% | refusal loses a correct early stop before correct→wrong |
| terminal_correct | 35 | 31.8% | refusal delays an already correct terminal answer |
| terminal_wrong | 12 | 10.9% | refusal delays but does not repair the wrong answer |
| changed_wrong_to_wrong | 23 | 20.9% | answer changes, but both stop and final are wrong |

Using final-answer mismatch as the operational definition, a majority of simple-only stops are non-terminal. But rejection is not uniformly beneficial: its direct accuracy benefit is the recovery group, while the overthinking group is harmed and the remaining groups only incur delay. This supports history/timing signals, but still requires the Pareto sweep to test whether a flat `min_tokens` floor reproduces the same gains more efficiently.

Per-problem details are in `simple_only_cases.csv`; machine-readable summary statistics are in `analysis_2x2.json`.
