# GOAL: complete and push the DEER confidence-bank cap-30 experiment

You are the persistent experiment owner on **ugcpu2**. Work autonomously until
the experiment is complete, audited, committed, and pushed to GitHub. Do not
pause for routine choices or ask the user to relay commands. Use the safest
reasonable fallback when a transient runtime issue occurs, document it, and
continue.

## 0. Non-negotiable boundaries

1. Perform **all work inside** `/localdata/dzhaoah/Governor`. Do not clone,
   build, cache experiment outputs, or edit the repository under
   `/homes/dzhaoah`.
2. Preserve every unrelated tracked/untracked file and every foreign process.
   Never use `git reset --hard`, `git clean`, force-push, recursive deletion,
   or kill a process you did not start.
3. Inspect GPU ownership before launching. Use all eight healthy free 3090s if
   available; if fewer are healthy/free, use all safe GPUs and adapt the shard
   count without blocking. Never evict another user's process.
4. This task is **DEER only**. Do not run TJE, Governor sweeps, main generation,
   formal DEER readouts, or any 32B/Llama experiment.
5. The source main trajectories and faithful DEER results are immutable inputs.
   Write only under the new result root and its ignored runtime area.
6. Do not alter the scientific protocol to make a failure disappear. Retry
   transient request/server failures; code or data inconsistencies must be
   diagnosed and fixed with a small, tested change.

## 1. Scientific objective

Build a threshold-agnostic DEER confidence bank for the first **30**
case-insensitive whole-word `Wait` positions of every frozen trajectory:

- models:
  - `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`
    at revision `916b56a44061fd5cd7d6a8fb632557ed4f724f60`;
  - `Qwen/Qwen3-8B`
    at revision `b968826d9c46dd6066d109eabc6255188de91218`;
- benchmarks: `math500`, `amc23`, `aime24`;
- development/full seeds: `42,43,44`;
- confirmation/test seeds: `45,46,47`;
- total environments: `2 × 3 × 6 = 36`;
- total trajectories expected from committed inputs: `3420`;
- total cap-30 candidate trials expected from committed inputs: `45217`.

At every selected Wait, use the pinned DEER trial prompt, model-specific
confidence calculation, and 20-token trial cap. **Never stop early and never
generate a formal readout.** Compatible trials from the existing faithful
`threshold=0.95` DEER bank must be reused; only missing trials are generated.
Downstream threshold selection and answer grading will be performed later on
the Mac.

Authoritative protocol:

- `benchmark/FalseConsensus/related_work/DEER_CONFIDENCE_BANK_CAP30.md`
- `benchmark/FalseConsensus/related_work/configs/deer_confidence_bank_cap30.json`

## 2. Exact inputs and outputs

Inputs:

- main trajectories:
  `benchmark/FalseConsensus/results/governor_v2/{development,confirmation}__*/main`;
- reusable faithful trials:
  `benchmark/FalseConsensus/results/related_work/{full,test}/*/deer/trials`;
- split manifest:
  `benchmark/FalseConsensus/governor_v2/generated/split_manifest.json`.

Only formal output root:

```text
benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30/
  full/<model>__<benchmark>__seed_<seed>/
    bank_manifest.json
    trials.jsonl.gz
    trials/problem_*.json          # resumable runtime; gitignored
  test/<model>__<benchmark>__seed_<seed>/
    bank_manifest.json
    trials.jsonl.gz
    trials/problem_*.json          # resumable runtime; gitignored
  summary.json
  _runtime/                        # logs/status/server logs; gitignored
```

The 36 archives, 36 manifests, and `summary.json` are the GitHub deliverables.
Raw `trials/` files and `_runtime/` are not committed.

## 3. Repository and environment preflight

From `/localdata/dzhaoah/Governor`:

1. Capture `git status --short --branch`; do not discard anything.
2. Fetch origin, move safely to `main`, and fast-forward to the exact source
   commit supplied in the supervisor's tmux kickoff message (or a descendant).
   If unrelated tracked edits prevent switching, preserve them without staging
   them and continue only when the experiment code is the expected version.
3. Verify these modules import and compile:
   - `deer_confidence_bank.py`
   - `launch_deer_confidence_bank.py`
   - `audit_deer_confidence_bank.py`
4. Run:

```bash
python -m unittest \
  benchmark.FalseConsensus.related_work.tests.test_deer_confidence_bank -v
python -m unittest discover \
  -s benchmark/FalseConsensus/related_work/tests
```

Acceptance: the focused tests pass; the complete related-work suite has zero
failures (document any already-declared skips).

Use the existing `gov` environment when healthy:

```text
/localdata/dzhaoah/miniforge3/envs/gov/bin/python
HF_HOME=/localdata/dzhaoah/hf-cache
```

Confirm `vllm`, `torch`, `transformers`, and `openai` import. Install/repair only
inside this localdata environment if required. Do not modify a shared system
Python.

## 4. GPU and endpoint plan

Inspect all GPUs and active processes first. Preferred layout when all eight
GPUs are free and healthy:

| GPU | Model | Port | Shard |
|---:|---|---:|---:|
| 0 | DeepSeek-7B | 18100 | 0/4 |
| 1 | DeepSeek-7B | 18101 | 1/4 |
| 2 | DeepSeek-7B | 18102 | 2/4 |
| 3 | DeepSeek-7B | 18103 | 3/4 |
| 4 | Qwen3-8B | 18200 | 0/4 |
| 5 | Qwen3-8B | 18201 | 1/4 |
| 6 | Qwen3-8B | 18202 | 2/4 |
| 7 | Qwen3-8B | 18203 | 3/4 |

Run one independent BF16 vLLM endpoint per GPU, no tensor parallelism. Use the
pinned model revisions, `max-model-len=34816`, and a conservative memory
utilization that fits a 24 GB 3090. The served model name must equal the exact
model ID expected by the collector. Put PID files and logs under
`deer_confidence_bank_cap30/_runtime/servers/`.

Wait for every `/v1/models` endpoint to become healthy and verify its served
model before collection. If eight-way replication is impossible because of a
real resource constraint, choose `N` healthy endpoints per model, pass
`--num-shards N`, and cover every shard exactly once. Never silently omit jobs.

## 5. Mandatory smoke before the full run

Choose one DeepSeek and one Qwen trajectory with more than 10 Waits whose old
faithful DEER record contains fewer than the cap-30 target. Run the new
collector into `_runtime/smoke/`.

For each smoke result verify:

- schema is `related-work-deer-confidence-bank-problem-1`;
- `max_attempts == 30`;
- `formal_readout == false`;
- candidates are sequential and equal `min(number_of_Waits, 30)`;
- at least one old trial was reused and at least one missing trial was newly
  generated;
- every trial has logprobs and numeric confidence;
- no `readout` object exists;
- no request error is recorded.

Do not start the full run until both model smokes pass.

## 6. Full sharded collection

First run all shard commands with `--dry-run` and verify that their union is
exactly 18 jobs per model: both scopes × three benchmarks × three seeds, with no
duplicates.

Preferred four-shard commands:

```bash
PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python

$PY -m benchmark.FalseConsensus.related_work.launch_deer_confidence_bank \
  --model-key deepseek --endpoint http://127.0.0.1:18100/v1 \
  --shard-index 0 --num-shards 4 --workers 4
# repeat DeepSeek shard 1/2/3 at ports 18101/18102/18103

$PY -m benchmark.FalseConsensus.related_work.launch_deer_confidence_bank \
  --model-key qwen3 --endpoint http://127.0.0.1:18200/v1 \
  --shard-index 0 --num-shards 4 --workers 4
# repeat Qwen3 shard 1/2/3 at ports 18201/18202/18203
```

Run the eight shard launchers concurrently and monitor:

- endpoint health and GPU memory;
- `_runtime/<model>_shard_<n>/status.json`;
- shard logs for errors, context failures, empty logprobs, or repeated retries;
- output growth and completion manifests.

The collectors are resumable. On a transient endpoint/request failure, restore
that endpoint and rerun only the failed shard command. Do not restart completed
jobs. Keep going until all shard status files and all 36 manifests are complete.

## 7. Strict acceptance and packing

Run:

```bash
PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
ROOT=benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30

$PY -m benchmark.FalseConsensus.related_work.audit_deer_confidence_bank \
  --root "$ROOT" \
  --output "$ROOT/summary.json" \
  --expected-environments 36 \
  --pack
```

Acceptance is all-or-nothing:

- exactly 36 environments;
- exactly 3420 problem payloads;
- exactly 45217 cap-30 trials, unless a recomputation from the immutable main
  trajectories proves that committed input coverage changed;
- zero missing problems, duplicate problem IDs, trial errors, missing logprobs,
  malformed rows, or non-sequential candidate IDs;
- `reused_trial_count + generated_trial_count == trial_count`;
- no formal readout and no online early exit;
- 36 gzip archives, all passing decompression and matching recorded SHA-256;
- raw and validity-gated hit probabilities are monotone:
  `P10 <= P20 <= P30`;
- summary contains Wilson 95% intervals and the increments
  `P20-P10`, `P30-P20`.

Run the audit a second time with `--archives-only` and without `--pack` to prove
that committed archives are independently readable. Run `git diff --check` and
the focused tests again.

## 8. Commit and push

Before staging, update safely from `origin/main`. Never force-push. Stage only:

- the 36 `bank_manifest.json` files;
- the 36 `trials.jsonl.gz` archives;
- `deer_confidence_bank_cap30/summary.json`.

Explicitly print and inspect `git diff --cached --name-only`. It must not contain
raw `trials/`, `_runtime/`, model caches, unrelated experimental files, or any
pre-existing user work.

Commit message:

```text
results: add DEER confidence frontier cap-30 bank
```

Push directly to `origin/main`. If rejected because main advanced, fetch and
rebase safely, rerun the archive audit, and retry without force. Verify that
`origin/main` contains the result commit.

## 9. Final report to the supervisor

Report only after GitHub verification:

1. result commit SHA and verified remote branch;
2. healthy GPUs/endpoints and actual parallel layout;
3. wall time per model and total generated vs reused trial counts;
4. exact environment/problem/trial/archive counts and zero-error audit status;
5. raw and validity-gated `P10`, `P20`, `P30` for:
   - pooled all trajectories;
   - DeepSeek and Qwen separately;
   - full and test scopes separately;
6. `P20-P10` and `P30-P20` in percentage points;
7. output archive size and SHA audit status;
8. tests run and pass/skip counts;
9. any deviation or limitation.

Remain responsible for the task until the push and remote verification are
complete.
