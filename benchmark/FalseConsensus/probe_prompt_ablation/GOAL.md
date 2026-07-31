# GOAL: Complete the matched Simple@32 vs CertaIndex@32 prompt-timing ablation

You are the persistent execution agent on `ugcpu2`. Own this experiment from
preflight through validated artifacts and a pushed commit. Do not stop merely
after launching jobs. Monitor, resume, diagnose, aggregate, test, and report
until every acceptance condition below is satisfied or a genuinely external
blocker remains.

## 1. Mandatory workspace and safety boundary

- Perform every repository action under `/localdata/dzhaoah/Governor`.
- The machine is shared. Never kill, reset, or attach to another user's
  processes. Resolve free GPUs with `nvidia-smi` before serving.
- GPUs 0 and 1 have historically been unreliable. Do not assume any numeric
  index is usable; inspect current state and select GPUs with no material
  foreign compute process.
- The duplicate Llama collection was intentionally stopped. Do not resume any
  Llama collector or Llama vLLM server.
- Preserve all partial Llama files and logs. In particular, do not delete,
  stage, commit, or push untracked/modified artifacts under
  `benchmark/FalseConsensus/results/governor_v2_scale_dev_llama_corrected/`,
  `.runlogs/llama_*`, or unrelated local edits.
- Do not regenerate any frozen main trajectory or existing Simple@32 bank.
- Do not reset, checkout away, clean, force-push, or broadly stage the dirty
  worktree. Use explicit `git add <exact paths>` only.

## 2. Scientific objective

Test whether the CertaIndex probe prompt improves the accuracy-output-token
trade-off by delaying the first answer consensus relative to Simple@32.

This is a prompt-timing experiment, not a comparison of two different stopping
rules:

- both arms use the same frozen main trajectory;
- both probe every 64 main tokens starting at token 64;
- both use `max_tokens=32`, the same temperature/top-p/seed inherited from the
  frozen main run, and stop sequence `\\]`;
- both stop on the first window of three consecutive probes whose answers are
  non-empty, mathematically equivalent, and certain under the same uncertainty
  predicate;
- only the probe suffix differs: existing Governor Simple suffix versus the
  faithful CertaIndex suffix.

The CertaIndex collector may stop issuing future probes once its first eligible
three-probe consensus is observed. This is an online cost optimization and
preserves the primary first-consensus estimand.

## 3. Frozen scope

Use every available trajectory; do not select or report by split:

- models:
  - `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`
  - `Qwen/Qwen3-8B`
- benchmarks: `math500`, `amc23`, `aime24`
- development namespaces: seeds 42, 43, 44;
- confirmation namespaces: seeds 45, 46, 47;
- total paired problem-seed trajectories per arm: exactly 3,420;
- partial environment directories: exactly 36 per arm
  (`2 models x 3 benchmarks x 6 phase-specific seeds`).

The different seed sets reflect the already collected train/dev and test banks.
Every benchmark problem still has three sampled trajectories. The final report
must pool all 3,420 rows and must not include train/dev/test result tables.
Model/benchmark/seed identities remain available only for pairing and
equal-environment macro robustness.

## 4. Required implementation

The intended preparation lives under:

`benchmark/FalseConsensus/probe_prompt_ablation/`

Required files:

- `protocol.json`
- `run_certaindex32.py`
- `acceptance.py`
- `analyze_prompt_timing.py`
- `tests/test_prompt_timing.py`
- this GOAL

The existing collector is:

`benchmark/FalseConsensus/related_work/certaindex_mid.py`

It must support confirmation banks by inferring
`expected_problem_count` from the selected frozen main trajectory directory,
not from the old development-only 400/32/24 constants. Preserve the old
development behavior and all existing CertaIndex semantics.

If these prepared files are not present in the current branch, implement them
exactly from this GOAL before using GPUs. Do not weaken the scope or acceptance
conditions. Run:

```bash
python -m json.tool \
  benchmark/FalseConsensus/probe_prompt_ablation/protocol.json >/dev/null

python -m unittest \
  benchmark.FalseConsensus.related_work.tests.test_related_work \
  benchmark.FalseConsensus.related_work.tests.test_online_window \
  benchmark.FalseConsensus.related_work.tests.test_false_stop_analysis \
  benchmark.FalseConsensus.probe_prompt_ablation.tests.test_prompt_timing

python -m benchmark.FalseConsensus.probe_prompt_ablation.run_certaindex32 \
  --model deepseek --check-inputs

python -m benchmark.FalseConsensus.probe_prompt_ablation.run_certaindex32 \
  --model qwen3 --check-inputs
```

The two preflights must each report 18 environments and 1,710 complete
main/Simple inputs.

## 5. Runtime environment and model servers

Reuse an existing compatible environment if it passes imports. Otherwise create
or repair a project-local/user-local environment without modifying system Python.
At minimum the collector needs the repository dependencies, OpenAI client,
Transformers/tokenizer stack, Dynasor evaluator dependencies, and vLLM.

The model weights were previously available on this machine, but do not assume
cache paths. Inspect existing Hugging Face caches first. Download only missing
files and pin the revisions recorded in `protocol.json`.

Start one BF16 vLLM server per model on two actually free 3090s:

- DeepSeek-7B endpoint: `http://127.0.0.1:18000/v1`
- Qwen3-8B endpoint: `http://127.0.0.1:18001/v1`

A 7B/8B model should use one 3090 each. Do not tensor-parallelize across shared
GPUs unless a single-GPU smoke proves impossible. Choose safe
`--gpu-memory-utilization` and `--max-model-len` values that fit the frozen
prefixes; do not cause OOMs that affect other users.

Before collection, verify:

1. both ports belong to your two intended vLLM processes;
2. `/v1/models` returns the expected served model;
3. tokenizer/model revision and chat template match the frozen manifests;
4. a two-problem CertaIndex@32 smoke per model produces non-empty probe records,
   `probe_out_tokens <= 32`, parseable answers when the model answers, and no
   request/context errors;
5. the smoke writes to a dedicated `_smoke` directory outside the formal
   output and cannot be counted by acceptance.

## 6. Formal collection

Formal output root:

`benchmark/FalseConsensus/results/probe_prompt_ablation/certaindex32/`

Run the two model launchers concurrently, each against its own endpoint:

```bash
python -m benchmark.FalseConsensus.probe_prompt_ablation.run_certaindex32 \
  --model deepseek --workers 16

python -m benchmark.FalseConsensus.probe_prompt_ablation.run_certaindex32 \
  --model qwen3 --workers 16
```

Use tmux windows or durable log files so both pipelines survive disconnects.
The collectors are restartable and must skip only records whose identity and
manifest settings match. Do not overwrite a different-cap or different-prompt
bank.

Monitor:

- completed problem counts per environment;
- request/retry/error counts;
- endpoint health and GPU memory;
- context-length errors;
- cap violations;
- ETA from actual throughput.

Expected total runtime with two models in parallel is roughly 2-3 hours,
conservatively under 4 hours. If progress projects beyond 6 hours, diagnose
throughput, unexpected no-consensus trajectories, model serving, and worker
concurrency instead of silently waiting.

## 7. Strict acceptance and CPU analysis

After both collectors finish, stop only the two vLLM servers you started.
Do not stop foreign processes.

Run:

```bash
python -m benchmark.FalseConsensus.probe_prompt_ablation.acceptance \
  --output \
  benchmark/FalseConsensus/results/probe_prompt_ablation/analysis/acceptance.json

python -m benchmark.FalseConsensus.probe_prompt_ablation.analyze_prompt_timing
```

Acceptance must show:

- 36 complete CertaIndex partial-environment directories;
- 3,420 frozen main trajectories;
- 3,420 existing Simple trajectories;
- 3,420 CertaIndex@32 trajectories;
- zero duplicate paired identities;
- zero corrupt/request-error rows;
- zero `probe_out_tokens > 32`;
- settings exactly cap 32, interval 64, start 64, patience 3;
- all 3,420 Simple/CertaIndex pairs replayed.

Required analysis artifacts:

- `analysis/acceptance.json`
- `analysis/per_problem.csv`
- `analysis/summary.json`
- `analysis/report.md`

The report must give both problem-pooled and equal-environment-macro summaries,
but no split-specific table. It must include:

- first-consensus position and stop rate;
- delivered accuracy and delta versus frozen full generation;
- main-only and all-generated output-token saving;
- consumed probe-output tax;
- wrong among actual stops;
- Harm, Rescue, and Harm/Rescue;
- CertaIndex later/earlier/same counts when both stop;
- Simple-only, CertaIndex-only, and neither-stop counts;
- mean/median CertaIndex consensus delay;
- Simple harms protected by CertaIndex;
- new harms introduced by CertaIndex;
- CertaIndex-corrects-Simple and CertaIndex-breaks-Simple paired counts.

Primary token accounting is generated output tokens:
`main tokens through stop + consumed probe output tokens`.
Report prompt/prefill tokens and wall time separately; never call the primary
number total GPU compute or latency.

## 8. Final tests and artifact integrity

Run at least:

```bash
python -m unittest \
  benchmark.FalseConsensus.probe_prompt_ablation.tests.test_prompt_timing \
  benchmark.FalseConsensus.related_work.tests.test_false_stop_analysis \
  benchmark.FalseConsensus.related_work.tests.test_related_work \
  benchmark.FalseConsensus.related_work.tests.test_online_window

git diff --check
```

Also verify JSON/CSV parseability, exact row counts, manifest hashes, and that
formal raw probe files are not Git LFS pointer stubs.

## 9. Commit and push without touching Llama residue

Create a dedicated branch if needed. Stage only:

- `benchmark/FalseConsensus/probe_prompt_ablation/`
- the minimal confirmation-count compatibility edit in
  `benchmark/FalseConsensus/related_work/certaindex_mid.py`
- `benchmark/FalseConsensus/results/probe_prompt_ablation/`
- any narrowly scoped tests required by this experiment.

Do not use `git add -A` or `git add .`. Before committing, print the staged file
list and prove no partial Llama artifact or unrelated edit is staged.

Commit with a descriptive message, push the branch to origin, and record the
commit SHA. Do not merge to main and do not force-push.

## 10. Final response

Return a concise but complete final report containing:

1. commit SHA and pushed branch;
2. exact coverage and acceptance status;
3. model/server/GPU configuration actually used;
4. wall-clock time and auxiliary call count;
5. the Simple and CertaIndex accuracy-saving-stop points;
6. consensus-delay and Harm/Rescue findings;
7. all test results;
8. limitations or deviations;
9. exact artifact paths.

Do not ask the user routine questions. Resolve recoverable environment,
dependency, endpoint, resume, and aggregation issues yourself. Ask only if the
required model weights are inaccessible, no usable GPU exists, or proceeding
would require deleting/overwriting user data.
