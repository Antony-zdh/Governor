# Matched Governor / related-work comparison

Primary reporting uses only the frozen **development split**. All methods share the same main trajectories, model/benchmark/seed cells, answer grader, and fair all-generated-token accounting. No test example was read.

## Benchmark-macro development results

| Model | Method | Accuracy | Δ accuracy vs vanilla (pp) | Fair token saving | Main-only saving | Stop rate |
|---|---|---:|---:|---:|---:|---:|
| DeepSeek-R1-Distill-Qwen-7B | Vanilla (full generation) | 79.76% | +0.00 | 0.00% | 0.00% | 0.00% |
| DeepSeek-R1-Distill-Qwen-7B | CertaIndex | 23.87% | -55.89 | 76.68% | 78.60% | 98.67% |
| DeepSeek-R1-Distill-Qwen-7B | TJE | 60.67% | -19.09 | 65.00% | 78.45% | 93.44% |
| DeepSeek-R1-Distill-Qwen-7B | DEER | 74.93% | -4.83 | 20.16% | 25.68% | 56.07% |
| DeepSeek-R1-Distill-Qwen-7B | Governor — Naive agreement | 43.54% | -36.22 | 68.98% | 70.33% | 97.67% |
| DeepSeek-R1-Distill-Qwen-7B | Governor — Conservative | 69.81% | -9.94 | 26.22% | 29.44% | 73.43% |
| DeepSeek-R1-Distill-Qwen-7B | Governor — Balanced task-aware† | 64.63% | -15.13 | 40.42% | 43.04% | 88.61% |
| Qwen3-8B | Vanilla (full generation) | 85.44% | +0.00 | 0.00% | 0.00% | 0.00% |
| Qwen3-8B | CertaIndex | 15.33% | -70.11 | 90.10% | 91.00% | 99.78% |
| Qwen3-8B | TJE | 85.00% | -0.44 | 2.03% | 5.82% | 22.50% |
| Qwen3-8B | DEER | 86.22% | +0.78 | 16.29% | 21.37% | 41.35% |
| Qwen3-8B | Governor — Naive agreement | 28.96% | -56.48 | 84.36% | 85.12% | 99.78% |
| Qwen3-8B | Governor — Conservative | 55.76% | -29.69 | 47.83% | 50.29% | 92.54% |
| Qwen3-8B | Governor — Balanced task-aware† | 51.06% | -34.39 | 54.31% | 56.46% | 96.17% |

## Per-benchmark development results

| Model | Benchmark | Method | Accuracy | Δ accuracy (pp) | Fair token saving | Main-only saving | Stop rate |
|---|---|---|---:|---:|---:|---:|---:|
| DeepSeek-R1-Distill-Qwen-7B | MATH500 | Vanilla (full generation) | 90.67% | +0.00 | 0.00% | 0.00% | 0.00% |
| DeepSeek-R1-Distill-Qwen-7B | MATH500 | CertaIndex | 48.00% | -42.67 | 82.16% | 84.01% | 96.00% |
| DeepSeek-R1-Distill-Qwen-7B | MATH500 | TJE | 82.00% | -8.67 | 56.47% | 66.82% | 80.33% |
| DeepSeek-R1-Distill-Qwen-7B | MATH500 | DEER | 80.33% | -10.33 | 39.92% | 49.43% | 79.33% |
| DeepSeek-R1-Distill-Qwen-7B | MATH500 | Governor — Naive agreement | 57.00% | -33.67 | 72.13% | 73.60% | 93.00% |
| DeepSeek-R1-Distill-Qwen-7B | MATH500 | Governor — Conservative | 73.33% | -17.33 | 34.75% | 38.27% | 63.33% |
| DeepSeek-R1-Distill-Qwen-7B | MATH500 | Governor — Balanced task-aware† | 71.67% | -19.00 | 40.79% | 43.96% | 70.00% |
| DeepSeek-R1-Distill-Qwen-7B | AMC23 | Vanilla (full generation) | 87.50% | +0.00 | 0.00% | 0.00% | 0.00% |
| DeepSeek-R1-Distill-Qwen-7B | AMC23 | CertaIndex | 12.50% | -75.00 | 83.87% | 85.01% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | AMC23 | TJE | 66.67% | -20.83 | 65.05% | 79.11% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | AMC23 | DEER | 83.33% | -4.17 | 16.39% | 21.41% | 50.00% |
| DeepSeek-R1-Distill-Qwen-7B | AMC23 | Governor — Naive agreement | 29.17% | -58.33 | 71.06% | 72.14% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | AMC23 | Governor — Conservative | 75.00% | -12.50 | 24.15% | 27.00% | 79.17% |
| DeepSeek-R1-Distill-Qwen-7B | AMC23 | Governor — Balanced task-aware† | 66.67% | -20.83 | 44.38% | 46.47% | 95.83% |
| DeepSeek-R1-Distill-Qwen-7B | AIME24 | Vanilla (full generation) | 61.11% | +0.00 | 0.00% | 0.00% | 0.00% |
| DeepSeek-R1-Distill-Qwen-7B | AIME24 | CertaIndex | 11.11% | -50.00 | 64.01% | 66.80% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | AIME24 | TJE | 33.33% | -27.78 | 73.48% | 89.42% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | AIME24 | DEER | 61.11% | +0.00 | 4.18% | 6.19% | 38.89% |
| DeepSeek-R1-Distill-Qwen-7B | AIME24 | Governor — Naive agreement | 44.44% | -16.67 | 63.76% | 65.27% | 100.00% |
| DeepSeek-R1-Distill-Qwen-7B | AIME24 | Governor — Conservative | 61.11% | +0.00 | 19.75% | 23.07% | 77.78% |
| DeepSeek-R1-Distill-Qwen-7B | AIME24 | Governor — Balanced task-aware† | 55.56% | -5.56 | 36.08% | 38.70% | 100.00% |
| Qwen3-8B | MATH500 | Vanilla (full generation) | 89.67% | +0.00 | 0.00% | 0.00% | 0.00% |
| Qwen3-8B | MATH500 | CertaIndex | 46.00% | -43.67 | 89.88% | 91.06% | 99.33% |
| Qwen3-8B | MATH500 | TJE | 88.33% | -1.33 | 3.57% | 10.02% | 46.67% |
| Qwen3-8B | MATH500 | DEER | 92.00% | +2.33 | 33.42% | 41.87% | 72.67% |
| Qwen3-8B | MATH500 | Governor — Naive agreement | 48.00% | -41.67 | 82.48% | 83.49% | 99.33% |
| Qwen3-8B | MATH500 | Governor — Conservative | 68.67% | -21.00 | 48.64% | 51.64% | 87.33% |
| Qwen3-8B | MATH500 | Governor — Balanced task-aware† | 65.67% | -24.00 | 56.79% | 59.27% | 92.67% |
| Qwen3-8B | AMC23 | Vanilla (full generation) | 83.33% | +0.00 | 0.00% | 0.00% | 0.00% |
| Qwen3-8B | AMC23 | CertaIndex | 0.00% | -83.33 | 89.94% | 90.65% | 100.00% |
| Qwen3-8B | AMC23 | TJE | 83.33% | +0.00 | 4.36% | 7.45% | 20.83% |
| Qwen3-8B | AMC23 | DEER | 83.33% | +0.00 | 10.37% | 14.38% | 29.17% |
| Qwen3-8B | AMC23 | Governor — Naive agreement | 16.67% | -66.67 | 87.17% | 87.67% | 100.00% |
| Qwen3-8B | AMC23 | Governor — Conservative | 37.50% | -45.83 | 53.96% | 55.72% | 95.83% |
| Qwen3-8B | AMC23 | Governor — Balanced task-aware† | 37.50% | -45.83 | 59.48% | 61.07% | 95.83% |
| Qwen3-8B | AIME24 | Vanilla (full generation) | 83.33% | +0.00 | 0.00% | 0.00% | 0.00% |
| Qwen3-8B | AIME24 | CertaIndex | 0.00% | -83.33 | 90.49% | 91.30% | 100.00% |
| Qwen3-8B | AIME24 | TJE | 83.33% | +0.00 | -1.83% | 0.00% | 0.00% |
| Qwen3-8B | AIME24 | DEER | 83.33% | +0.00 | 5.10% | 7.85% | 22.22% |
| Qwen3-8B | AIME24 | Governor — Naive agreement | 22.22% | -61.11 | 83.44% | 84.21% | 100.00% |
| Qwen3-8B | AIME24 | Governor — Conservative | 61.11% | -22.22 | 40.88% | 43.50% | 94.44% |
| Qwen3-8B | AIME24 | Governor — Balanced task-aware† | 50.00% | -33.33 | 46.68% | 49.04% | 100.00% |

† `Governor — Balanced task-aware` uses the frozen Balanced-MATH level floor on MATH500. On AMC23/AIME24 it uses the old protocol's explicitly predeclared fixed-1536 non-MATH candidate, which is a **secondary analysis**, not the frozen non-MATH primary. Conservative remains the frozen non-MATH primary.

Fair saving counts all newly generated main and probe output tokens; re-sent probe prompt tokens are reported separately in the CSV/JSON artifacts.
