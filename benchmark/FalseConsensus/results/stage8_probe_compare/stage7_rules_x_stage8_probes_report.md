# Stage 7 winning rules re-tested with Stage 8 probe designs

Same two rule configs Stage 7 selected as usable operating points (Conservative/Balanced, `consecutive` family), unchanged -- only the probe-answer/certainty signal feeding them is swapped, on the same 100-problem Stage 8 subset. P0-on-subset is recomputed here as the fair baseline (Stage 7's report.md numbers were n=500, not directly comparable).

## Conservative: 8-consecutive, min_tok=1024, certain=True (`consec_p8_mt1024_cert1`)

                     config_id  n_problems_used  overall_accuracy  stop_coverage  correct_stop_rate  false_stop_rate  avg_main_tokens  avg_probe_output_tokens  avg_total_generated_tokens  correct_to_wrong_truncation  wrong_to_correct_recovery_truncated
design                                                                                                                                                                                                                                                      
P0      consec_p8_mt1024_cert1              100              0.78           0.36           0.916667         0.083333          2042.58                   157.50                     2200.08                            0                                    0
P1_32   consec_p8_mt1024_cert1              100              0.78           0.40           0.900000         0.100000          2014.17                   497.28                     2511.45                            0                                    1
P1_64   consec_p8_mt1024_cert1              100              0.79           0.25           0.920000         0.080000          2098.88                  1032.96                     3131.84                            0                                    0
P2      consec_p8_mt1024_cert1              100              0.78           0.00                NaN              NaN          2266.45                   694.80                     2961.25                            0                                    0
P3      consec_p8_mt1024_cert1              100              0.78           0.01           1.000000         0.000000          2250.49                   862.50                     3112.99                            0                                    0
P4      consec_p8_mt1024_cert1              100              0.78           0.00                NaN              NaN          2266.45                   694.80                     2961.25                            0                                    0

- **P1_32** vs P0: accuracy 78.0% (+0.0%), coverage 40.0% (+4.0%), total tokens 2511 (+311)
- **P1_64** vs P0: accuracy 79.0% (+1.0%), coverage 25.0% (-11.0%), total tokens 3132 (+932)
- **P2** vs P0: accuracy 78.0% (+0.0%), coverage 0.0% (-36.0%), total tokens 2961 (+761)
- **P3** vs P0: accuracy 78.0% (+0.0%), coverage 1.0% (-35.0%), total tokens 3113 (+913)
- **P4** vs P0: accuracy 78.0% (+0.0%), coverage 0.0% (-36.0%), total tokens 2961 (+761)

## Balanced: 6-consecutive, min_tok=1024, certain=False (`consec_p6_mt1024_cert0`)

                     config_id  n_problems_used  overall_accuracy  stop_coverage  correct_stop_rate  false_stop_rate  avg_main_tokens  avg_probe_output_tokens  avg_total_generated_tokens  correct_to_wrong_truncation  wrong_to_correct_recovery_truncated
design                                                                                                                                                                                                                                                      
P0      consec_p6_mt1024_cert0              100              0.77           0.58           0.793103         0.206897          1786.15                   138.00                     1924.15                            0                                    2
P1_32   consec_p6_mt1024_cert0              100              0.77           0.60           0.800000         0.200000          1747.17                   432.00                     2179.17                            0                                    4
P1_64   consec_p6_mt1024_cert0              100              0.75           0.58           0.793103         0.206897          1762.53                   871.68                     2634.21                            0                                    5
P2      consec_p6_mt1024_cert0              100              0.78           0.01           1.000000         0.000000          2249.21                   689.60                     2938.81                            0                                    0
P3      consec_p6_mt1024_cert0              100              0.78           0.02           1.000000         0.000000          2247.02                   861.50                     3108.52                            0                                    0
P4      consec_p6_mt1024_cert0              100              0.78           0.00                NaN              NaN          2266.45                   694.80                     2961.25                            0                                    0

- **P1_32** vs P0: accuracy 77.0% (+0.0%), coverage 60.0% (+2.0%), total tokens 2179 (+255)
- **P1_64** vs P0: accuracy 75.0% (-2.0%), coverage 58.0% (+0.0%), total tokens 2634 (+710)
- **P2** vs P0: accuracy 78.0% (+1.0%), coverage 1.0% (-57.0%), total tokens 2939 (+1015)
- **P3** vs P0: accuracy 78.0% (+1.0%), coverage 2.0% (-56.0%), total tokens 3109 (+1184)
- **P4** vs P0: accuracy 78.0% (+1.0%), coverage 0.0% (-58.0%), total tokens 2961 (+1037)
