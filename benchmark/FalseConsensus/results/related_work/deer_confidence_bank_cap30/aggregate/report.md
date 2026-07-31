# DEER cap-30 direct-submit frontier

The replay accepts the first non-empty DEER answer with confidence strictly above the threshold, directly submits it without a formal readout, and otherwise retains the frozen full answer. Token saving charges all generated probe-output tokens through the decision.

| Scope | Threshold | Accuracy | Drop | Token saving | Stop rate | Stopped accuracy | False-stop | Avg probes | Harm / rescue |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full | 0.950000 | 85.60% | +2.96 pp | 46.22% | 83.59% | 90.38% | 9.62% | 7.33 | 117/36 (3.25) |
| test | 0.950000 | 92.25% | +2.05 pp | 52.68% | 86.70% | 94.27% | 5.73% | 6.68 | 22/8 (2.75) |
| full | 0.990000 | 87.46% | +1.10 pp | 39.73% | 79.57% | 93.98% | 6.02% | 8.20 | 54/24 (2.25) |
| test | 0.990000 | 94.15% | +0.15 pp | 46.10% | 83.33% | 97.19% | 2.81% | 7.53 | 9/8 (1.12) |
| full | 0.995000 | 88.01% | +0.55 pp | 37.10% | 77.45% | 95.09% | 4.91% | 8.50 | 35/20 (1.75) |
| test | 0.995000 | 94.44% | -0.15 pp | 44.13% | 82.16% | 97.51% | 2.49% | 7.81 | 7/8 (0.88) |
| full | 0.999000 | 88.60% | -0.04 pp | 32.23% | 73.57% | 96.52% | 3.48% | 9.18 | 15/16 (0.94) |
| test | 0.999000 | 94.30% | +0.00 pp | 37.61% | 77.49% | 98.11% | 1.89% | 8.65 | 4/4 (1.00) |
| full | 0.999990 | 88.67% | -0.11 pp | 15.49% | 44.04% | 98.09% | 1.91% | 11.46 | 5/8 (0.62) |
| test | 0.999990 | 94.30% | +0.00 pp | 19.56% | 48.25% | 100.00% | 0.00% | 10.88 | 0/0 (∞) |
| full | 0.999999 | 88.74% | -0.18 pp | 9.25% | 30.41% | 98.92% | 1.08% | 12.17 | 0/5 (0.00) |
| test | 0.999999 | 94.30% | +0.00 pp | 11.11% | 32.02% | 100.00% | 0.00% | 11.95 | 0/0 (∞) |
| full | 1.000000 | 88.56% | +0.00 pp | -2.48% | 0.00% | nan% | nan% | 13.25 | 0/0 (∞) |
| test | 1.000000 | 94.30% | +0.00 pp | -2.50% | 0.00% | nan% | nan% | 13.09 | 0/0 (∞) |

## Faithful related-work anchors

| Scope | Method | Accuracy drop | Token saving |
|---|---|---:|---:|
| full | deer_frozen | +4.31 pp | 28.80% |
| full | tje_frozen | +6.14 pp | 27.05% |
| test | deer_frozen | +6.73 pp | 33.39% |
| test | tje_frozen | +6.73 pp | 26.11% |

## Same-threshold comparison (tau=0.95, cap=10)

At the same threshold and cap, direct submit omits the readout and therefore saves more tokens. With the project robust mathematical equivalence grader, it also has a smaller measured accuracy drop than the faithful readout variant.

| Scope | Variant | Accuracy drop | Token saving |
|---|---|---:|---:|
| full | Direct submit | +2.41 pp | 35.16% |
| full | Faithful DEER + readout | +4.31 pp | 28.80% |
| test | Direct submit | +2.05 pp | 40.34% |
| test | Faithful DEER + readout | +6.73 pp | 33.39% |

## Direct submit at approximately matched faithful-DEER accuracy

| Scope | Cap | Threshold | Direct drop | Direct saving | Faithful DEER drop | Faithful DEER saving |
|---|---:|---:|---:|---:|---:|---:|
| full | 10 | 0.925 | +3.95 pp | 37.54% | +4.31 pp | 28.80% |
| full | 20 | 0.925 | +4.71 pp | 45.08% | +4.31 pp | 28.80% |
| full | 30 | 0.925 | +4.79 pp | 48.99% | +4.31 pp | 28.80% |
| test | 10 | 0.9 | +4.97 pp | 44.25% | +6.73 pp | 33.39% |
| test | 20 | 0.9 | +5.70 pp | 54.34% | +6.73 pp | 33.39% |
| test | 30 | 0.9 | +5.85 pp | 57.17% | +6.73 pp | 33.39% |
