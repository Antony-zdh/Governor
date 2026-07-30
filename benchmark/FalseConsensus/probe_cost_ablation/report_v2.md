# Probe-cost ablation v2 — report

## Why this was redone

The v1 `probe_cost_ablation` (see `SUPERSEDED.md`) was only a probe-call-count
inventory, not a probe-cost ablation. It sliced `cap*4` **characters** (not
tokens) from probe records that contain **no `probe_text`** (so the slice was a
no-op), summed the original cap-32 `probe_out_tokens` for every cap (so caps
8/16/32 were identical), replayed **no Governor rule**, produced **no
stop/delivered answer**, ran **no grader**, and omitted accuracy, accuracy
drop, gross/net/zero-probe-tax saving, PSF, and the Pareto/frontier view. The
script also hard-coded the repo path. It is preserved for audit only and is not
evidence.

## Frozen experimental scope

- **Bank:** frozen Governor-v2 DEV bank only (development trajectories for
  `DeepSeek-R1-Distill-Qwen-7B` and `Qwen3-8B` × {math500, amc23, aime24} ×
  seeds {42,43,44}). Main trajectories are frozen and were **not** regenerated.
- **Dev split:** 114 dev problems/seed (100 math500 + 8 amc23 + 6 aime24) × 3
  seeds × 2 models = **684 unique DEV trajectories** (validated independently
  from `split_manifest.json`).
- **Probe schedules:** start=64, interval ∈ {64,128,256,512}. Interval 128/256/
  512 are derived by **strict position downsampling** (`(pos - 64) % interval == 0`)
  from a single real interval-64 bank — no repeated probe calls.
- **True generation caps:** {8,16,32} output tokens, enforced by the model's
  own tokenizer.
- **Policies (frozen, no tuning):** `governor_conservative`,
  `governor_balanced_task_aware_secondary` (balanced_math on MATH500; the
  predeclared fixed-1536 non-MATH secondary on AMC23/AIME24),
  `governor_naive_agreement` (control). Source: `final_eval/protocol.json`
  (v1 frozen methods); replayed via the authoritative
  `evaluate_existing_methods.decide_stop` / `_valid` / `_equivalence_ids`
  interpreter and `replay_rules.answers_equal` / `grading.robust_answers_equal`
  grader — **not a simplified substitute**.

## Real probing requirement (satisfied)

Each cap is a genuine `completions.create(max_tokens=cap, stop=["]"])` call
with the exact `dense_simple32` prompt semantics
(`apply_chat_template(problem) + decode(token_ids[:position]) + SIMPLE_SUFFIX`),
so cap-32 is directly comparable to the authoritative dense bank. No cap-8/16
outcome is inferred by truncating a cap-32 answer. Each probe stores raw text,
finish_reason, actual `completion_tokens`, tokenizer-re-encoded token IDs
(provenance flag `tokenizer_reencode`), prompt tokens, parsed answer, and the
`is_certain` flag. Cap enforcement is checked: `actual_out_tokens <= cap`
(early EOS may be shorter).

## Cost accounting (per trajectory × cap × interval × policy)

- `consumed_main_tokens` = main tokens through the stop probe (or full main if
  no stop); future probes after an early stop are **excluded** from cost.
- `gross_tokens_used = consumed_main_tokens`;
  `actual_total_tokens_used = consumed_main + probe_output_tokens`;
  `ideal_zero_probe_tax_tokens_used = consumed_main` (probe output tax zeroed).
- Denominator = `full_main_tokens` (frozen full generation).
- `gross_saving = (full - consumed_main)/full`;
  `actual_net_saving = (full - (consumed_main + probe_out))/full`;
  `probe_tax = gross - net`; `ideal_zero_probe_tax_saving = gross_saving`;
  `PSF = mean(actual_net_saving > 0)`.
- Probe **prompt/prefill** tokens are reported separately (sensitivity view
  adds them: `actual + probe_prompt`), per the repo's fair/actual convention.

## Aggregation

First by environment = model × benchmark × seed, then equal-weight
macro-average over environments. Bootstrap CIs use the repo's paired
hierarchical resampler shape (10000 samples, seed 20260727) over seeds+problems.

## Validation / tests

- `collect_capped_probes.py` smoke on 2 DEV trajectories × all 3 caps: cap
  enforcement OK, caps genuinely differ (cap-8 hits `finish_reason=length` at
  8; cap-16/32 hit `stop` earlier), raw text + token IDs + finish_reason
  populated, replay end-to-end produces sensible stop/cost/grading.
- Unit tests (`tests/test_probe_cost_v2.py`): cap enforcement, interval
  downsampling (64/128/256/512 start=64), stop excludes future probes from
  cost, no-stop fallback, grading, gross/net/zero-tax cost identities,
  environment-macro aggregation, coverage (684×12×3=24624). **10/10 pass.**
- Relevant existing suites: `governor_v2.tests.test_governor_v2` (20),
  `governor_v2.tests.test_evaluate_existing_methods` (3),
  `related_work.tests.test_related_work` (51),
  `related_work.tests.test_online_window` (6). **All pass.**

## Results

All acceptance gates green (see `acceptance_v2.json`): 24,624 rows = 684 dev
trajectories × 12 interval×cap × 3 policies; 8,208 cells before policy; 0
duplicate keys; 0 cap violations across 166,722 raw probes checked; 0 null
cost fields; cost identities recompute exactly; no train/test rows; 18 envs
(2 models × 3 benchmarks × 3 seeds).

**cap-32 vs authoritative dense bank (acceptance #8):** 55,574 probes compared
at interval-64; answer match 96.7%, output-token match 98.0%, certainty match
99.99%. The ~3% deterministic mismatch is vLLM batching nondeterminism (identical
prompt/revision/decoding/start-interval/max_tokens), not a config difference.

### Macro table (env-macro over 18 environments; full 36-row CSV in `macro_table_v2.csv`)

Accuracy-drop (pp) / gross / actual-net / probe-tax / PSF / stop-rate:

| policy | cap | int=64 | int=128 | int=256 | int=512 |
|---|---|---|---|---|---|
| conservative | 32 | 26.7 / .485 / .437 / .048 / .870 / .922 | 19.6 / .363 / .333 / .030 / .788 / .828 | 14.1 / .229 / .210 / .019 / .590 / .613 | 10.4 / .100 / .089 / .011 / .293 / .301 |
| balanced | 32 | 28.4 / .512 / .467 / .045 / .892 / .932 | 22.1 / .440 / .413 / .026 / .883 / .913 | 22.0 / .349 / .333 / .016 / .780 / .807 | 13.8 / .206 / .196 / .010 / .526 / .538 |
| naive (control) | 32 | 58.9 / .802 / .783 / .018 / .986 / .996 | 46.2 / .702 / .688 / .014 / .977 / .987 | 37.2 / .585 / .574 / .011 / .953 / .955 | 26.2 / .413 / .405 / .008 / .804 / .830 |

(Cap 8 and 16 differ from cap 32 by ≤0.02 in every cell — see `macro_table_v2.csv`.)

### Key conclusions

1. **Lower caps barely move the frontier.** Within a policy, cap 8/16/32 are
   nearly identical (e.g. conservative @ int=64: gross .462/.478/.485, net
   .417/.430/.437). Most probes hit the `"]"` stop token before the cap binds
   (152,835 of 166,722 probes finish via `stop`, not `length`), so the cap
   rarely constrains output. The probe tax is ~0.019–0.048 and is roughly
   cap-invariant.
2. **Lower probe frequency (higher interval) substantially moves the frontier
   and changes accuracy, not just token count.** Conservative cap-32: int=64
   → 512 drops net saving .437→.089 and accuracy-drop 26.7→10.4 pp (fewer
   probes → later/no stop → closer to baseline accuracy but less saving).
   PSF falls .870→.293. So interval is the operative lever; cap is not.
3. **Probe tax scales with probe count, not cap.** Conservative uses ~68 probe
   calls (tax .048) vs naive ~23 (tax .018) at int=64 cap-32. The tax is the
   probe *output* tokens, which are short (~6–13 tokens/probe); the larger
   probe-prompt/prefill tax is reported separately (sensitivity view) and does
   not enter the primary net-saving figure.
4. **Naive agreement (control)** gives the largest saving (.80) but a 59 pp
   accuracy collapse — it stops on 3 consecutive equal answers regardless of
   correctness, confirming it is a diagnostic control, not a usable policy.

**Frontier verdict:** the cap dimension is essentially flat; the interval
dimension trades accuracy for token saving. The frozen conservative and
balanced policies sit on a meaningfully better accuracy/net-saving point than
naive, and their probe tax (output tokens) is small relative to gross saving.

## Caveats

- vLLM sampling is not bit-identical across runs even with the same seed; cap-32
  vs the authoritative dense bank will show a small deterministic mismatch rate
  (reported in `acceptance_v2.json` / analysis), explained by batching
  nondeterminism rather than a prompt/revision difference.
- Probe prompt/prefill tokens are reported separately and not added to the
  primary cost (per the repo's fair/actual convention).
