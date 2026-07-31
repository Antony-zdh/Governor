# GOAL: complete and push the TJE top-1..top-6 threshold frontier bank

Work autonomously until the complete experiment is audited, packed, committed,
pushed, and verified on GitHub. Do not stop merely to report progress and do
not ask the user routine questions. Diagnose and recover from ordinary vLLM,
environment, endpoint, retry, disk, and resumability problems yourself.

## Hard boundaries

1. Perform **all work only in `/localdata/dzhaoah/Governor`**. Never use the
   `/homes/dzhaoah/Governor` checkout.
2. Preserve all unrelated work, especially the existing untracked corrected
   Llama directories. Never stage, delete, move, or modify them.
3. Never rewrite or delete the immutable faithful TJE inputs under
   `results/related_work/{full,test}/*/tje`.
4. This task generates **readouts only**. It must issue zero new TJE confidence
   queries and zero main-trajectory generations.
5. Do not run DEER, Governor sweeps, CertaIndex, 32B, or Llama experiments.
6. Do not force-push. Push only a normal fast-forward commit to `origin/main`.

## Scientific objective

Build a discrete TJE threshold frontier over the highest 1–6 official
confidence classes:

- top-1: `Almost certain` (faithful TJE threshold);
- top-2: `Highly likely`;
- top-3: `Very good chance`;
- top-4: `Likely`;
- top-5: `Better than even`;
- top-6: `Less than even`.

For each threshold, stop at the first stored confidence label at or above that
level. Reuse the faithful confidence records. Reuse the faithful top-1 readout
when its trigger matches; otherwise generate the missing final readout at each
distinct first-crossing trigger exactly once.

TJE has **no artificial max-Wait cap**. The source primary policy covers every
whole-word `Wait` plus final `</think>`. Do not introduce a cap of 10, 20, 30,
or any other number.

Expected complete coverage:

- 36 environments;
- 3,420 trajectories;
- 4,366 new unique readouts before any context-budget outcomes:
  3,484 in full and 882 in test;
- models: DeepSeek-R1-Distill-Qwen-7B and Qwen3-8B;
- benchmarks: MATH500, AMC23, AIME24;
- full seeds 42/43/44 and test seeds 45/46/47.

Read and follow:

- `benchmark/FalseConsensus/related_work/TJE_THRESHOLD_READOUT_BANK_TOP1_6.md`
- `benchmark/FalseConsensus/related_work/configs/tje_threshold_readout_bank_top1_6.json`
- `benchmark/FalseConsensus/related_work/tje_threshold_readout_bank.py`
- `benchmark/FalseConsensus/related_work/launch_tje_threshold_readout_bank.py`
- `benchmark/FalseConsensus/related_work/audit_tje_threshold_readout_bank.py`

## Start state and update

```bash
cd /localdata/dzhaoah/Governor
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
```

Record the source commit. Do not clean the worktree and do not touch unrelated
untracked Llama results.

Use the existing Python environment:

```bash
PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
$PY -m unittest \
  benchmark.FalseConsensus.related_work.tests.test_tje_threshold_readout_bank -v
```

Also run dry-run discovery for every shard before starting GPU work:

```bash
for MODEL in deepseek qwen3; do
  for SHARD in 0 1 2 3; do
    LEN=34816
    [ "$MODEL" = qwen3 ] && LEN=33792
    $PY -m benchmark.FalseConsensus.related_work.launch_tje_threshold_readout_bank \
      --model-key "$MODEL" --endpoint http://127.0.0.1:1/v1 \
      --scope both --shard-index "$SHARD" --num-shards 4 \
      --workers 2 --max-model-len "$LEN" --dry-run
  done
done
```

Require exactly 18 jobs per model across the four shards and complete source
manifests for every job.

## GPU and serving layout

Use all eight GPUs, one independent BF16 vLLM endpoint per GPU:

- GPUs 0–3: DeepSeek, four endpoints, one shard per endpoint;
- GPUs 4–7: Qwen3, four endpoints, one shard per endpoint.

Reuse the environment repairs proven by the preceding DEER cap-30 run:

- `LD_LIBRARY_PATH` must include the gov environment `lib`;
- use the bundled CUDA toolkit required by the installed vLLM;
- set `VLLM_USE_FLASHINFER_SAMPLER=0`;
- use exact pinned model revisions and exact model IDs;
- no tensor parallel;
- `gpu-memory-utilization=0.90`;
- DeepSeek `max-model-len=34816`;
- Qwen3 `max-model-len=33792`;
- never reduce the scientific context window silently.

Use new ports that do not collide with stale panes, for example:

- DeepSeek: 18300, 18301, 18302, 18303;
- Qwen3: 18400, 18401, 18402, 18403.

Before collection, verify each endpoint with `/v1/models` and confirm the
reported model ID is exact. Confirm all eight GPUs hold only the intended
servers.

## Mandatory smoke

Run one DeepSeek and one Qwen smoke before the full shards:

- DeepSeek full/math500/seed42/problem404;
- Qwen3 full/math500/seed42/problem280.

Each was selected because it requires at least two distinct new readouts.
Run the collector directly with `--problem-id`, inspect every produced
decision and readout, then remove only the smoke output directory (not any
source data) or reuse it only if the full output path and manifest settings
match exactly.

Smoke acceptance:

1. `confidence_queries_generated == 0`;
2. top-1..top-6 threshold labels are exact;
3. stop trigger IDs are monotone non-increasing as top-k becomes more
   permissive;
4. every unique stop trigger has exactly one readout;
5. the readout prompt contains the actual stored
   `\confidence{<label>}` event, `</think>`, and final-response boundary;
6. no request error, null finish reason, context overflow, identity mismatch,
   or malformed record;
7. `reused + generated == unique readouts`;
8. invalid/truncated readout with a genuine `finish_reason=length` is a method
   outcome, not a collector failure.

If smoke fails, fix the implementation, add a regression test, push the code
fix, and rerun smoke. Do not proceed with a scientifically ambiguous shortcut.

## Full collection

After smoke passes, launch eight concurrent durable shards. For each model and
shard use its matching endpoint:

```bash
$PY -m benchmark.FalseConsensus.related_work.launch_tje_threshold_readout_bank \
  --model-key <deepseek|qwen3> \
  --endpoint http://127.0.0.1:<port>/v1 \
  --scope both --shard-index <0..3> --num-shards 4 \
  --workers 2 --max-model-len <34816|33792>
```

Run shards in named tmux windows and keep logs under the result `_runtime`
directory. Monitor every shard. A failed job must be diagnosed and resumed;
completed problem payloads are restartable and must not be regenerated.

Do not count an invalid mathematical readout as infrastructure failure.
Do count request exceptions, missing source records, identity mismatch,
malformed decisions, context overflow, or nonzero confidence-query generation
as hard failures.

## Audit and packing

After every shard completes:

```bash
ROOT=benchmark/FalseConsensus/results/related_work/tje_threshold_readout_bank_top1_6

$PY -m benchmark.FalseConsensus.related_work.audit_tje_threshold_readout_bank \
  --root "$ROOT" --output "$ROOT/summary.json" --pack

$PY -m benchmark.FalseConsensus.related_work.audit_tje_threshold_readout_bank \
  --root "$ROOT" --output "$ROOT/archive_audit.json" --archives-only
```

Both commands must exit zero. Require:

- 36/36 environments and 3,420/3,420 trajectories;
- archive SHA-256 matches;
- zero recorded request errors;
- zero newly generated confidence queries;
- all six policies present per trajectory;
- monotone first-crossing trigger IDs;
- exact one-readout coverage for every unique stop trigger;
- generated/reused counts sum exactly;
- all deterministic gzip archives readable without raw files.

Run:

```bash
$PY -m unittest \
  benchmark.FalseConsensus.related_work.tests.test_tje_threshold_readout_bank -v
$PY -m unittest discover \
  -s benchmark/FalseConsensus/related_work/tests -p 'test_*.py'
git diff --check
```

## Commit and push

The raw per-problem `readouts/`, empty `triggers/`, and `_runtime/` paths are
gitignored. Commit only:

- 36 `bank_manifest.json` files;
- 36 deterministic `readouts.jsonl.gz` archives;
- `summary.json` and `archive_audit.json`;
- any necessary tested code fix directly related to this experiment.

Never stage unrelated untracked Llama directories or other user work.

Suggested message:

```text
results: add TJE top-1 to top-6 threshold readout bank
```

Before pushing, inspect `git status --short` and `git diff --cached --stat`.
Push normally to `origin/main`, then verify the commit is contained by
`origin/main`.

## Final report

Return only after push verification. Report:

1. result commit SHA and remote branch;
2. exact environment/trajectory/readout counts;
3. generated versus reused readouts;
4. invalid/truncated/context-budget outcome counts;
5. confirmation that zero confidence queries were generated;
6. wall time and per-model timing;
7. serving layout and any non-scientific environment workarounds;
8. smoke and full test/audit results;
9. archive size and SHA verification;
10. any deviations or remaining limitations.
