# Human-evaluation adjudication

Raw rater exports and task HTML were not modified. This directory is a separate adjudication layer.

## Task A

- 134 cases; 70 pre-adjudication disagreements.
- 61 A/D conflicts resolved to D under the project operation of record.
- Final counts: A=24, B=2, C=1, D=82, E=25.
- The original two-rater agreement remains 47.76% (kappa 0.286); adjudication does not change inter-rater reliability.

## Task B

- 89 risk-enriched cases; 5 conflicts adjudicated; 8 final grader errors.
- Risk-enriched sample error rate: 8.99%.
- This rate is not a population-wide grader error estimate.

## Reproduce

```bash
MPLCONFIGDIR=/tmp/governor-mpl python -m benchmark.FalseConsensus.human_eval.adjudicate_reviews
```
