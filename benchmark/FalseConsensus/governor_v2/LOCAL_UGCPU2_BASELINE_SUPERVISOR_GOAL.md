# GOAL: Supervise ugcpu2 until all related-work baseline experiments are complete

You are the **local primary Codex agent**. Your responsibility is not merely
to send a task to another agent. You must connect to the persistent Codex
agent already running inside tmux on `ugcpu2`, give it a complete task,
inspect and steer its work, independently verify its artifacts, recover from
failures, and continue until the related-work baseline experiments are
genuinely complete and durable on GitHub.

Do not return after delegation. Do not treat “the remote agent says it is
done” as completion. Completion requires the evidence and acceptance checks
listed below.

## 0. Resume checkpoint — 2026-07-28

This section records the live state at the latest supervisor handoff and
overrides any older conflicting machine/path assumptions later in this file.
On resume, inspect the live tmux pane and filesystem before acting; PIDs and
progress counts below are observations, not identities to invent or reuse
blindly.

User-authorized resource boundary:

- remote host: `ugcpu2`;
- remote repository and **all experiment artifacts**:
  `/localdata/dzhaoah/Governor`;
- use **GPU 0 for DeepSeek and GPU 1 for Qwen3 only**, with full available
  VRAM and compute;
- GPUs 2–7 are occupied by another user and are strictly out of scope;
- never reset a GPU, kill an unrelated process, or broaden the GPU set.

Current Git/runtime state:

- tmux agent target: `0:0.0`;
- branch: `related-work-baselines-ugcpu2-20260727`;
- branch base/HEAD before the first durable related-work commit:
  `dbe76ad50d100f4bf237688f31942e4dc745fb07`;
- related-work implementation/results are still untracked at this checkpoint;
  do not lose them, and do not start the full bank before a reviewed durable
  implementation/smoke commit is pushed;
- conda environment:
  `/localdata/dzhaoah/miniforge3/envs/gov`;
- required CUDA toolkit/runtime:
  `/usr/local/cuda-13.0.0`, with the conda `libstdc++.so.6` preloaded and
  the conda/CUDA libraries on `LD_LIBRARY_PATH`;
- runtime versions already recorded by the remote artifacts:
  Python 3.11, vLLM 0.26.0, PyTorch 2.11.0+cu130, Transformers 5.14.1;
- exact cached model revisions:
  - DeepSeek:
    `916b56a44061fd5cd7d6a8fb632557ed4f724f60`;
  - Qwen3:
    `b968826d9c46dd6066d109eabc6255188de91218`;
- live vLLM endpoints at the checkpoint:
  - GPU 0, DeepSeek, `127.0.0.1:18000`, observed server PID `836351`;
  - GPU 1, Qwen3, `127.0.0.1:18001`, observed server PID `836352`;
  - both BF16, prefix caching enabled, `max_model_len=34816`,
    `max_num_seqs=8`; DeepSeek memory utilization 0.88 and Qwen3 0.95.
  Re-resolve exact PIDs before any process action and never use broad
  `pkill`.

Frozen-bank facts already independently verified:

- 18 development manifests and 2,736 trajectories;
- 400 MATH500, 32 AMC23, and 24 AIME24 problems per model/seed;
- split-manifest SHA-256:
  `3d30cd624dd9cd637b5d3f40e030247d225114db6074c6b2d26a1351d676e9a6`;
- full frozen-bank SHA-256:
  `be1aeaa1d3a41ff21bf5052ea379621a78d7e35d1361916323cb3ac659f79893`;
- protocol version: `governor-v2-preregistered-2026-07-27.10`;
- independently counted primary trigger upper bounds:
  DeepSeek TJE 32,070, Qwen3 TJE 33,746; CertaIndex interval-64
  DeepSeek 99,833, Qwen3 129,860; DEER no more than 27,360 calls.

Implementation/smoke state:

- implementation lives under
  `benchmark/FalseConsensus/related_work/`;
- runtime scripts and smoke evidence live under
  `benchmark/FalseConsensus/results/related_work/_runtime/`;
- the original smoke exposed two real false positives: a 4,096-token
  DeepSeek AIME TJE readout truncated with no answer, and a near-max DeepSeek
  TJE confidence completion ended with `finish_reason=length` and no parsed
  label;
- corrections now include a vLLM
  `structured_outputs.choice` constraint over the exact ten TJE labels,
  an 8,192-token readout cap with exact pinned-tokenizer context budgeting,
  hard invalidation for truncation/null finish/context overflow, complete
  DEER logprob storage and hand recomputation, the exact Qwen3 `</think>`
  gate, positive latency checks, and shared production audit predicates;
- compileall, preflight, `git diff --check`, and 91 related-work tests with
  zero skips passed before the current clean smoke;
- the clean one-code-version smoke reached 18/18 case exits with code 0, and
  the corrected DeepSeek AIME TJE readout is valid:
  answer `55`, 4,931 output tokens from an 8,192 allowance,
  `finish_reason=stop`, completed boxed, not truncated, and no context
  overflow;
- **the smoke is not yet accepted**: the DeepSeek near-max DEER response was
  `"{12"` with a valid full logprob sequence, but
  `deer.parse_trial_response(response_text)` returned an empty answer. The
  DEER prompt already ends in the literal `\boxed`, so the parser must
  faithfully account for that prompt/completion boundary (for example by
  parsing the inducer plus completion, if that matches the official
  protocol). Fix the production collector and near-max probe together, add a
  regression fixture for `prompt suffix "\\boxed" + completion "{12"`, and
  rerun the affected smoke/audit. Do not weaken the truthy-answer predicate;
- inspect `.../_runtime/smoke/smoke_driver.log`, the tmux pane, canonical
  reproducibility output, and all six near-max probes before declaring smoke
  complete.

Immediate resume sequence:

1. capture `0:0.0` and inspect the clean smoke without injecting input while
   the agent is busy;
2. verify all 18 cases, canonical reproducibility, and six near-max probes;
3. require the clean DeepSeek AIME TJE record to show a nonempty completed
   boxed readout, `readout_valid=true`, non-`length` finish, no truncation,
   and no context overflow; require near-max DeepSeek TJE to parse one of the
   exact ten labels with non-`length` finish;
4. fix the DEER prompt/completion boundary so the official answer inducer
   ending in `\boxed` plus a completion such as `{12` yields answer `12` in
   both the production collector and near-max probe; add regression coverage
   and rerun the affected DeepSeek DEER smoke;
5. run the hardened audit plus compileall, all 91+ tests with zero skips,
   preflight, and `git diff --check`;
6. only then commit and push the implementation/config/tests/smoke evidence;
7. fetch that commit into a clean local worktree and independently review it;
8. after review, start the two concurrent model pipelines on GPU 0/1,
   CertaIndex then TJE then DEER, with restartable per-problem output.

Revised timing estimate from live smoke:

- GPU reprobing only: most likely **6–9 hours** wall clock with both model
  pipelines running concurrently and four workers per model;
- conservative reserve including transient retries and strict validation:
  **8–12 hours**;
- aggregation, 10,000-sample bootstrap, report/PDF QA, incremental commits,
  and final local/GitHub audit: an additional **2–4 hours**;
- therefore reserve **10–14 hours from full-run launch to complete GitHub
  delivery**. Re-estimate after the first 10–15 minutes of full CertaIndex
  using observed completed problems/probes per minute. The older 5–7-hour
  estimate below is superseded.

## 1. Fixed scope and outcome

Complete the three selected related-work baselines on the existing Governor
v2 **development train+dev frozen trajectories**:

1. CertaIndex / Dynasor faithful `mid`, using the original CertaIndex probe
   wording;
2. Think Just Enough (TJE), using its self-assessed-confidence prompt and
   primary keyword-triggered policy;
3. DEER, using the official model-specific base method, not DEER-Pro.

Active experimental grid:

- models:
  - `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`
  - `Qwen/Qwen3-8B`
- benchmarks: `math500`, `amc23`, `aime24`
- seeds: `42`, `43`, `44`
- phase/splits: development `train` and `dev` only
- 18 environment runs and 2,736 model-seed-problem trajectories total
- no GSM8K
- no confirmation/test data
- no 32B or architecture-heldout model in this task

Primary sources of truth:

- CertaIndex/Dynasor implementation:
  `dynasor/core/cot.py` and `dynasor/core/evaluator.py` in this repository;
- CertaIndex paper:
  <https://papers.nips.cc/paper_files/paper/2025/hash/d037fd021c9aace128b8ce25001cdb6c-Abstract-Conference.html>;
- TJE paper:
  <https://aclanthology.org/2026.findings-eacl.263/>;
- DEER paper and official code:
  <https://arxiv.org/abs/2504.15895> and
  <https://github.com/iie-ycx/DEER>.

Reuse the already frozen main trajectories. Do not regenerate or modify them.
The expensive GPU work is method-specific probing/readout only. Produce
complete per-problem records, aggregate metrics, paired uncertainty
intervals, a concise Chinese Markdown report, a PDF rendered from that report,
reproduction configs/manifests, validation logs, and all source code needed
to reproduce the experiment.

Expected wall clock is governed by the revised checkpoint estimate above:
6–9 hours for GPU reprobing, with an 8–12 hour operational reserve and
10–14 hours through final report/GitHub delivery. Persist through recoverable
failures.

## 2. Local/remote roles

### Local primary agent: you

You own the outcome. You must:

- use the `remote-tmux-agent` skill faithfully;
- establish the exact tmux target before sending anything;
- capture and understand the pane before every action;
- send the initial long instruction via a temporary file + `scp` + tmux
  buffer, verify the pasted text, and only then press Enter;
- avoid sending new work while the remote agent is busy;
- monitor at sensible intervals, inspect files and processes independently,
  and give corrective follow-ups when necessary;
- answer remote-agent questions from the repository, official papers/code,
  and evidence whenever possible rather than relaying them to the user;
- take over a stalled implementation when that is faster and safe;
- validate the final branch and artifacts yourself;
- ensure results are committed and pushed without losing local or remote user
  work.

### Remote tmux agent

The remote agent performs implementation and GPU execution on `ugcpu2`. It
must use separate tmux panes/windows for model servers and long-running
runners, make collectors restartable, monitor both GPUs, write manifests and
progress summaries, and commit/push incremental durable checkpoints.

## 3. Machine facts and safety boundaries

- SSH alias: `ugcpu2`.
- Always use the absolute project area
  `/localdata/dzhaoah/Governor`.
- Do not assume `~` points to the intended filesystem.
- The repository, environments, model cache, runtime logs, and experiment
  outputs are intentionally under `/localdata/dzhaoah`; do not redirect
  experiment output to `/homes/dzhaoah`.
- The login shell may be `tcsh`; use `bash -lc` for scripted remote commands.
- The user explicitly assigned GPU 0 and GPU 1 with full VRAM/compute.
  GPU 0 serves DeepSeek and GPU 1 serves Qwen3. Re-verify health and current
  processes, but do not substitute another card.
- GPUs 2–7 belong to another user/workload and must never be selected,
  reset, or have their processes touched.
- Before starting a model, verify the selected cards are healthy, have no
  unrelated compute processes, and really have close to 24 GB available.
- Never kill another user’s process, reset a GPU, or occupy an unassigned
  card.
- If GPU 0 or GPU 1 is no longer healthy/exclusive, do not substitute GPUs
  2–7. Exhaust read-only diagnosis and ask the user if the assigned pair
  cannot safely continue.
- Preserve unrelated files, branches, tmux sessions, and processes. Never use
  `git reset --hard`, destructive checkout, force-push, or broad recursive
  deletion.
- Never print or commit secrets.

Recommended topology after the GPU IDs are verified:

- one GPU permanently serves DeepSeek-7B;
- one GPU permanently serves Qwen3-8B;
- do not use tensor parallel;
- run the two model pipelines concurrently;
- use distinct local ports and record them in a run manifest.

Start with conservative vLLM concurrency (`max_num_seqs` and client workers
around 6–8), BF16, prefix caching, and GPU memory utilization around
0.88–0.90. Calibrate with a long AIME prefix. Increase concurrency only from
measured headroom. Never silently use quantization, CPU offload, or a
different model revision to avoid OOM.

## 4. Establish the remote agent correctly

Begin with read-only checks:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 ugcpu2 \
  "echo connected && hostname && tmux list-sessions"
ssh ugcpu2 \
  "tmux list-windows -a -F '#{session_name}:#{window_index} #{window_name} active=#{window_active} panes=#{window_panes}'"
ssh ugcpu2 \
  "tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} active=#{pane_active} cmd=#{pane_current_command} pid=#{pane_pid}'"
```

Resolve the exact `session:window.pane`. Capture roughly the last 60–80 lines
and classify the pane as idle, busy, awaiting approval, or containing queued
input. Do not paste over unknown text. If the expected agent is absent, inspect
all sessions before deciding whether to create a new agent pane.

The first message to the remote agent must include the fixed scope, protocols,
hardware rules, acceptance criteria, and Git workflow from this GOAL. For a
long message, use the safe file/scp/tmux-buffer procedure from the skill; do
not paste it through shell quoting.

## 5. Repository and environment preparation

Remote repository path must be:

```text
/localdata/dzhaoah/Governor
```

Before changing anything, inspect:

```bash
cd /localdata/dzhaoah/Governor
git status --short --branch
git remote -v
git log -5 --oneline --decorate
```

Treat any dirty changes as user work. Do not overwrite them. Fetch GitHub and
work on a dedicated branch such as:

```text
related-work-baselines-ugcpu2-20260727
```

If the existing remote tmux agent has already made relevant changes on
another branch, preserve and continue that branch rather than discarding it.

The local workspace may also contain uncommitted CertaIndex adapted-replay
work. Never reset or overwrite it. Use a separate local git worktree for clean
integration/validation if needed.

Audit, rather than assume, the infrastructure:

- Python and virtual environments;
- CUDA driver;
- PyTorch CUDA support;
- vLLM version and RTX 3090 compatibility;
- `transformers`, `openai`, `datasets`, `sympy`, `latex2sympy2`,
  `word2number`, `pandas`/`numpy`, `pandoc`, and PDF dependencies;
- model cache availability;
- disk quota and free space under `/localdata/dzhaoah`.

Prefer a dedicated, recorded virtual environment. Do not modify system Python.
Install only missing packages, pin or record exact versions, and capture:

```text
python version
torch version
CUDA runtime/driver
vLLM version
transformers version
model revisions if available
```

Do not redownload models that are already valid in cache. Do not assume vLLM
or the models exist.

Before GPU work, verify the frozen input bank:

- exactly 18 development main-run manifests;
- complete `math500` train+dev problem IDs: 400 per model/seed;
- complete `amc23` train+dev IDs: 32 per model/seed;
- complete `aime24` train+dev IDs: 24 per model/seed;
- 2,736 trajectories total;
- no test problem appears;
- trajectory and split-manifest hashes are recorded;
- no main trajectory is modified by the new collectors.

## 6. Shared implementation requirements

Implement method-specific collectors and replay/evaluation under a clearly
named related-work directory in the repository. Reuse common utilities for:

- loading and validating frozen main runs;
- tokenizer-consistent prefix positions;
- task answer extraction and robust mathematical equivalence;
- atomic per-problem writes;
- idempotent resume;
- flattening;
- per-run manifests and SHA-256 input hashes;
- token and wall-clock accounting;
- completeness/duplicate/split-leakage validation;
- paired hierarchical bootstrap.

Every output directory must have a manifest that records:

- method and reproduction class;
- exact prompt text or prompt file hash;
- trigger definition and positions;
- output cap;
- sampling parameters;
- seed policy;
- model ID/revision;
- source commit;
- input trajectory and split hashes;
- expected and observed problem/probe counts;
- failures/retries;
- whether test was read (must be false);
- whether main generation was changed (must be false).

Collectors must resume safely by validating an existing per-problem file
before skipping it. A partial or corrupt file must be quarantined and
regenerated, never silently counted as complete.

Use the same frozen trajectory prefix and tokenizer as Governor v2. Record
both the stored token count and re-encoded token count. Fail or flag material
misalignment.

## 7. Baseline protocols

### 7.1 CertaIndex faithful `mid` — primary CertaIndex result

Use the original suffix verbatim from `dynasor/core/cot.py`:

```text
... Oh, I suddenly got the answer to the whole problem, **Final Answer**

\[ \boxed{
```

Protocol:

- probe checkpoints: start 64, interval 64 on the frozen tokenized main trace;
- probe output cap: 20;
- temperature: 0.6;
- top-p: 0.95;
- probe seed: the environment base seed, consistently recorded;
- stop on the boxed-answer terminator in the same manner as the existing
  collector;
- patience: 3;
- all three answers nonempty;
- all three probes certain;
- uncertainty words exactly:
  `wait`, `hold`, `but`, `okay`, `no`, `hmm`;
- answer agreement uses Dynasor mathematical equivalence, not raw strings;
- no maturity floor and no extra Governor condition.

The expected full-bank upper bound is approximately:

- DeepSeek-7B: 99,833 CertaIndex probes;
- Qwen3-8B: 129,860 CertaIndex probes;
- total: 229,693.

Do not reuse `simple@32` answers for this result. Keep the existing
`certaindex_mid_stop_logic_on_simple32` result as an explicitly adapted
auxiliary baseline only.

If the frozen-prefix checkpoint convention differs by one chunk from the
streaming implementation in `dynasor/core/cot.py`, document that distinction
precisely. Do not conceal it under the word “faithful.” The prompt and
stopping rule must be faithful; any frozen-trajectory timing adaptation must
be named.

### 7.2 Think Just Enough — primary keyword-triggered policy

Use the official TJE confidence scale/instruction and structured
`\confidence{...}` response. Preserve all ten confidence labels. Primary
threshold is:

```text
Almost certain
```

Primary triggers:

- reflective marker `Wait` according to the paper’s policy;
- final `</think>` confidence check.

At a trigger, condition the confidence query on the complete frozen reasoning
prefix. Force/parse the structured confidence label without allowing a new
reasoning continuation inside the confidence response. If confidence is below
threshold, continue to the next trigger. If it is `Almost certain`, terminate
reasoning and generate the final answer/readout exactly as specified by the
method, recording that extra output cost.

Expected all-prefix upper bound before early stopping is approximately:

- DeepSeek-7B: 32,070 confidence points;
- Qwen3-8B: 33,746 confidence points.

Do not run Periodic-Conf(100), Periodic-Conf(1000), “Alternatively only,” or
lower-threshold ablations until all three primary baselines are complete and
durable. Their configs may be prepared, but they are not required GPU work in
this goal.

Important labeling: TJE normally supplies a confidence instruction as part of
the method and can alter online generation. Because this task keeps the main
trajectory frozen, call the result a **frozen-trajectory TJE reproduction**
unless the official procedure can be shown to leave the main trajectory
identical. Do not call it an end-to-end faithful run merely because the
confidence prompt is exact.

### 7.3 DEER — official base method

Use the official `iie-ycx/DEER` code and paper as the source of truth. Vendor
or pin the exact upstream commit used; do not depend on an unrecorded moving
checkout.

Primary configuration:

- base DEER, not DEER-Pro;
- default linguistic transition point: `Wait`;
- at most 10 answer-confidence attempts per problem;
- answer inducer:

```text
\n**Final Answer**\n\boxed
```

- trial-answer output cap: 20;
- request token logprobs required for confidence;
- threshold: 0.95;
- follow the official model-specific policy for each model;
- for Qwen3, use the official Qwen3-specific geometric-confidence behavior
  and its additional `</think>` requirement;
- if official code and paper differ on arithmetic vs geometric aggregation,
  follow the released model-specific code for the primary reproduction and
  document the discrepancy.

The hard upper bound from 2,736 trajectories × 10 attempts is 27,360 trial
answer calls, split evenly by model before early exit. Account for any final
answer/conclusion readout after a successful exit.

As with TJE, label the exact reproduction class. Replaying official DEER
probes on a frozen pre-generated path is not automatically identical to
running the entire online controller from the original prompt.

## 8. Fair accounting and metrics

For every method, preserve two cost views:

1. the paper-style reasoning/main-length metric;
2. a fair all-generated-token metric:

```text
main tokens through stop/full
+ every probe/confidence/trial-answer output incurred
+ any final answer/readout output introduced by the method
```

Probe/input prompt tokens are reported separately and must not be hidden.
Also report probe calls and wall-clock time.

For a trajectory with no early stop:

- deliver the frozen full-generation answer if it completed naturally within
  the evaluation budget;
- retain all probing costs incurred before full completion/cap.

For a stopped trajectory:

- use the answer that the actual baseline would deliver, not the future frozen
  full answer;
- grade with the project’s robust task-aware evaluator;
- record recovery truncated and overthinking avoided.

Produce at least:

- accuracy;
- full-generation accuracy;
- accuracy difference in percentage points, method minus full;
- average main tokens;
- average probe/readout generated tokens;
- average all-generated tokens;
- main-only token saving;
- all-generated-token saving;
- probe prompt tokens separately;
- stop rate;
- probe-call count;
- capped/right-censored rate;
- invalid/unparsed response rate;
- recovery-truncated and overthinking-avoided rates;
- wall-clock and throughput.

Summaries:

- each split × model × benchmark × seed environment;
- dev pooled across seeds for each model × benchmark;
- train+dev diagnostic pooled view;
- macro views that do not let MATH500 dominate AMC/AIME by sample count.

Use deterministic paired hierarchical bootstrap with 10,000 samples and seed
`20260727`: resample seeds, then paired problem rows within seed. Report 95%
confidence intervals for accuracy difference and token saving. Explicitly
warn that AMC/AIME intervals are wide.

## 9. Smoke test before scale-up

Do not launch the full 6–9 hour GPU workload immediately.

For each model and each method:

1. test one short MATH prefix;
2. test one medium AMC prefix;
3. test one long AIME prefix near the maximum observed context;
4. verify prompt construction, response parsing, logprobs where required,
   token accounting, determinism/seed behavior, and output manifests;
5. inspect GPU memory, server logs, and request failures;
6. measure throughput and revise the ETA.

For CertaIndex, verify that exact repeated probe calls with the same seed are
reproducible and that the own-prompt output is not accidentally the simple
prompt.

For TJE, verify all ten labels parse and `Almost certain` triggers the actual
final-answer path.

For DEER, verify the DeepSeek and Qwen3 policies separately and inspect the
per-token logprobs/confidence calculation by hand on several probes.

Do not proceed if a smoke result silently lacks logprobs, truncates the answer
before it can be parsed, uses the wrong model/template, or exceeds memory.

## 10. Parallel execution and monitoring

After smoke passes:

- dedicate one server/runner pipeline to each model;
- run method stages within each model in a restartable order;
- CertaIndex is the largest bank and should begin first;
- TJE and DEER follow without reloading the model;
- keep server and runner logs in explicit files;
- write progress counters such as completed/expected problems and probes;
- push a durable code/config commit before the long run;
- push incremental result commits after each model × method completes and
  validates.

As local supervisor, check:

- remote agent pane state;
- server and runner panes;
- `nvidia-smi` utilization/memory/temperature;
- recent logs;
- completed problem/probe counts;
- error/retry counts;
- disk usage;
- latest git commit/push state.

Do not poll tightly. A 10–20 minute cadence is appropriate during a healthy
long stage. If a runner makes no measurable progress for two checks, inspect
before intervening. If OOM occurs, reduce concurrency first; do not change
precision or method semantics. If a server crashes, preserve logs, restart it,
and resume idempotently.

The remote agent should continue through individual corrupt responses or
transient API failures, recording and retrying them. It must not declare the
whole task blocked because a handful of requests fail.

## 11. Acceptance checks

Before any completion claim, independently verify:

### Coverage

- exactly 18 environments per primary method;
- exactly 2,736 per-problem result rows per primary method;
- exact expected problem ID set in every environment;
- zero duplicates;
- zero test rows;
- no missing/corrupt output files;
- no unauthorized model, seed, benchmark, or split;
- CertaIndex probe count agrees with the frozen interval-64 bank except for
  explicitly justified endpoint behavior;
- TJE/DEER trigger counts agree with independently recomputed frozen-text
  triggers and their early-stop/max-attempt policies.

### Semantics

- prompt hashes match the checked-in prompt files;
- output caps, temperatures, top-p, seeds, thresholds, uncertainty words,
  trigger policies, and model-specific branches match manifests;
- CertaIndex uses own prompt, not simple;
- TJE uses the structured ten-class confidence prompt;
- DEER uses actual token logprobs and the official model-specific policy;
- stopped accuracy uses the delivered early answer/readout;
- no-stop accuracy uses only a legitimate natural full answer;
- total generated tokens include every auxiliary generated output;
- prompt tokens are separately present;
- reproduction labels honestly distinguish faithful prompt/rule from
  frozen-trajectory adaptation.

### Reproducibility

- unit tests pass;
- a small sample replay is byte/hash stable across two runs;
- aggregate regeneration from per-problem data is deterministic;
- report numbers reconcile exactly with CSV/JSON artifacts;
- manifests contain source/input/config hashes and environment versions;
- `git diff --check` passes;
- no secret, cache, environment, temporary file, or oversized monolithic file
  is committed.

## 12. Analysis and report

Create a concise Chinese report with:

1. executive conclusion;
2. exact scope and reproduction labels;
3. implementation/protocol table for CertaIndex, TJE, and DEER;
4. dev model × benchmark table with full accuracy, method accuracy,
   accuracy delta with CI, all-generated-token saving with CI, main-only
   saving, stop rate, and probe overhead;
5. accuracy-versus-token Pareto comparison against full generation and the
   available Governor exploratory candidates;
6. matched-accuracy and matched-token interpretation where possible;
7. separate explanation of paper-style and fair token accounting;
8. failure/censoring/parse diagnostics;
9. limitations, especially frozen-trajectory adaptation for TJE/DEER and
   small AMC/AIME sample sizes;
10. exact reproduction commands and artifact inventory.

Render the Markdown to PDF with Pandoc. Visually inspect the rendered PDF for
overflow, broken tables, missing glyphs, and unreadable figures. Keep the
report focused; detailed raw tables belong in CSV/JSON.

Do not spin a negative adapted result into a claim that the original paper is
invalid. Compare methods under the matched local protocol and clearly
separate that from quoted paper results.

## 13. Git and GitHub delivery

Commit intentionally and incrementally:

1. implementation, prompts, configs, tests, and smoke evidence;
2. CertaIndex result shards by model;
3. TJE result shards by model;
4. DEER result shards by model;
5. aggregate data, figures, Markdown/PDF report, and final audit.

Push the dedicated remote branch after every durable milestone. Never
force-push.

At the end, the local supervisor must:

- fetch the remote branch;
- inspect commit history and file sizes;
- run validation from a clean local worktree;
- preserve the current dirty local workspace;
- integrate with `main` only through a safe, intentional merge after tests
  pass and conflicts are understood;
- push the final GitHub state;
- verify the remote branch/main commit IDs from GitHub or `git ls-remote`.

If an individual artifact exceeds GitHub’s normal file limit, split it by
model/environment or use per-problem files. Do not omit raw results merely to
make the push easier.

## 14. When to ask the user

Do not ask routine implementation questions. Resolve them from:

1. the checked-in protocol and frozen manifests;
2. official upstream paper/code;
3. existing repository conventions;
4. a reversible smoke test.

Ask only for a genuinely external decision, such as:

- no identifiable pair of exclusive full-memory GPUs;
- SSH/authentication remains unavailable after diagnosis;
- GitHub access is unavailable;
- a required model cannot be obtained under existing credentials;
- official method ambiguity would materially change the primary result and
  cannot be resolved from paper/code.

Before asking, summarize the exact evidence, alternatives tried, and safest
options. Do not leave a healthy GPU job stopped while waiting on a
non-blocking question.

## 15. Final completion message

Return only after everything above is satisfied. The final response must
state:

- GitHub branch and final commit SHA;
- whether it is merged/pushed to `main`;
- exact GPU IDs and environment versions;
- start/end time and wall-clock per method/model;
- coverage counts and zero-missing/zero-test evidence;
- primary dev results for all 6 model × benchmark cells and all 3 methods;
- paths/links to raw data, metrics, manifests, report Markdown, and PDF;
- tests and audit commands that passed;
- retries/failures and how they were resolved;
- any limitation that remains;
- confirmation that remote model servers/runners were stopped while unrelated
  tmux sessions and user processes were preserved.

The goal is complete only when the experiments, validation, report, and
GitHub delivery are all complete—not when the remote agent merely starts the
jobs.
