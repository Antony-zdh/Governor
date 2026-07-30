# Governor v2 multivariate A1-A3 diagnostic

Matched protocol: 1 model(s) × 3 benchmarks × 3 seeds = 9 environments; 1,710 development trajectories; dense simple@32 probes every 64 main tokens. Pooled estimates weight problems; macro estimates weight each environment equally.

## A1 scope and completeness

| Metric | Problem-pooled | Environment-macro |
|---|---:|---:|
| Trajectories | 1,710 | 9 environments |
| Probe rows | 99,266 | - |
| Empty probes | 285 (0.3%) | 0.1% |
| Natural completion | 1,677 (98.1%) | 98.8% |
| Mean main tokens | 3748 | 5880 |
| Final accuracy | 92.8% | 89.3% |
| Whole-trajectory unanimous coverage | 18.0% | 8.9% |
| Whole-trajectory unanimous accuracy | 98.4% | 99.2% |
| Final-answer grader | stored robust collector flag | same within every environment |

### Model × benchmark audit (three seeds pooled; primary w=5)

| Model | Benchmark | n | Full acc | First-consensus acc | Last-5 FC rate | Strict-stop Δacc | Net saving | Recovery / overthinking |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek-32B | AIME24 | 90 | 77.8% | 30.0% | 21.8% | -32.2 pp | 49.7% | 43 / 0 (∞:1) |
| DeepSeek-32B | AMC23 | 120 | 96.7% | 50.0% | 2.6% | -33.3 pp | 62.1% | 56 / 0 (∞:1) |
| DeepSeek-32B | MATH500 | 1500 | 93.4% | 55.6% | 6.0% | -23.1 pp | 66.2% | 562 / 11 (51.1:1) |

## A2 calibration and window sensitivity

Cumulative CCE pooled / macro: 0.254 / 0.328; cumulative unanimous coverage: 17.9% / 8.9%; cumulative unanimous false-consensus rate: 1.6% / 0.8%.

| w | CCE pooled / macro | Last-window unanimous coverage pooled / macro | Unanimous answer accuracy pooled / macro | False-consensus rate pooled / macro |
|---:|---:|---:|---:|---:|
| 3 | 0.118 / 0.126 | 83.3% / 92.9% | 92.8% / 89.5% | 7.2% / 10.5% |
| 5 | 0.127 / 0.130 | 80.5% / 90.5% | 93.3% / 89.9% | 6.7% / 10.1% |
| 8 | 0.133 / 0.135 | 78.4% / 89.1% | 93.8% / 90.3% | 6.2% / 9.7% |

Strict first consensus is the earliest run of exactly w consecutive probes whose answers are non-empty, successfully parsed by the collector, and normalized-equivalent. Net output saving charges every consumed probe completion.

| w | Reached pooled / macro | First-consensus acc pooled / macro | False consensus pooled / macro | Wrong consensus -> recovery pooled / macro | Delivered / full acc macro | Δacc macro | Net saving macro |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 98.2% / 99.3% | 50.4% / 41.7% | 49.6% / 58.3% | 86.8% / 84.0% | 42.0% / 89.3% | -47.31 pp | 75.7% |
| 5 | 92.3% / 96.7% | 66.4% / 58.8% | 33.6% / 41.2% | 79.8% / 77.2% | 59.7% / 89.3% | -29.56 pp | 59.3% |
| 8 | 85.4% / 94.1% | 76.3% / 66.9% | 23.7% / 33.1% | 71.1% / 71.6% | 67.9% / 89.3% | -21.36 pp | 43.9% |

Strict w=3 additionally yields 833 false commits and saves 3115 main tokens on average among stopped trajectories.

## A3 secondary soft-share consensus diagnostic

This secondary diagnostic is intentionally broader than strict first consensus: it uses a trailing window, at least three non-empty answers, and share >= 0.8. It must not be labelled as the strict consecutive-w result. Probe-1 is reported only as an early-readout control.

| w | Reached pooled / macro | First-consensus acc pooled / macro | Wrong consensus -> recovery pooled / macro | Recovery | Overthinking | Recovery:overthinking | Probe-1 wrong | Wrong Probe-1 -> correct final pooled / macro |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 98.2% / 99.3% | 50.4% / 41.7% | 86.8% / 84.0% | 723 | 9 | 80.33:1 | 1228 | 90.6% / 88.2% |
| 5 | 97.5% / 99.1% | 53.8% / 45.2% | 85.8% / 82.9% | 661 | 11 | 60.09:1 | 1228 | 90.6% / 88.2% |
| 8 | 93.0% / 97.0% | 63.3% / 58.3% | 82.0% / 77.7% | 479 | 9 | 53.22:1 | 1228 | 90.6% / 88.2% |

For w=5, the first consensus answer differs from the final answer on 759 trajectories; 661 of them finish correct.

### Consensus-time bins (w=5)

| Position definition | Bin | n | Final accuracy | Consensus accuracy | Recovery rate |
|---|---|---:|---:|---:|---:|
| absolute_tokens | <512 | 960 | 93.3% | 51.1% | 43.0% |
| absolute_tokens | 512-1K | 389 | 96.1% | 58.9% | 37.5% |
| absolute_tokens | 1-2K | 213 | 92.0% | 56.3% | 36.6% |
| absolute_tokens | 2-4K | 69 | 81.2% | 56.5% | 24.6% |
| absolute_tokens | 4-8K | 22 | 68.2% | 36.4% | 31.8% |
| absolute_tokens | >=8K | 15 | 73.3% | 73.3% | 0.0% |
| trajectory_fraction | 0-20% | 962 | 90.9% | 43.8% | 48.2% |
| trajectory_fraction | 20-40% | 307 | 94.8% | 54.1% | 40.7% |
| trajectory_fraction | 40-60% | 243 | 96.7% | 77.4% | 19.3% |
| trajectory_fraction | 60-80% | 113 | 97.3% | 79.6% | 17.7% |
| trajectory_fraction | 80-100% | 43 | 88.4% | 76.7% | 11.6% |

## Interpretation

- The broad false-consensus/recovery finding is retained only if it appears across both pooled and equal-environment macro summaries.
- Window size is a material controller dimension: stronger persistence reduces false stops but also sharply reduces token saving.
- Probe-1 error is not consensus error. Recovery claims should point to the first-consensus transition table, not to the Probe-1 control.
- Consensus-time associations remain descriptive because problem difficulty and trajectory length are confounders.
