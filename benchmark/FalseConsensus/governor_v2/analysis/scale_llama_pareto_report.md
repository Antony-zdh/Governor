# Llama-8B scale sweep acceptance report

## Scope and integrity

- Model: `deepseek-ai/DeepSeek-R1-Distill-Llama-8B`.
- Data: MATH500, AMC23, and AIME24; seeds 42/43/44; train/dev/test.
- Candidate rules: 17,712.
- Metric rows: 478,224 = 17,712 rules × 27 environments.
- Every rule has the same 9 train, 9 dev, and 9 test environments. There are
  no duplicate metric identities or unknown/missing rules.
- Selection and the Pareto frontier use train+dev only. Test is used only for
  the cross-split diagnostic below.

## Pareto result

The preregistered three-objective frontier contains 75 rules. The objectives
maximize dev Q20 total-decode-token saving while minimizing worst train/dev
model-level and benchmark-level accuracy drop.

Under the existing operating-point gates:

| Profile | Eligible frontier rules | Best rule |
|---|---:|---|
| conservative | 0 | — |
| balanced | 0 | — |
| token-efficient | 4 | `entropy_budget_fraction__1499bbc05821` |

The best token-efficient rule has:

- train/dev worst-model drop: 1.50 pp;
- train/dev worst-benchmark drop: 4.17 pp;
- dev Q20 saving: 1.39%;
- mean dev saving: 9.35%;
- positive-saving environments: 88.89%.

On the held-out test split, the same rule has a 1.67 pp worst-benchmark drop,
0.56 pp mean drop, −1.59% Q20 saving, and 14.29% mean saving. The negative Q20
means its savings are not uniformly positive despite a favorable mean.

## Accuracy floor and cross-split stability

The dev accuracy floor reaches 0.00 pp worst-benchmark drop, but the
tie-broken floor rule (`entropy_budget_fraction__1765371a32d1`) has −1.64% dev
Q20 saving and only 2.32% mean dev saving. Its test worst-benchmark drop is
0.67 pp.

Across all 17,712 rules, the Pearson correlation between dev and test
worst-benchmark accuracy drop is 0.899. Among the 1,224 rules with dev
worst-benchmark drop at most 1.5 pp, test drop ranges from 0.00 to 1.33 pp
with a 0.59 pp mean.

## Reproducibility

- Sweep: `generated/sweep_scale_llama.jsonl.gz`
- Per-rule metrics/frontier flag: `analysis/scale_llama_pareto.csv`
- Machine-readable summary and input hashes:
  `analysis/scale_llama_pareto_summary.json`
- Analysis command: `analysis/scale_model_pareto.py`
