# Governor v2 — unified (W, s) consensus sweep + jointly-swept DEER

Created 2026-08-02. Supersedes the v1 17,712-rule sweep (archived at
`governor_v2/generated/backup_v1_sweep_20260802/`).

## What this is

A preregistered Pareto sweep of the **consensus early-exit signal**, collapsed to
two hyperparameters — **window size** `W ∈ {1,3,5,8,12,16,24,30}` and **share
threshold** `s ∈ {0.6,0.8,1.0}` — plus operational knobs (probe interval
{64,128,256,512}, validity {nonempty,schema}, maturity min_tokens
{0,512,1024,2048,4096}, certainty {off,on}) over a fixed-schedule and an
event-triggered family. Enumerates to **3,520 rules** (after dropping the
behaviourally redundant `W=1, s≠1.0` cases).

**DEER** (trial-answer-submit variant) is swept over 14 confidence thresholds
through the **same pipeline, gates, and token accounting**, to test whether the
failure is early exit itself or the consensus signal.

All accuracy uses the **robust grader** (`grading.robust_answers_equal`); the v1
sweep had a grader-import bug that silently used a weak fallback when run as a
module (see `log.md` 2026-08-02).

## Gates (preregistered)

Applied in order on dev (macro over 18 model×benchmark×seed environments):
`total accuracy drop ≤ cap` → `total net token saving ≥ floor` → `psf ≥ floor`.

| Operating point | Max drop | Min saving | psf |
|---|---|---|---|
| conservative | 1.0 pp | 10% | 0.80 |
| balanced | 2.0 pp | 20% | 0.80 |
| token_efficient | 3.5 pp | 30% | 0.70 |

## Headline result (dev, macro over 18 environments)

- **Consensus: 0 / 3,520 rules clear any gate.** Capping drop at 1.0 pp allows at
  most 0.2% net saving; reaching 10% saving costs 2.66 pp, 20% costs 6.17 pp,
  30% costs 11.8 pp. Large windows (up to W=30) buy low drop only by stopping so
  late that net saving collapses to ~0.
- **DEER clears all three gates**: conservative 0.33 pp @ 28.2%, balanced
  1.03 pp @ 29.6%, token_efficient 2.75 pp @ 31.9%; near-neutral −0.06 pp @ 20.8%.
- Full-generation baseline accuracy 82.5% (matches DEER's baseline — grader fix).

→ Early exit is possible; the **consensus signal** is what cannot make it safe.

## Generalization

- Held-out **test split** (dev models, unseen seeds 45–47): consensus drop tracks
  dev at **r=0.98**; the joint conservative gate is empty for consensus (0 on dev,
  444 on test-alone in-sample winners, 0 on both), while DEER clears both splits
  (3 thresholds conservative, 5 balanced).
- Unseen **scale** (Qwen-32B) and **architecture/family** (Llama-8B), now at
  **three test seeds (45/46/47), 9 env each** (`heldout_test/`): frontier
  reproduces r=**0.97** (32B) and r=**0.94** (Llama). The **conservative gate is
  empty on every model** (dev, 32B, Llama all admit 0; best rule under 1.0pp drop
  saves 0.6% on 32B, 9.3% on Llama). Scale effect at looser gates: on 32B a few
  consensus rules become admissible in-sample (4 balanced, 6 token_efficient) —
  a larger model's answers stabilize a bit earlier — but these are not dev-selected
  (dev admits none) and Llama stays 0/0/0. (Earlier single-seed heldout numbers
  r=0.95/0.87 with spurious in-sample passers were seed-45-only noise; superseded.)
- **Heterogeneity (honest):** DEER's advantage over consensus is largest on
  Qwen3-8B and MATH500 and weak/noisy on DeepSeek-7B and AIME24 (see
  `report/figures/panels/`). DEER is a positive control for the signal, not a
  benchmarked SOTA.
- DEER on 32B/Llama: confidence bank not collected there → future GPU work.

## Files

- `dev/consensus_dev_train.jsonl.gz` — 126,720 rows (3,520 × 18 env × {train,dev}).
- `test/consensus_test.jsonl.gz` — 253,440 rows (dev models seeds 45–47 + heldout
  32B/Llama seed 45; multiple evaluation budgets — filter to the selection budget
  per benchmark: 16384 MATH500/AMC23, 32768 AIME24).
- `deer/deer_threshold_sweep.jsonl.gz` — 756 rows (14 τ × train/dev/test envs).
- `select_v2_robust.json` — gate selection summary.
- `candidate_rules_v2.jsonl.gz`, `protocol_v2.json`, `manifest.json` — provenance.

## Reproduce

```bash
cd benchmark/FalseConsensus/governor_v2
python make_protocol_v2.py                      # protocol_v2.json + candidate_rules_v2.jsonl
# consensus dev (shard in parallel), run as module from repo root:
python -m benchmark.FalseConsensus.governor_v2.replay_rules sweep \
  --protocol protocol_v2.json --rules generated/candidate_rules_v2.jsonl \
  --split-manifest generated/split_manifest.json \
  --results-root ../results/governor_v2 --phase development \
  --shard-index I --shard-count 10 --output shard_I.jsonl
python deer_threshold_sweep.py --output deer_sweep.jsonl   # from governor_v2/ (robust grader)
python select_v2.py --consensus shard_*.jsonl --deer deer_sweep.jsonl --output select.json
python confirm_v2.py "test_shard_*.jsonl" deer_sweep.jsonl # test + heldout
```
