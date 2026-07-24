# Stage 10 v2 - multi-candidate rule funnel

## Frozen protocol

- risk bands are exclusive on DeepSeek train accuracy drop: conservative <=1pp, balanced (1,3]pp, exploratory (3,6]pp
- train carries up to 40 candidates per band
- validation carries up to 15 per band and must satisfy the same band upper bound on both train and validation
- the former 99-problem test split is explicitly renamed validation-2 because it now participates in selection; it carries up to 10 per band
- validation-2 promotion allows a +2pp point-estimate buffer because n=99 is discrete/noisy; Qwen simple@32 is the external final gate
- every round reserves equal quota for consecutive and history families before filling remaining slots by token cost

## Funnel counts

- train: 120 (conservative=40, balanced=40, exploratory=40)
- validation: 45 (conservative=15, balanced=15, exploratory=15)
- validation-2 evaluated: 45 (conservative=15, balanced=15, exploratory=15)
- finalists: 21 (conservative=6, balanced=7, exploratory=8)

## Finalists after DeepSeek validation-2

| Band | Config | Family | Accuracy | Tokens | Coverage | False-stop | Drop |
|---|---|---|---:|---:|---:|---:|---:|
| conservative | `consec_p5_level768-1536_cert1_validschema` | consecutive | 75.8% | 1739 | 62.6% | 17.7% | +1.0pp |
| conservative | `consec_p4_level768-2048_cert1_validschema` | consecutive | 75.8% | 1807 | 62.6% | 17.7% | +1.0pp |
| conservative | `hist_w5_mv3_s1.0_level768-2048_swany_span0_cert1_validschema` | history | 75.8% | 1837 | 60.6% | 18.3% | +1.0pp |
| conservative | `hist_w5_mv5_s1.0_level768-2048_swany_span0_cert1_validschema` | history | 76.8% | 1854 | 57.6% | 15.8% | +0.0pp |
| conservative | `hist_w5_mv3_s1.0_fixed1536_swany_span0_cert1_validschema` | history | 74.7% | 1883 | 56.6% | 23.2% | +2.0pp |
| conservative | `hist_w5_mv5_s1.0_fixed1536_swany_span0_cert0_validschema` | history | 75.8% | 1902 | 53.5% | 20.8% | +1.0pp |
| balanced | `consec_p4_fixed1024_cert1_validschema` | consecutive | 74.7% | 1564 | 72.7% | 22.2% | +2.0pp |
| balanced | `hist_w5_mv3_s1.0_fixed768_swany_span0_cert1_validschema` | history | 74.7% | 1570 | 74.7% | 21.6% | +2.0pp |
| balanced | `hist_w5_mv3_s1.0_fixed1024_swany_span0_cert1_validschema` | history | 75.8% | 1644 | 71.7% | 21.1% | +1.0pp |
| balanced | `consec_p4_level768-1536_cert1_validschema` | consecutive | 73.7% | 1660 | 67.7% | 20.9% | +3.0pp |
| balanced | `hist_w5_mv3_s1.0_level512-1536_swany_span0_cert0_validschema` | history | 74.7% | 1663 | 66.7% | 19.7% | +2.0pp |
| balanced | `consec_p5_fixed1024_cert1_validschema` | consecutive | 76.8% | 1684 | 67.7% | 17.9% | +0.0pp |
| balanced | `hist_w5_mv5_s1.0_fixed1024_swany_span0_cert1_validschema` | history | 76.8% | 1684 | 67.7% | 17.9% | +0.0pp |
| exploratory | `consec_p3_fixed1024_cert1_validschema` | consecutive | 72.7% | 1434 | 75.8% | 28.0% | +4.0pp |
| exploratory | `consec_p4_level512-1024_cert1_validschema` | consecutive | 74.7% | 1461 | 75.8% | 21.3% | +2.0pp |
| exploratory | `consec_p4_fixed768_cert1_validschema` | consecutive | 74.7% | 1475 | 75.8% | 21.3% | +2.0pp |
| exploratory | `consec_p3_level512-1536_cert1_validschema` | consecutive | 70.7% | 1484 | 72.7% | 27.8% | +6.1pp |
| exploratory | `hist_w5_mv3_s0.8_fixed1024_swany_span0_cert1_validschema` | history | 74.7% | 1488 | 73.7% | 23.3% | +2.0pp |
| exploratory | `hist_w5_mv3_s1.0_fixed512_swany_span0_cert1_validschema` | history | 74.7% | 1500 | 75.8% | 21.3% | +2.0pp |
| exploratory | `hist_w5_mv5_s0.8_fixed1024_swany_span0_cert1_validschema` | history | 74.7% | 1518 | 71.7% | 22.5% | +2.0pp |
| exploratory | `hist_w5_mv3_s0.8_level512-1536_swany_span0_cert0_validschema` | history | 73.7% | 1535 | 70.7% | 22.9% | +3.0pp |

## Matched Qwen simple@32 external gate

| Band | Config | Family | Accuracy | Tokens | Coverage | False-stop | Drop |
|---|---|---|---:|---:|---:|---:|---:|
| balanced | `consec_p4_fixed1024_cert1_validschema` | consecutive | 72.6% | 1462 | 93.6% | 25.2% | +5.2pp |
| balanced | `hist_w5_mv3_s1.0_fixed768_swany_span0_cert1_validschema` | history | 73.2% | 1466 | 89.6% | 23.7% | +4.6pp |
| balanced | `consec_p4_level768-1536_cert1_validschema` | consecutive | 74.2% | 1575 | 92.2% | 23.2% | +3.6pp |
| balanced | `hist_w5_mv3_s1.0_fixed1024_swany_span0_cert1_validschema` | history | 74.6% | 1584 | 89.4% | 22.1% | +3.2pp |
| balanced | `consec_p5_fixed1024_cert1_validschema` | consecutive | 74.6% | 1599 | 89.2% | 22.0% | +3.2pp |
| balanced | `hist_w5_mv5_s1.0_fixed1024_swany_span0_cert1_validschema` | history | 74.6% | 1599 | 89.2% | 22.0% | +3.2pp |
| balanced | `hist_w5_mv3_s1.0_level512-1536_swany_span0_cert0_validschema` | history | 75.2% | 1613 | 88.6% | 21.0% | +2.6pp |
| conservative | `consec_p5_level768-1536_cert1_validschema` | consecutive | 75.8% | 1678 | 88.4% | 20.1% | +2.0pp |
| conservative | `consec_p4_level768-2048_cert1_validschema` | consecutive | 76.0% | 1791 | 87.8% | 20.7% | +1.8pp |
| conservative | `hist_w5_mv3_s1.0_level768-2048_swany_span0_cert1_validschema` | history | 77.0% | 1862 | 83.8% | 18.4% | +0.8pp |
| conservative | `hist_w5_mv5_s1.0_level768-2048_swany_span0_cert1_validschema` | history | 76.8% | 1869 | 83.6% | 18.4% | +1.0pp |
| conservative | `hist_w5_mv3_s1.0_fixed1536_swany_span0_cert1_validschema` | history | 77.4% | 1935 | 85.8% | 19.1% | +0.4pp |
| conservative | `hist_w5_mv5_s1.0_fixed1536_swany_span0_cert0_validschema` | history | 77.2% | 1940 | 85.6% | 19.2% | +0.6pp |
| exploratory | `hist_w5_mv3_s1.0_fixed512_swany_span0_cert1_validschema` | history | 70.8% | 1289 | 90.8% | 27.1% | +7.0pp |
| exploratory | `consec_p4_level512-1024_cert1_validschema` | consecutive | 71.0% | 1314 | 93.8% | 26.9% | +6.8pp |
| exploratory | `consec_p3_fixed1024_cert1_validschema` | consecutive | 70.8% | 1322 | 96.8% | 28.3% | +7.0pp |
| exploratory | `consec_p4_fixed768_cert1_validschema` | consecutive | 71.0% | 1326 | 93.8% | 26.9% | +6.8pp |
| exploratory | `hist_w5_mv3_s0.8_fixed1024_swany_span0_cert1_validschema` | history | 69.4% | 1337 | 96.8% | 29.8% | +8.4pp |
| exploratory | `hist_w5_mv5_s0.8_fixed1024_swany_span0_cert1_validschema` | history | 69.6% | 1350 | 96.6% | 29.4% | +8.2pp |
| exploratory | `consec_p3_level512-1536_cert1_validschema` | consecutive | 70.8% | 1377 | 95.4% | 28.1% | +7.0pp |
| exploratory | `hist_w5_mv3_s0.8_level512-1536_swany_span0_cert0_validschema` | history | 71.0% | 1413 | 95.4% | 27.5% | +6.8pp |

Qwen is a final gate over multiple predeclared finalists, not an untouched estimator after choosing the winner. A new seed is required for the final unbiased performance estimate.

## Provisional recommendation

`hist_w5_mv5_s1.0_level768-2048_swany_span0_cert1_validschema`

Selection rule: first require <=1pp point-estimate accuracy drop on both DeepSeek validation-2 and matched Qwen; among the passing conservative candidates, balance token cost and false-stop rather than minimizing tokens alone.

- Plain-language rule: five valid, certain, schema-valid probes must agree; level 1-3 may stop after 768 tokens and level 4-5 after 2,048.
- DeepSeek validation-2: accuracy 76.8%, total tokens 1854, false-stop 15.8%.
- Matched Qwen simple@32: accuracy 76.8%, total tokens 1869, false-stop 18.4%.
- Stage-7 Conservative v0 remains the lower-false-stop fallback; a new seed is required before deployment.
