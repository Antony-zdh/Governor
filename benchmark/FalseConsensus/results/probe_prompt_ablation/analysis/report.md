# Simple@32 vs CertaIndex@32 prompt-timing ablation

Paired trajectories (pooled): **3420** across 36 environments (2 models x 3 benchmarks x 6 seeds). Both arms share the frozen main trajectory, probe every 64 tokens from token 64, max_tokens=32, and the identical patience-3 consensus stop rule; only the probe suffix differs. No train/dev/test table.

Primary token accounting = main tokens through stop + consumed probe output tokens (generated output tokens only). Probe prompt/prefill tokens and wall time are reported separately and are NOT called GPU compute/latency.

## Pooled summary (all 3,420 rows)
| metric | Simple@32 | CertaIndex@32 |
|---|---|---|
| accuracy | 0.4605 | 0.4345 |
| baseline (full gen) accuracy | 0.8971 | 0.8971 |
| accuracy delta vs baseline | -0.4365 | -0.4626 |
| stop rate | 0.9915 | 0.9927 |
| mean first-consensus position | 703.5282 | 587.5558 |
| median first-consensus position | 384 | 320 |
| wrong among stops | 0.5435 | 0.5688 |
| main-only token saving | 0.8125 | 0.8324 |
| all-generated token saving | 0.7922 | 0.8147 |
| consumed probe-output tax (tok) | 78.8813 | 65.2635 |
| Harm | 0.4488 | 0.4751 |
| Rescue | 0.0123 | 0.0126 |
| Harm/Rescue | 36.5476 | 37.7907 |

## Paired consensus timing & direction (pooled)
- both stop: 0.9883; Simple-only stop: 0.0032; CertaIndex-only stop: 0.0044; neither stop: 0.0041
- when both stop — CertaIndex later: 0.2243, earlier: 0.3398, same: 0.4243
- mean CertaIndex consensus delay (tokens, when both stop): -114.9728; median: 0

## Paired correctness shifts (pooled)
- CertaIndex-corrects-Simple: 228 (0.0667)
- CertaIndex-breaks-Simple: 317 (0.0927)
- Simple harms protected by CertaIndex: 220 (0.0643)
- new harms introduced by CertaIndex: 310 (0.0906)
- Simple harm/rescue counts: harm=1535 rescue=42; CertaIndex harm/rescue counts: harm=1625 rescue=43

## Equal-environment macro (mean over 36 environments)
| metric | Simple@32 | CertaIndex@32 |
|---|---|---|
| accuracy | 0.3464 | 0.3058 |
| stop_rate | 0.9976 | 0.9981 |
| mean_first_consensus_position | 1250.6626 | 892.5069 |
| main_only_saving | 0.8110 | 0.8451 |
| all_generated_saving | 0.7929 | 0.8303 |
| consumed_probe_output_tax_tokens | 118.4211 | 84.3538 |
| harm | 0.4858 | 0.5277 |
| rescue | 0.0056 | 0.0068 |

macro consensus delay (mean/median): -357.8985 / -49.7778

## Conclusion
CertaIndex reaches first consensus earlier than Simple when both stop (mean delay -114.9728 tokens); see the direction counts above. Accuracy: Simple 0.4605 vs CertaIndex 0.4345; net all-generated saving Simple 0.7922 vs CertaIndex 0.8147.

## Artifacts
- per_problem.csv (3,420 paired rows), summary.json, acceptance.json, report.md under benchmark/FalseConsensus/results/probe_prompt_ablation/analysis/
