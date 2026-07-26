# False Consensus experiments

Stage 1 (logging) and Stages 2-5 (analysis) from `plan.md`.

## Governor v2 · multi-environment rule development

The next protocol lives in [`governor_v2/`](governor_v2/README.md). It adds:

- deterministic problem-grouped 60/20/20 splits per sufficiently large
  benchmark, with small benchmarks reserved as external stress tests;
- probe-independent main trajectories followed by dense simple@32 re-probing;
- one uniform seven-dimension rule schema, including probe frequency;
- a parameterized model × benchmark × seed collection matrix;
- automatic one-at-a-time and full \(2^7\) selected-rule ablations.

The v2 collection and selection protocol is preregistered. Development uses
DeepSeek-R1-Distill-Qwen-7B and Qwen3-8B; Llama-8B and Distill-Qwen-32B are
held out for architecture/scale confirmation. Final rule IDs are frozen from
train/dev before any one-shot test or external-stress evaluation.

## Stage 1 · Logging mode

Governor does not control the model — no early stop, no upgrade. It only logs
every probe along one reasoning trajectory per problem.

```bash
# 1. serve the model (one A100 is enough)
vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
    --enable-prefix-caching --api-key token-abc123

# 2. log 100 MATH500 problems, budget 3072, probe every 128 tokens
python logging_run.py --dataset math500 --start 0 --end 100 \
    --budget 3072 --probe-interval 128 --output results/stage1_logging
```

Fixed settings (per plan.md): temperature 0.6, top_p 0.95, probe
`**Final Answer**\n\n\[ \boxed{` with 10 probe tokens, seed 42.

Output:
- `results/stage1_logging/probes.csv` — one row per probe
  (problem_id, dataset, token_position, probe_id, probe_answer, share,
  entropy, unique_answers, dominant_answer, is_certain, reasoning,
  final_answer, final_correct)
- `results/stage1_logging/traj/problem_<id>.json` — full trajectory text

`share`/`entropy` are computed cumulatively over all probes so far, with
math-equivalence grouping (`math_equal`). The run is resumable: already-logged
problems (existing traj file) are skipped.

## Stages 2-5 · Analysis

```bash
python analyze.py --input results/stage1_logging
```

Produces in `<input>/analysis/`: Figure 1 (calibration curve), Figure 2
(agreement histogram), false-consensus case export (share=1 AND wrong),
Figure 4 (consensus time), Figure 5 (consensus reliability + CCE), and
`report.md` with all headline numbers.

Two agreement definitions are reported side by side:
- **cumulative share** — over all probes of the trajectory (plan.md's
  definition; probe 1 alone is trivially share=1, so it only becomes
  meaningful late in the trajectory);
- **window share** — over the non-empty answers in the last 5 probes
  (what a Governor actually sees when deciding to stop). The analysis also
  simulates Dynasor-style early stopping (stop when the last 3 probes agree,
  are certain, and non-empty) to price the cost of false consensus.

Correctness is re-evaluated in `analyze.py` from the raw dataset answers
(`strip_string` erases some references, e.g. `\text{east}` -> `""`).

## Stage 3 · Classification

```bash
python classify_cases.py results/stage1_logging/analysis
```

`classify_cases.py` holds the per-case Type A-E assignment (edit the
`CLASSIFICATION` dict after manual review) and renders the Figure 3 pie.
