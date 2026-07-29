# Governor v2 multivariate A1-A3 diagnostic

Matched protocol: 2 models × 3 benchmarks × 3 seeds = 18 environments; 2,736 development trajectories; dense simple@32 probes every 64 main tokens. Pooled estimates weight problems; macro estimates weight each environment equally.

## A1 scope and completeness

| Metric | Problem-pooled | Environment-macro |
|---|---:|---:|
| Trajectories | 2,736 | 18 environments |
| Probe rows | 229,693 | - |
| Empty probes | 1,406 (0.6%) | 0.4% |
| Natural completion | 2,590 (94.7%) | 91.3% |
| Mean main tokens | 5404 | 9059 |
| Final accuracy | 88.6% | 78.9% |
| Whole-trajectory unanimous coverage | 11.5% | 4.7% |
| Whole-trajectory unanimous accuracy | 97.5% | 98.1% |
| Final-answer grader | stored robust collector flag | same within every environment |

### Model × benchmark audit (three seeds pooled; primary w=5)

| Model | Benchmark | n | Full acc | Last-5 FC rate | Strict-stop Δacc | Net saving | Recovery / overthinking |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | AIME24 | 72 | 73.6% | 23.1% | -44.4 pp | 66.2% | 42 / 0 (∞:1) |
| Qwen3-8B | AMC23 | 96 | 86.5% | 4.0% | -45.8 pp | 76.9% | 56 / 2 (28.0:1) |
| Qwen3-8B | MATH500 | 1200 | 91.2% | 6.4% | -28.4 pp | 79.1% | 539 / 19 (28.4:1) |
| DeepSeek-7B | AIME24 | 72 | 47.2% | 48.5% | -9.7 pp | 54.7% | 15 / 0 (∞:1) |
| DeepSeek-7B | AMC23 | 96 | 85.4% | 4.5% | -32.3 pp | 56.3% | 45 / 0 (∞:1) |
| DeepSeek-7B | MATH500 | 1200 | 89.8% | 10.1% | -19.2 pp | 63.7% | 440 / 18 (24.4:1) |

## A2 calibration and window sensitivity

Cumulative CCE pooled / macro: 0.204 / 0.241; cumulative unanimous coverage: 11.3% / 4.6%; cumulative unanimous false-consensus rate: 1.9% / 1.5%.

| w | CCE pooled / macro | Last-window unanimous coverage pooled / macro | Unanimous answer accuracy pooled / macro | False-consensus rate pooled / macro |
|---:|---:|---:|---:|---:|
| 3 | 0.124 / 0.201 | 83.7% / 88.0% | 89.1% / 83.6% | 10.9% / 16.4% |
| 5 | 0.124 / 0.203 | 78.7% / 84.4% | 90.3% / 84.0% | 9.7% / 16.0% |
| 8 | 0.117 / 0.200 | 73.9% / 80.6% | 91.9% / 84.7% | 8.1% / 15.3% |

Strict stop below requires all w answers to be non-empty and normalized-equivalent; net output saving charges every consumed probe completion.

| w | Stop coverage macro | Delivered acc / full acc macro | Δacc macro | Net saving macro | False stops among stops macro | Recovery killed / overthinking avoided |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 99.6% | 32.3% / 78.9% | -46.60 pp | 82.3% | 67.8% | 1204 / 36 |
| 5 | 97.9% | 48.9% / 78.9% | -29.99 pp | 66.1% | 51.2% | 730 / 42 |
| 8 | 94.8% | 61.6% / 78.9% | -17.29 pp | 51.4% | 38.0% | 415 / 44 |

Strict w=3 additionally yields 1478 false commits and saves 4706 main tokens on average among stopped trajectories.

## A3 early readout versus first consensus

First consensus uses a trailing window, at least three non-empty answers, and share >= 0.8. Probe-1 is reported only as an early-readout control.

| w | Reached pooled / macro | Recovery | Overthinking | Recovery:overthinking | Probe-1 wrong | Wrong Probe-1 -> correct final pooled / macro |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 98.9% / 99.6% | 1204 | 36 | 33.44:1 | 2098 | 86.0% / 78.0% |
| 5 | 98.8% / 99.5% | 1137 | 39 | 29.15:1 | 2098 | 86.0% / 78.0% |
| 8 | 95.8% / 98.1% | 867 | 44 | 19.70:1 | 2098 | 86.0% / 78.0% |

For w=5, the first consensus answer differs from the final answer on 1411 trajectories; 1139 of them finish correct.

### Consensus-time bins (w=5)

| Position definition | Bin | n | Final accuracy | Consensus accuracy | Recovery rate |
|---|---|---:|---:|---:|---:|
| absolute_tokens | <512 | 1432 | 90.5% | 42.7% | 49.1% |
| absolute_tokens | 512-1K | 653 | 90.2% | 56.5% | 36.1% |
| absolute_tokens | 1-2K | 418 | 88.8% | 56.7% | 32.8% |
| absolute_tokens | 2-4K | 135 | 77.8% | 44.4% | 34.1% |
| absolute_tokens | 4-8K | 41 | 53.7% | 26.8% | 26.8% |
| absolute_tokens | >=8K | 23 | 39.1% | 21.7% | 17.4% |
| trajectory_fraction | 0-20% | 1709 | 85.6% | 36.5% | 50.8% |
| trajectory_fraction | 20-40% | 574 | 93.7% | 61.7% | 33.4% |
| trajectory_fraction | 40-60% | 267 | 95.1% | 79.4% | 16.1% |
| trajectory_fraction | 60-80% | 120 | 91.7% | 74.2% | 18.3% |
| trajectory_fraction | 80-100% | 32 | 84.4% | 46.9% | 37.5% |

## Interpretation

- The broad false-consensus/recovery finding is retained only if it appears across both pooled and equal-environment macro summaries.
- Window size is a material controller dimension: stronger persistence reduces false stops but also sharply reduces token saving.
- Probe-1 error is not consensus error. Recovery claims should point to the first-consensus transition table, not to the Probe-1 control.
- Consensus-time associations remain descriptive because problem difficulty and trajectory length are confounders.
