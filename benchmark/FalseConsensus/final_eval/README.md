# Frozen final-evaluation protocol

This directory freezes the next-step evaluation before any new-seed result is
inspected. The machine-readable source of truth is `protocol.json`.

## What is frozen

The primary MATH500 comparison uses the complete 500-problem set, generation
seeds 43/44/45, temperature 0.6, top-p 0.95, a 3072-token reasoning budget,
and a simple 32-token forced-answer probe every 128 reasoning tokens.

The two Governor operating points are:

- **Conservative** — eight consecutive valid and certain equivalent answers,
  with no stop before 1024 reasoning tokens.
- **Balanced-MATH** — five consecutive valid and certain equivalent answers;
  the minimum is 768 tokens for MATH levels 1–3 and 2048 for levels 4–5.

Here, `schema` means that empty readouts and single-letter A/B/C/D artifacts
are invalid for free-response MATH. `certain` rejects probe text containing
the existing hesitation markers (`wait`, `hold`, `but`, `okay`, `no`, `hmm`).

Balanced-MATH is deliberately not transferred to datasets without MATH
levels. Conservative is the primary general rule. A fixed-1536, task-aware
Balanced candidate is predeclared only as a secondary non-MATH analysis.

## One-shot boundary

Seeds 43/44/45 estimate stochastic generation variance, but they do not
constitute new examples. A genuinely untouched dataset is a separate test.
Neither source may be used for further tuning. If a new rule is proposed after
viewing these results, it must be marked post-hoc and evaluated on a newly
registered holdout.

## Logging commands

Run each model and seed into a separate directory:

```bash
python benchmark/FalseConsensus/logging_run.py \
  --dataset math500 --start 0 --end 500 \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  --budget 3072 --probe-interval 128 --probe-tokens 32 \
  --probe-suffix-style simple --temperature 0.6 --top-p 0.95 \
  --seed 43 --workers 12 \
  --output benchmark/FalseConsensus/results/final_eval/deepseek7b_math500/seed_43
```

Repeat with seeds 44 and 45, then with `Qwen/Qwen3-8B`. The runner is
resumable by trajectory file. New runs record main/probe decode tokens,
main/probe prompt tokens, per-request latency, and per-trajectory wall-clock.

## Cost interpretation

We report three nested cost views:

1. main reasoning decode tokens;
2. total generated tokens (main plus probe output);
3. measured wall-clock and prompt/prefill workload.

The third is the deployment-facing result. Prompt tokens are a workload proxy,
not automatically equal to uncached prefill compute; cache statistics and GPU
utilization must be captured from the serving process when available.

## Locked evaluation order

1. Run DeepSeek seeds 43–45.
2. Replay full, fixed-budget, naive, faithful/adapted CertaIndex, Conservative,
   and Balanced-MATH without parameter changes.
3. Run Qwen seeds 43–45 with the identical protocol.
4. Run the one-shot untouched dataset.
5. Only then aggregate multi-seed estimates and apply the submission gate.

