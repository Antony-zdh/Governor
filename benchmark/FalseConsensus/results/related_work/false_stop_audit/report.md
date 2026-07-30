# Related-work false-stop audit

All available replay rows are pooled across split labels. No threshold is selected and no split-specific result is reported.

## Overall pooled outcomes

| Method | N | Stop | Accuracy delta | Token saving | Wrong / stop | Harm | Rescue | Harm / rescue |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deer_frozen | 2,736 | 72.84% | -4.31 pp | 28.80% | 208/1993 (10.44%) | 142 | 32 | 4.44 |
| tje_frozen | 2,736 | 63.85% | -6.14 pp | 27.05% | 370/1747 (21.18%) | 206 | 40 | 5.15 |

Harm means full generation is correct but the stopped delivery is wrong. Rescue means full generation is wrong but the stopped delivery is correct. `Wrong / stop` is a reference-answer false-stop rate and includes persistent wrong cases where full generation is also wrong.

## Model diagnostics

| Method | Model | N | Stop | Accuracy delta | Token saving | Wrong / stop | Harm | Rescue |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| deer_frozen | Qwen/Qwen3-8B | 1,368 | 70.18% | -0.44 pp | 27.47% | 3.12% | 18 | 17 |
| deer_frozen | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 1,368 | 75.51% | -8.19 pp | 30.54% | 17.23% | 124 | 15 |
| tje_frozen | Qwen/Qwen3-8B | 1,368 | 43.57% | -3.07 pp | 2.32% | 12.58% | 50 | 10 |
| tje_frozen | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 1,368 | 84.14% | -9.21 pp | 59.18% | 25.63% | 156 | 30 |

## Interpretation boundary

- These are false stops, not false consensus: DEER and TJE do not require repeated answer agreement.
- The audit uses the existing frozen-trajectory adaptations and therefore does not claim end-to-end paper fidelity.
- The primary table is problem-pooled; `summary.json` also stores equal-weight environment-macro rates.
