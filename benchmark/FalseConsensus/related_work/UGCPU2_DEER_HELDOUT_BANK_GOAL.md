# GOAL: DEER confidence bank for the HELD-OUT models (32B + Llama-8B), then push

You are the persistent experiment owner on **ugcpu2** (8× RTX 3090). Work
autonomously until the experiment is complete, audited, committed, and pushed to
GitHub. Do not pause for routine choices. On a transient runtime issue, use the
safest reasonable fallback, document it, and continue.

This extends the existing dev-model DEER confidence bank
(`deer_confidence_bank_cap30`, DeepSeek-7B + Qwen3-8B) to the two **held-out**
models so the DEER frontier can be evaluated on unseen scale and architecture,
matching the consensus sweep that already covers them.

## 0. Non-negotiable boundaries

1. Do **all** work inside `/localdata/dzhaoah/Governor`. Never touch the repo
   under `/homes/dzhaoah`.
2. Preserve every unrelated tracked/untracked file and every foreign process.
   Never use `git reset --hard`, `git clean`, force-push, recursive deletion, or
   kill a process/GPU you did not start. Inspect `nvidia-smi` for ownership
   before launching; use only free, healthy 3090s and adapt shard/TP counts to
   what is free without evicting anyone.
3. This task is **DEER confidence-bank collection only**, for the **held-out
   models only**. Do not run TJE, consensus/Governor sweeps, main generation,
   formal DEER readouts, or touch the dev-model bank.
4. The source main trajectories are immutable inputs. Write only under the new
   result root and its ignored runtime area.
5. Do not alter the scientific protocol to make a failure disappear. Retry
   transient server/request failures; fix genuine code/data problems with a
   small, tested change and document it.

## 1. Scientific objective

Build a **threshold-agnostic, cap-30 direct-submit DEER confidence bank** for the
first **30** case-insensitive whole-word `Wait` positions of every frozen
held-out trajectory. Identical protocol to `DEER_CONFIDENCE_BANK_CAP30.md`
(pinned trial prompt, model-specific confidence, 20-token trial cap, **never stop
early, never generate a formal readout**). Threshold selection and grading happen
later on the Mac.

- Models (both are DeepSeek-R1 distills → base DEER policy `avg1`,
  `require_think_close=False`; verify via `deer.policy_for_model`):
  - `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` (held-out **scale**);
  - `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` (held-out **architecture/family**).
  - `--model-revision` is unpinned for these (`None`/`main`); pass `main` or omit.
- Benchmarks: `math500`, `amc23`, `aime24`.
- Scope: **test only**, confirmation seeds `45, 46, 47`.
- Environments: `2 × 3 × 3 = 18`.
- Expected trajectories from committed inputs: **684**.
- Expected cap-30 candidate trials (all newly generated — **no faithful DEER bank
  exists for these models, so there is nothing to reuse**): **≈ 6,485**
  (verify against the realized count; small deviations are fine).

## 2. Inputs and outputs

Inputs (already committed on `main` — pull first):
- Main trajectories:
  `benchmark/FalseConsensus/results/governor_v2/confirmation__<slug>__<benchmark>__seed_<45|46|47>/main/`
  where `<slug>` is `deepseek-ai-deepseek-r1-distill-qwen-32b` or
  `deepseek-ai-deepseek-r1-distill-llama-8b`.
- Split manifest:
  `benchmark/FalseConsensus/governor_v2/generated/split_manifest.json`.

Output — a NEW bank root (do not write into the dev bank):
- `benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30_heldout/`
  with a `test/` scope and one env dir per environment named
  `qwen32b__<benchmark>__seed_<seed>` and `llama8b__<benchmark>__seed_<seed>`
  (keep this key convention consistent so the Mac-side reader can map them),
  each containing `bank_manifest.json` and `trials.jsonl.gz` (pack raw
  per-problem trials into the archive as the dev bank does).
- A `summary.json` + `report.md` at the bank root (env list, trajectory/trial
  counts, invalid-trial-answer count), mirroring the dev bank's audit output.
- Resumable per-problem runtime files and any endpoint/shard logs go under an
  ignored `_runtime/` and `**/trials/` area (see the dev bank's `.gitignore`
  patterns) — commit the packed archives + manifests, not the runtime.

## 3. Model serving (you start and own these servers)

Serve with vLLM OpenAI-compatible endpoints, **prefix caching on**, bf16,
`--max-model-len 34816` (covers the AIME24 32K budget + trial), temperature 0.
The collector never starts servers; it only sends requests to the endpoint URL
you pass.

Recommended two-phase layout (uses all 8 GPUs each phase, simplest to reason
about; the 32B is the bottleneck):

- **Phase A — 32B (bottleneck).** Two tensor-parallel-4 servers, one on GPUs
  0–3 and one on GPUs 4–7 (32B bf16 ≈ 65 GB needs TP≥4 on 24 GB cards):
  ```
  CUDA_VISIBLE_DEVICES=0,1,2,3 vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
    --tensor-parallel-size 4 --enable-prefix-caching --dtype bfloat16 \
    --max-model-len 34816 --gpu-memory-utilization 0.92 --port 18010
  CUDA_VISIBLE_DEVICES=4,5,6,7 vllm serve ... --port 18011
  ```
  Split the 9 × 32B envs across the two endpoints. If a 34K context OOMs on
  32B/TP=4, lower `--max-model-len` toward the longest actual prefix and/or
  reduce collector `--workers`; do not drop trajectories.
- **Phase B — Llama-8B (fast).** After 32B finishes, tear those down and serve
  eight TP=1 Llama-8B endpoints (one per GPU, ports 18020–18027) and spread the
  9 × Llama envs across them. Llama-8B fits comfortably on one 3090.

(If you prefer to run both models concurrently instead: 32B TP=4 on GPUs 0–3 +
four TP=1 Llama on GPUs 4–7 — also fine; 32B remains the long pole.)

## 4. Collection — run the collector directly (bypass the launcher's reuse gate)

`launch_deer_confidence_bank.py` hard-requires a faithful-DEER `reuse_dir`, which
does **not** exist for these models. Do **not** try to satisfy it. Instead invoke
the collector directly per environment with **no** `--reuse-dir` (the collector
already treats reuse as optional: `reuse_dir=None` ⇒ generate all trials). This
needs **no `model_map.py` change**, since the collector takes `--model` directly.

Per environment:
```
python -m benchmark.FalseConsensus.related_work.deer_confidence_bank \
  --main-run   benchmark/FalseConsensus/results/governor_v2/confirmation__<slug>__<benchmark>__seed_<seed>/main \
  --output     benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30_heldout/test/<key>__<benchmark>__seed_<seed> \
  --url        <endpoint for that model> \
  --model      <model_id> --model-revision main \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
  --workers 6 --max-attempts 30
```
Drive the 18 envs with a small parallel driver (e.g. a shard-per-endpoint loop
modeled on `launch_deer_confidence_bank.py`, but constructing jobs without the
reuse requirement). You MAY instead add a tested `--no-reuse` flag to the
launcher that skips the `reuse_dir` existence check and passes `--reuse-dir`
through as empty — if you do, keep the change minimal and note it.

Confirm before the full run, on one small env (e.g. `llama8b__aime24__seed_45`,
6 problems): the collector reports `reuse_dir: null`, all trials
`record_source` are freshly generated, `policy == avg1`, `formal_readout ==
false`, `max_attempts == 30`, and `direct_submit_analysis == true`.

## 5. Audit + pack

After all 18 envs complete:
1. Pack each env's raw `trials/` into `trials.jsonl.gz` (as the dev bank does).
2. Run/adapt `audit_deer_confidence_bank.py` against the new root with
   `--expected-environments 18`; it must pass (per-problem schema, method, cap,
   no formal readout, sequential candidate ids, reuse/generated accounting).
3. Write `summary.json` + `report.md` (18 envs, 684 trajectories, realized trial
   count, invalid-trial-answer count).

## 6. Commit + push (required)

1. `git pull --ff-only` first; you are collaborating with a Mac-side branch.
   If `main` has advanced, rebase/merge cleanly without discarding others' work.
2. Commit only: the new bank archives + manifests + summary/report, the
   `.gitignore` additions for its runtime, and any minimal tested code change you
   made (with a one-line rationale). Do **not** commit `_runtime/`, per-problem
   `trials/`, or server logs.
3. Message: `data: DEER confidence bank cap-30 for held-out 32B + Llama-8B (test seeds 45/46/47)`.
4. `git push` to `origin`. Confirm the push succeeded and report the commit SHA.

## 7. Time budget and fallback

Expect **~1–3 h** of active 32B compute (the bottleneck) and **<30 min** for
Llama, plus server load/startup, audit, and push — **budget a ~6 h window**. If a
32B server is unstable on TP=4, fall back to TP=8 (single instance across all 8
GPUs) and run 32B envs serially, then Llama; document the change. If fewer than 8
GPUs are free, use what is free and reduce parallelism — never evict another
user. If you cannot finish within the window, commit and push whatever
environments completed (the bank is per-env resumable) and report exactly which
of the 18 remain.

## 8. Definition of done

- All 18 held-out env dirs exist with packed `trials.jsonl.gz` + `bank_manifest.json`.
- Audit passes at `--expected-environments 18`; `summary.json` + `report.md` written.
- New bank committed and **pushed to GitHub**; commit SHA reported.
- No unrelated file or foreign process disturbed; runtime artifacts left ignored.
- A short final report: realized trajectory/trial counts, any fallbacks taken,
  and the pushed SHA.
