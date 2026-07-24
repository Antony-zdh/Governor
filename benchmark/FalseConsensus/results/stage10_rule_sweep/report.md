# Stage 10 v1 — simple@32 rule sweep

This is an offline replay; no model calls were made.

## Protocol

- split: train 300, validation 101, test 99, stratified by MATH level
- selection: conservative/balanced bounds must hold independently on both train and validation; among qualifying rules, minimize pooled development cost. Test is reported only for selected rules
- primary cost: vanilla has no probe cost; controller methods include actual simple@32 probe output tokens
- validity filter: `schema` removes empty and single-letter A–D answers for this non-multiple-choice dataset
- difficulty floors: fixed, MATH-level adaptive, and an online early-instability proxy based on the first four probes
- frozen baselines evaluated on test without selection: naive p3, Stage-7 Conservative p8+1024, and Stage-7 Balanced p6+1024; the two Stage-7 rules receive the same schema filter as Governor++ v0

The Stage-6 human audit has only 100 completed labels and audited the old @10 probe, so it is not used as if it were a full per-probe label set for @32. The schema filter is the available evidence-backed deterministic filter.

## Selected configurations

- **aggressive**: `consec_p3_fixed0_cert0_validnonempty`
  - `{"config_id": "consec_p3_fixed0_cert0_validnonempty", "easy_min": 0, "family": "consecutive", "floor_kind": "fixed", "hard_min": 0, "patience": 3, "require_certain": false, "validity_mode": "nonempty"}`
- **balanced**: `consec_p3_level768-1536_cert0_validschema`
  - `{"config_id": "consec_p3_level768-1536_cert0_validschema", "easy_min": 768, "family": "consecutive", "floor_kind": "level", "hard_min": 1536, "patience": 3, "require_certain": false, "validity_mode": "schema"}`
- **conservative**: `consec_p3_level768-2048_cert0_validschema`
  - `{"config_id": "consec_p3_level768-2048_cert0_validschema", "easy_min": 768, "family": "consecutive", "floor_kind": "level", "hard_min": 2048, "patience": 3, "require_certain": false, "validity_mode": "schema"}`

## Validation operating points

| Point | Accuracy | Δ accuracy [95% CI] | Total tokens | Saving [95% CI] | Coverage | False-stop | Recovery cut | Overthinking saved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| vanilla | 80.2% | N/A | 2426 | N/A | 0.0% | N/A | 0 | 0 |
| conservative | 81.2% | N/A | 1783 | N/A | 70.3% | 16.9% | 2 | 3 |
| balanced | 78.2% | N/A | 1616 | N/A | 77.2% | 20.5% | 5 | 3 |
| aggressive | 65.3% | N/A | 1143 | N/A | 93.1% | 35.1% | 19 | 4 |

## Held-out DeepSeek test

| Point | Accuracy | Δ accuracy [95% CI] | Total tokens | Saving [95% CI] | Coverage | False-stop | Recovery cut | Overthinking saved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| vanilla | 76.8% | +0.0pp [+0.0, +0.0] | 2252 | 0.0% [0.0%, 0.0%] | 0.0% | N/A | 0 | 0 |
| naive | 58.6% | -18.2pp [-27.3, -9.1] | 1039 | 53.9% [47.6%, 59.7%] | 90.9% | 41.1% | 22 | 4 |
| stage7_conservative_v0 | 78.8% | +2.0pp [-2.0, +6.1] | 1937 | 14.0% [9.3%, 19.0%] | 50.5% | 10.0% | 1 | 3 |
| stage7_balanced_v0 | 77.8% | +1.0pp [-3.0, +5.1] | 1789 | 20.6% [15.3%, 26.0%] | 60.6% | 11.7% | 2 | 3 |
| conservative | 72.7% | -4.0pp [-9.1, +1.0] | 1737 | 22.9% [17.4%, 28.5%] | 64.6% | 25.0% | 6 | 2 |
| balanced | 71.7% | -5.1pp [-11.1, +1.0] | 1555 | 31.0% [25.6%, 36.4%] | 70.7% | 27.1% | 7 | 2 |
| aggressive | 58.6% | -18.2pp [-27.3, -9.1] | 1039 | 53.9% [47.6%, 59.7%] | 90.9% | 41.1% | 22 | 4 |

## Qwen3-8B transfer hold-out

| Point | Accuracy | Δ accuracy [95% CI] | Total tokens | Saving [95% CI] | Coverage | False-stop | Recovery cut | Overthinking saved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| vanilla | 77.8% | +0.0pp [+0.0, +0.0] | 2757 | 0.0% [0.0%, 0.0%] | 0.0% | N/A | 0 | 0 |
| naive | 74.0% | -3.8pp [-6.4, -1.4] | 2014 | 26.9% [23.9%, 29.9%] | 68.0% | 16.2% | 30 | 11 |
| stage7_conservative_v0 | 78.0% | +0.2pp [-0.4, +0.8] | 2783 | -1.0% [-2.2%, 0.2%] | 35.6% | 2.8% | 1 | 2 |
| stage7_balanced_v0 | 74.0% | -3.8pp [-6.2, -1.4] | 1817 | 34.1% [31.7%, 36.5%] | 81.2% | 18.7% | 30 | 11 |
| conservative | 72.8% | -5.0pp [-7.8, -2.2] | 1796 | 34.8% [32.4%, 37.1%] | 86.2% | 23.2% | 37 | 12 |
| balanced | 71.0% | -6.8pp [-10.0, -3.8] | 1570 | 43.1% [40.9%, 45.1%] | 90.4% | 25.7% | 50 | 16 |
| aggressive | 58.8% | -19.0pp [-23.0, -15.0] | 953 | 65.4% [63.0%, 67.8%] | 93.4% | 39.8% | 108 | 13 |

## Decision

The expanded difficulty-adaptive p3 rules pass the development constraints but fail to preserve accuracy on DeepSeek test and Qwen. They therefore do not qualify as Governor++ operating points.

The frozen Stage-7 Conservative v0 is the only tested rule that preserves accuracy on both DeepSeek test and Qwen. Its DeepSeek test saving is modest, and on Qwen its probe overhead cancels the main-token saving. The frozen Balanced v0 saves more on DeepSeek but incurs a clear Qwen accuracy loss. Thus this sweep does not demonstrate a cross-model Pareto improvement beyond the existing conservative rule; the accuracy–compute ceiling remains.

Because the rule upgrade failed held-out transfer, do not train or promote a calibrator from this sweep alone. A matched Qwen @32 stream and/or new seed is needed for the next clean validation.

Qwen has only a `simple@10` probe stream. This section tests whether the selected rule transfers without tuning, but it is not a clean simple@32 compute comparison. A matched Qwen simple@32 re-probe is required before making a cross-model probe-cost claim.

Full train/validation grids and per-problem selected outputs are stored beside this report.
