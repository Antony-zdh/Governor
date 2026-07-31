# DEER confidence bank, cap 30

This experiment measures the DEER answer-probability signal independently of
DEER's expensive formal readout.

## Frozen protocol

- Inputs: the existing Governor v2 frozen main trajectories for
  MATH500/AMC23/AIME24, DeepSeek-7B/Qwen3-8B, development seeds 42/43/44 and
  confirmation seeds 45/46/47.
- Trigger: the first 30 case-insensitive whole-word `Wait` positions.
- Probe: the pinned DEER trial-answer prompt and model-specific confidence
  calculation from `deer.py`.
- Collection: never stop early and never issue a formal readout.
- Reuse: copy compatible trials from the faithful `deer_frozen` result, then
  generate only missing positions.
- Offline action: submit the first non-empty parsed trial answer whose
  confidence is strictly greater than the selected threshold.
- Fallback: if no valid trial crosses the threshold, use the frozen Full
  outcome.

The paper-faithful DEER point (`threshold=0.95` plus formal readout) remains a
separate immutable baseline. The new curve must be labeled
`DEER-confidence direct-commit frontier`.

## Collection

One process handles one deterministic shard and one explicit endpoint:

```bash
python -m benchmark.FalseConsensus.related_work.launch_deer_confidence_bank \
  --model-key deepseek \
  --endpoint http://127.0.0.1:18100/v1 \
  --shard-index 0 --num-shards 4 --workers 4
```

Repeat shard indices 0--3 for DeepSeek and Qwen3 against eight independent
single-GPU endpoints. The launcher covers both `full` and `test` scopes by
default and is safely resumable.

## Audit and packing

```bash
python -m benchmark.FalseConsensus.related_work.audit_deer_confidence_bank \
  --root benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30 \
  --output benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30/summary.json \
  --expected-environments 36 --pack
```

The audit requires 36 complete environments, no missing problems, no trial
errors, sequential candidate IDs, non-empty logprob arrays, and the exact
cap-30 schema. It reports raw and validity-gated probabilities for
`confidence > 0.995` within the first 10, 20, and 30 Waits, with Wilson 95%
intervals.

After packing, repeat the command with `--archives-only` and without `--pack`
to validate the committed representation independently of resumable raw files.

Raw per-problem files under each `trials/` directory are resumable runtime
state and are ignored by Git. The committed data are the deterministic
`trials.jsonl.gz` archives, `bank_manifest.json` files, and global
`summary.json`.
