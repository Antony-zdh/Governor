# Stage 7 — Stop-rule Pareto Sweep report

- grid size: **142** configs (representative subset per plan.md §5.2 family, not full cross product; families: vanilla, hard_cap, consecutive, window_share [incl. history-aware + validity-filter variants], entropy, production_bug)
- vanilla (full generation) accuracy: **81.2%**

## Sanity check

`consec_p3_mt0_cert1` (3-consecutive, certain, min_tokens=0, validity=nonempty_only) reproduces the existing Dynasor-style simulation from `analyze.py`'s report.md:

- triggered: 416/500 (existing report: 416/500)
- stop-answer accuracy: 69.2% (existing report: 69.2%)
- avg main tokens: 1175


## Data limitation

`logging_run.py` never recorded per-request latency, so `wall_clock` / `prefill_cost_estimate` (plan.md §5.5) are not available. Only token-based costs (`avg_main_tokens`, `avg_probe_output_tokens`, `avg_total_generated_tokens`) are reported below.

## Selected operating points (plan.md §5.7)

### Conservative (accuracy drop ≤1pp)

- `consec_p8_mt1024_cert1` — 8-consecutive, min_tok=1024, certain=True
- accuracy: 81.0% (vanilla 81.2%, drop +0.2%)
- avg total generated tokens: 2085 (main 1935 + probe 150)
- stop coverage: 47.8%, false-stop rate: 7.1%
- correct→wrong truncation: 0, wrong→correct recovery truncated: 3, overthinking avoided: 177

### Balanced (accuracy drop ≤3pp)

- `consec_p6_mt1024_cert0` — 6-consecutive, min_tok=1024, certain=False
- accuracy: 78.8% (vanilla 81.2%, drop +2.4%)
- avg total generated tokens: 1793 (main 1664 + probe 129)
- stop coverage: 66.6%, false-stop rate: 15.0%
- correct→wrong truncation: 1, wrong→correct recovery truncated: 14, overthinking avoided: 240

### Aggressive (max token saving)

- `entropy_below_0.5_mt0` — entropy<=0.5, min_tok=0
- accuracy: 25.0% (vanilla 81.2%, drop +56.2%)
- avg total generated tokens: 138 (main 128 + probe 10)
- stop coverage: 100.0%, false-stop rate: 75.0%
- correct→wrong truncation: 0, wrong→correct recovery truncated: 286, overthinking avoided: 120

**Caveat**: plan.md §5.7 defines Aggressive as literally "max token saving" with no
accuracy floor, and the swept grid's true minimum is this near-immediate-stop
entropy rule — but at 25% accuracy (worse than random-ish guessing on MATH500)
this is not a usable Governor++ prototype, just the literal optimum of an
unconstrained objective. Re-running the same token-minimizing search with a
50%-accuracy floor instead lands on `window_w8_s0.6_mv3_mt0` (window=8,
share>=0.6, min_valid=3, min_tok=0): accuracy 53.2% (drop 28.0pp), avg total
generated tokens 882 (main 818 + probe 64), stop coverage 92.0%, false-stop
rate 47.6%, wrong→correct recovery truncated 145. Still a steep accuracy cost
— the real finding here is that this grid's Pareto frontier has **no config
that saves the majority of tokens while keeping accuracy above ~50%**; the
frontier drops off a cliff between the Balanced point (78.8% acc, 1793 tok)
and everything more aggressive than it. That cliff is itself evidence against
naive stop rules for an aggressive operating point — a smarter rule (e.g.
validity-filtered or difficulty-aware, Stage 8/9) would be needed to push the
frontier out here, not just a different threshold on the same signal.

## Production bug baseline

Reproducing the actual pre-fix `should_early_exit` behavior (log.md 2026-07-23): accuracy 27.8%, stop coverage 99.8%, false-stop rate 72.3% — quantifies how much worse the real deployed rule was vs. the documented 3-consecutive-consistent design intent.

Full grid: see `sweep_results.csv`. Figures: figureA/B/C `.png` in this directory.