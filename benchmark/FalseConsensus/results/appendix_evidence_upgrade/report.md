# Appendix Evidence Upgrade Audit

This report recomputes broader evidence from fixed local artifacts. It does not run a model or select a policy.

## Confirmation

- Observed 23/24 planned environments and 906/912 trajectories, 81,720 dense probes, 33,283 adaptive probes; complete=False.
- The retained four-model Test frontier is invalid because the Llama run generated degenerate punctuation/repetition; same-model Dev/Test and Qwen-32B scale evidence must be reported separately.

## Related work

- 18 model-method-benchmark Dev rows cover 2 models, 3 methods, 3 benchmarks, and 3 seeds per cell.
- Test rows available: 0.

## DEER components

- Frozen DEER Dev readouts: 486 paired cases; trial/readout disagreement 14.81%; trial/readout accuracy 88.68%/88.48%; mean readout 470.5 output tokens.
- Online raw audit: 36 complete run dirs, 1368 method-problem rows; complete=True.
- First branches: 117; transitions={'correct_to_correct': 79, 'correct_to_wrong': 1, 'wrong_to_correct': 1, 'wrong_to_wrong': 36}.
- All first-branch verifications terminate at 64-64 tokens; finish reasons {'length': 117}.
- Direct Stage-1 counterfactual changes macro accuracy by +0.000 pp and saving by +0.764 pp.

## Unchanged gaps

- No returned Task-A/Task-B human annotation CSV is present; taxonomy claims remain preliminary.
- Related-work baselines and the full online boundary controller still have no held-out Test run in the retained artifacts.
- No interval × probe-length × KV-reuse factorial ablation or DEER-v3 `C_cali` implementation is present.
