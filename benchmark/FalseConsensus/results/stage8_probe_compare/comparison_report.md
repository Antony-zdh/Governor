# Stage 8 — Probe design comparison (SS6.4 metrics)

Compared on the same 100 main trajectories / checkpoints (Stage 8 subset). Dynasor early-stop window `bar=3`, agreement window `5`. P0 = current 10-token probe (from probes.csv); P1_32/P1_64 = longer continuation budget; P2/P3/P4 = instruction/tag probes.

## Metric table

| design   |   n_problems |   n_checkpoints |   empty_rate |   parse_ok_rate |   artifact_rate |   valid_answer_rate |   window_cce |   n_with_share |   stop_rate |   stop_accuracy |   stop_final_acc |   token_saving |   wrong_stops |   ready_rate |   ready_precision |   ready_n |   nominal_budget |   mean_output_len |
|:---------|-------------:|----------------:|-------------:|----------------:|----------------:|--------------------:|-------------:|---------------:|------------:|----------------:|-----------------:|---------------:|--------------:|-------------:|------------------:|----------:|-----------------:|------------------:|
| P0       |          100 |            1737 |        0.100 |           0.900 |           0.100 |               0.900 |        0.141 |         94.000 |       0.730 |           0.589 |            0.795 |       1351.521 |            30 |      nan     |           nan     |   nan     |               10 |             0.000 |
| P1_32    |          100 |            1737 |        0.006 |           0.994 |           0.006 |               0.994 |        0.148 |        100.000 |       0.900 |           0.567 |            0.767 |       1392.533 |            39 |      nan     |           nan     |   nan     |               32 |            88.489 |
| P1_64    |          100 |            1737 |        0.003 |           0.997 |           0.003 |               0.997 |        0.155 |        100.000 |       0.910 |           0.571 |            0.758 |       1361.758 |            39 |      nan     |           nan     |   nan     |               64 |           169.398 |
| P2       |          100 |            1737 |        0.938 |           0.104 |           0.896 |               0.062 |        0.167 |          4.000 |       0.080 |           0.875 |            0.875 |       1131.375 |             1 |        0.062 |             0.673 |   107.000 |               40 |            72.537 |
| P3       |          100 |            1737 |        0.918 |           0.116 |           0.884 |               0.082 |        0.146 |          8.000 |       0.090 |           0.889 |            0.889 |        792.444 |             1 |        0.082 |             0.648 |   142.000 |               50 |            77.704 |
| P4       |          100 |            1737 |        0.999 |           0.001 |           0.999 |               0.001 |      nan     |        nan     |       0.000 |         nan     |          nan     |        nan     |             0 |        0.001 |             0.500 |     2.000 |               40 |           126.500 |

Notes:
- `parse_ok_rate` for P0 is proxied by P(answer non-empty) since P0 has no parse flag; for P1-P4 it is the recorded parser result.
- `artifact_rate = 1 - parse_ok_rate` (format not followed).
- `window_cce` = weighted mean |agreement_share - accuracy| over window-share bins (only problems with >=3 non-empty answers in the window contribute).
- `stop_*` use the Dynasor rule (last `bar` answers non-empty, design's certainty gate true, mutually equal). For P0 the gate is `is_certain`; P1 uses non-empty; P2/P3/P4 use the probe's explicit answer status.
- `ready_*` (P2/P3/P4 only): explicit readiness signal — precision = P(answer correct | probe status says ready).

## SS6.5 success-criteria check (factual, vs P0)

### P1_32
- artifact_rate: 0.006 vs P0 0.100 → lower
- empty_rate: 0.006 vs P0 0.100 → lower
- early-stop accuracy: 0.567 vs P0 0.589 → not higher  (token saving 1393 vs P0 1352)

### P1_64
- artifact_rate: 0.003 vs P0 0.100 → lower
- empty_rate: 0.003 vs P0 0.100 → lower
- early-stop accuracy: 0.571 vs P0 0.589 → not higher  (token saving 1362 vs P0 1352)

### P2
- artifact_rate: 0.896 vs P0 0.100 → not lower
- empty_rate: 0.938 vs P0 0.100 → not lower
- early-stop accuracy: 0.875 vs P0 0.589 → higher  (token saving 1131 vs P0 1352)

### P3
- artifact_rate: 0.884 vs P0 0.100 → not lower
- empty_rate: 0.918 vs P0 0.100 → not lower
- early-stop accuracy: 0.889 vs P0 0.589 → higher  (token saving 792 vs P0 1352)

### P4
- artifact_rate: 0.999 vs P0 0.100 → not lower
- empty_rate: 0.999 vs P0 0.100 → not lower
- early-stop: stop_rate=0.000 (P0 0.730); accuracy/token-saving N/A (design rarely/never produces a stop window).
