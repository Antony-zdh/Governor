# G2 boundary-aligned consensus report

## 1. Gate clearance on the boundary-aligned stream (dev, macro over 18 envs)

Prediction (hypothesis a): 0 rules clear any gate. Outcome (b) -- a gate clears -- would be a major finding and is reported as found, not tuned away.

| gate | drop cap | saving floor | psf | rules clearing (boundary) |
|---|---:|---:|---:|---:|
| conservative | 1.0pp | 10% | 0.8 | 0 |
| balanced | 2.0pp | 20% | 0.8 | 0 |
| token_efficient | 3.5pp | 30% | 0.7 | 0 |

Verdict: the boundary-aligned consensus stream **clears NO gate (0 rules on any gate)** on dev.

## 2. Accuracy-drop / net-saving frontier

| quantity | boundary stream | committed fixed-grid consensus |
|---|---:|---:|
| max net saving among drop<=1.0pp | 3.93% | n/a |
| drop at first 10% saving | 3.75pp | 2.66pp |
| drop at first 20% saving | 10.18pp | 6.17pp |
| drop at first 30% saving | 13.48pp | 11.76pp |

## 3. Harm:rescue by window W

| W | stops (boundary) | harm | rescue | observed | base-rate null | stops (committed) | harm (committed) | rescue (committed) | committed ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 618 | 253 | 11 | 22.04 | 8.14 | 668 | 361 | 8 | 42.53 |
| 3 | 491 | 127 | 12 | 10.20 | 3.98 | 639 | 180 | 7 | 24.07 |
| 5 | 358 | 78 | 9 | 8.26 | 3.65 | 603 | 120 | 9 | 12.68 |
| 8 | 235 | 48 | 7 | 6.47 | 3.28 | 525 | 69 | 8 | 8.18 |
| 12 | 160 | 31 | 5 | 5.73 | 2.82 | 420 | 40 | 7 | 5.40 |
| 16 | 113 | 21 | 5 | 3.91 | 2.66 | 311 | 30 | 7 | 4.07 |
| 24 | 56 | 11 | 4 | 2.56 | 2.20 | 193 | 13 | 5 | 2.45 |
| 30 | 15 | 3 | 1 | 2.33 | 1.83 | 121 | 8 | 4 | 1.89 |

## 4. Plain-language verdict

Hypothesis **(a)** is supported: the consensus family still clears no gate on dev when read at DEER's own boundary positions. The timing confound is eliminated by measurement rather than by hedging -- the failure is in *what* is read (the signal), not in *when* it is read. §5.7's fourth qualification can be promoted to a positive result.

Harm:rescue on the boundary stream is reported alongside the committed fixed-grid values (45.1:1 -> 2.0:1) above; excess over the base-rate null is in summary.json.
