# DEER cap-30 confidence bank — held-out 32B + Llama-8B (test seeds 45/46/47)

Threshold-agnostic, cap-30 **direct-submit** DEER confidence bank over the frozen
Governor v2 confirmation trajectories for the two **held-out** models. Identical
protocol to the dev bank (`DEER_CONFIDENCE_BANK_CAP30.md`): pinned trial prompt,
model-specific confidence, 20-token trial cap, never stop early, never issue a
formal readout. Threshold selection and grading happen later on the Mac.

Because no faithful-DEER bank exists for these models, the collector was invoked
directly with **no `--reuse-dir`** — every trial is freshly generated
(`record_source == "new_cap30_probe"`, `reused_trial_count == 0`).

## Models

Both are DeepSeek-R1 distills → base DEER policy `avg1`,
`require_think_close=False` (verified via `deer.policy_for_model`). The revision
is unpinned in `model_map.py`; the collector requires a 40-hex SHA, so `main`
was resolved to its current commit at collection time (more reproducible than a
branch name):

| Key | Model id | Revision (40-hex, = `main`) |
|---|---|---|
| qwen32b | `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` | `711ad2ea6aa40cfca18895e8aca02ab92df1a746` |
| llama8b | `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` | `6a6f4aa4197940add57724a7707d069478df56b1` |

## Headline numbers (audit output)

| Metric | Value |
|---|---:|
| Environments | 18 (2 models × 3 benchmarks × 3 seeds) |
| Scope | `test` (confirmation seeds 45/46/47) |
| Trajectories | 684 (342 per model: math500=100, amc23=8, aime24=6 per env) |
| Cap-30 candidate trials | **5,324** (all generated; 0 reused) |
| Invalid trial answers (empty `trial_answer`) | 161 |
| Recorded failures | 0 |

Per-model / benchmark (trials):

| Model | aime24 | amc23 | math500 | total |
|---|---:|---:|---:|---:|
| qwen32b (32B) | 374 | 249 | 2,131 | 2,754 |
| llama8b (8B) | 300 | 186 | 2,084 | 2,570 |
| **total** | 674 | 435 | 4,215 | **5,324** |

## Held-out finding: the `Wait` trigger is seed/architecture-dependent

The DEER trigger is the first 30 case-insensitive whole-word `Wait` positions.
On the Llama-8B confirmation trajectories, **seed 45 has zero `Wait` tokens
across all three benchmarks** (→ 0 candidates, 0 trials, envs still complete with
empty per-problem payloads — the protocol is followed faithfully; the trigger
simply never fires). Seeds 46/47 produce `Wait` normally. The 32B Qwen-distill
produces `Wait` on all seeds. This is a genuine frozen-input characteristic, not a
protocol deviation: the source trajectories are immutable inputs and were not
altered. The realized trial count (5,324) therefore falls below the ≈6,485
pre-collection estimate (which assumed both models emit `Wait` like the dev
models); the shortfall is entirely the 0-trigger Llama seed-45 envs.

## Audit

`audit_deer_confidence_bank.py` passes at `--expected-environments 18`, both on
the resumable raw files (`--pack`) and on the committed archives
(`--archives-only`): per-problem schema, method, cap-30, no formal readout,
sequential candidate ids, non-empty logprob arrays, reuse/generated accounting
(0 reused + 5,324 generated == 5,324), 0 recorded failures. Committed data:
deterministic `trials.jsonl.gz` archives + `bank_manifest.json` per env, and the
global `summary.json`.

## Serving fallbacks (documented)

- **flashinfer JIT**: vLLM 0.26 JIT-compiles its sampling kernel; the host's
  default `nvcc` (CUDA 10.1) rejected `--generate-dependencies-with-compile`.
  Fixed by pointing `CUDA_HOME`/`PATH` at `/usr/local/cuda-13.0` (matches the
  torch cu130 build). No protocol change.
- **NCCL / TP>1**: this box's 3090s are PCIe-only (no NVLink); the default NCCL
  transport crashed TP=4 init. Fixed with
  `NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 NCCL_NET_PLUGIN=none VLLM_HOST_IP=127.0.0.1`.
- **32B OOM**: the 32B confirmation trajectories are capped at 16,384 tokens
  (not 32K), so `--max-model-len 34816` over-reserved KV cache and OOM'd the
  flashinfer sampler warmup. Lowered to `--max-model-len 20000` (covers the
  longest 32B prefix + trial with margin) at `--gpu-memory-utilization 0.90`.
  Llama-8B trajectories reach 32,768 tokens, so Llama servers used the full
  `--max-model-len 34816` (fits on one 24 GB GPU: 16 GB weights + ~4.5 GB KV).
- All servers: bf16, prefix caching on, temperature 0, OpenAI-compatible
  `/v1/completions`; the collector sends `logprobs=1` greedy trials with `seed=base_seed`.

Layout: `test/<key>__<benchmark>__seed_<seed>/{bank_manifest.json,trials.jsonl.gz}`;
per-problem raw `trials/` and `_runtime/` (driver, shard logs, server-launch
helper) are git-ignored resumable state.
