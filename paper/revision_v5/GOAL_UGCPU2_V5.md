# GOAL: two probe collections that harden the preprint (G1 wording, G2 boundary-aligned consensus)

You are the persistent execution agent on `ugcpu2`. Own both experiments from
preflight through validated artifacts and a pushed branch. **Do not stop after
launching jobs.** Monitor, resume, diagnose, aggregate, test and report until
every acceptance condition is satisfied or a genuinely external blocker remains.

Context: the paper (`benchmark/FalseConsensus`, `paper/`) has been submitted to
ARR and we are hardening it for a preprint. Both experiments below exist to
remove a specific reviewer objection recorded in
`paper/revision_v5/DEFECT_LOG.md` (G1 and G2). Read that file first — it tells
you *why* each number matters, which is what lets you notice when a result is
suspicious.

**G1 and G2 are independent. Run them concurrently. Never let one block the
other.** If G2 turns out to be blocked, finish, accept, analyse, commit and push
G1 on its own rather than waiting.

---

## 1. Workspace and safety boundary

- Perform every repository action under `/localdata/dzhaoah/Governor`.
- Start from branch **`v5-preprint`** (fetch it; if the remote does not yet have
  it, branch from `main` after fetching and say so in the final report).
- The machine is shared, 8 × RTX 3090. Never kill, reset, or attach to another
  user's processes. Resolve genuinely free GPUs with `nvidia-smi` before
  serving; do not assume any numeric index is usable.
- The Vast.ai instance (id 45605832) is unrelated to this job and **must never
  be destroyed**.
- **Never regenerate a frozen main trajectory.** Every main trajectory under
  `benchmark/FalseConsensus/results/governor_v2/*/main/traj/` is frozen data the
  entire paper replays against. This job only *adds* probe banks.
- **Never modify or overwrite an existing `dense_simple32` bank.** G1 pairs
  against it; if it changes, the pairing is destroyed.
- Do not reset, checkout away from, clean, force-push, or broadly stage the
  worktree. Use explicit `git add <exact paths>` only. Never `git add -A`.
- 7B/8B models fit on one 3090 each in bf16. **Do not tensor-parallelize.** (The
  TP>1 NCCL workarounds recorded in `CLAUDE.md` are for the 32B model and are
  not needed here.)

---

## 2. G1 — un-truncated, two-model paired probe wording bank

### 2.1 Scientific objective

At every probe position, read the *same frozen prefix* with two probe wordings
that differ only in a commitment nudge, and measure how often they return the
same answer as a function of relative position in the trajectory.

The existing result (paper §4.2) is measured on one model, one benchmark, one
seed, with the re-probe capped at 3,072 tokens against 16K/32K main
trajectories — so it covers only the 241 of 400 trajectories short enough to be
read end to end, i.e. a **length-selected** subsample. This collection removes
the truncation and the single-environment scope.

**This is a paired readout experiment, not a stopping-rule comparison.** Both
arms read identical frozen prefixes at identical positions. Only the suffix
differs.

### 2.2 The two arms

Arm A (**already collected — do not re-run**): the existing `dense_simple32`
bank in each environment directory. Suffix:

```
**Final Answer**\n\n\[ \boxed{
```

Arm B (**collect this**): identical in every respect except the suffix:

```
... Oh, I suddenly got the answer to the whole problem, **Final Answer**\n\n\[ \boxed{
```

Both suffixes are already defined verbatim in
`benchmark/FalseConsensus/probe_compare/reprobe_paired.py` as `PROBE_SUFFIXES`
and in `benchmark/FalseConsensus/logging_run.py`. **Copy them from there; do not
retype them.** A whitespace difference invalidates the experiment.

Everything else must match `dense_simple32` exactly: `probe_tokens=32`,
`dense_interval=64`, `start_token=64`, stop sequence `\]`, the temperature /
top-p / seed recorded in the environment's `main/run_manifest.json`, and the
probe prompt construction `apply_chat_template(problem) + prefix + suffix` with
the prefix reconstructed by token slicing
(`ids = tokenizer.encode(full_text, add_special_tokens=False)`;
`prefix = tokenizer.decode(ids[:token_position])`).

### 2.3 Frozen scope

- environments: the **18 development** directories
  `results/governor_v2/development__*` — models
  `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` and `Qwen/Qwen3-8B`, benchmarks
  `math500` / `amc23` / `aime24`, seeds 42 / 43 / 44.
- problems: the **dev split only**, from
  `benchmark/FalseConsensus/governor_v2/generated/problem_ids/<bench>__dev.txt`
  (math500 100, amc23 8, aime24 6 → 114 per environment).
- expected trajectories: **114 × 6 = 684** (this is the same 684 the paper's
  §4.1 broader measurement uses — the match is intentional; confirm it).
- expected probe calls: **≈ 57,000**. Derived from the committed
  `dense_simple32` banks (train+dev = 2,736 trajectories / 229,693 probes; mean
  probes per trajectory 72 on math500, 120 on amc23, 231 on aime24). If your
  realized count differs from the paired `dense_simple32` dev-split count by
  even one probe position, that is a bug — stop and diagnose.

Do **not** collect train or test problems. Do not collect the confirmation
models (Llama-8B, Qwen-32B) — they are held out and this diagnostic never feeds
selection.

### 2.4 Implementation

The collector is `benchmark/FalseConsensus/governor_v2/dense_probe.py`. It
currently hardcodes `SIMPLE_SUFFIX` and writes `"probe_style": "simple"` into
the manifest. Extend it minimally:

- add `--probe-style {simple,certaindex}`, defaulting to `simple`;
- add `--problem-ids <file>` to restrict collection to listed problem ids;
- write the chosen style into `probe_manifest.json`;
- **preserve existing behaviour byte-for-byte when the new flags are absent.**

Prove that last point before using any GPU: re-run the collector in a
`--flatten-only` / dry mode against an existing `dense_simple32` directory and
show the manifest and CSV are unchanged. Add a unit test asserting that
`--probe-style simple` selects the identical suffix string as the current
constant.

Output root, one directory per environment, sibling to `dense_simple32`:

```
results/governor_v2/development__<model>__<bench>__seed_<NN>/dense_certaindex32/
    probe_manifest.json
    probes/problem_<id>.json
    probes.csv
```

Schema must be identical to `dense_simple32` so existing readers work unchanged.

### 2.5 Servers

One bf16 vLLM server per model on two actually-free 3090s, with prefix caching
enabled (probes on one trajectory share monotone prefixes; without
`--enable-prefix-caching` this job is several times slower):

- DeepSeek-7B → `http://127.0.0.1:18000/v1`
- Qwen3-8B → `http://127.0.0.1:18001/v1`

Choose `--gpu-memory-utilization` and `--max-model-len` that fit the longest
frozen prefix (32K on AIME24) without OOMing a neighbour. Verify before
collecting: the port belongs to your process, `/v1/models` returns the expected
model, and the tokenizer/chat-template hash matches the environment's
`main/run_manifest.json` and the `chat_template_sha256` recorded in the
`dense_simple32` bank. A chat-template mismatch silently invalidates the whole
collection — check it, do not assume it.

Smoke first: two problems per model into a `_smoke` directory **outside** the
formal output. Require non-empty probe records, `probe_out_tokens <= 32`,
parseable answers, no context-length errors.

### 2.6 Expected cost

≈ 57,000 probes at 32 output tokens, prefix-cached. **2–4 h wall clock** with
both models running concurrently on 2 × 3090, conservatively under 6 h. If your
projection exceeds 8 h, stop and diagnose throughput, prefix caching, and worker
concurrency rather than waiting. `--workers 16` per model is a reasonable start.

### 2.7 Acceptance (G1)

- 18 `dense_certaindex32` directories.
- Exactly 684 trajectories; per-environment counts 100/8/6 matching the dev id
  files.
- For every trajectory, the certaindex probe `token_position` list is **exactly
  equal** to the paired `dense_simple32` list. Report any mismatch as a failure,
  not a warning.
- Zero `probe_out_tokens > 32`; zero request-error rows; zero duplicate
  (problem_id, token_position) pairs.
- Manifest settings exactly: `probe_tokens 32`, `dense_interval 64`,
  `start_token 64`, `probe_style certaindex`.
- No `dense_simple32` file has a modified mtime or content hash.

### 2.8 Analysis (G1)

Write `benchmark/FalseConsensus/report/compute_probe_wording_v5.py`, modelled on
the existing `compute_probe_wording.py` but **without the 3,072-cap cleaning
step, which is no longer needed** — state explicitly in the report that no
length-based exclusion was applied, and report separately how many trajectories
hit the generation budget instead of finishing (those are still excluded, as
before, because their "position as % of length" is undefined).

Produce, in `benchmark/FalseConsensus/results/probe_wording_v5/`:

- `probe_wording_v5.json` and `per_position.csv`
- `report.md` containing, in this order:
  1. coverage: trajectories and positions, per environment and pooled;
  2. two-wording agreement rate by relative-position bin, using the **same 11
     bins** as the current figure (0–5, 5–10, 10–15, 15–20, 20–30, 30–40, 40–50,
     50–60, 60–70, 70–85, 85–100), reported **three ways**: pooled, macro over
     the 18 environments, and **per model separately**;
  3. probe-correctness rate by the same bins;
  4. the two headline numbers the paper quotes — disagreement in the first tenth
     and in the final third — recomputed, per model and pooled;
  5. the readout-vs-timing decomposition the paper cites (effect of *which*
     suffix on final accuracy vs effect of *when* one probes);
  6. a direct comparison against the committed v3 numbers
     (`figures/gen/probe_wording.json`: 46.5% agreement in the first tenth,
     88.6% in the last bin, 76.0% overall on 241 trajectories / 2,898
     positions), with an explicit statement of whether the effect grew, shrank,
     or reversed once length selection was removed.

**Report the per-model split honestly even if the two models disagree.** A
smaller effect on Qwen3-8B is a publishable finding and we would much rather
learn it here than from a reviewer. Do not pool away a model difference.

Use the robust grader (`grading.robust_answers_equal`) and **reset
`latex2sympy2.var = {}` before every grader call** — the library keeps a
module-global that makes grading order-dependent (see `CLAUDE.md`).

---

## 3. G2 — consensus evaluated at DEER's own boundary positions

### 3.1 Scientific objective

The paper contrasts a consensus family (reads a probe answer on a fixed 64-token
grid) against DEER (reads confidence in a freshly generated trial answer at a
reasoning boundary). Three factors differ at once, so the contrast is not a
one-factor ablation and §5.7 currently concedes this in prose.

This experiment holds **when** fixed and varies only **what** is read: run the
windowed consensus family on a probe stream sampled at *DEER's own boundary
positions* instead of the 64-token grid. If consensus still clears no gate, the
timing confound is eliminated by measurement rather than by hedging.

### 3.2 Getting the boundary positions

Boundary positions come from the committed DEER bank:

```
benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30/full/<model>__<bench>__seed_<NN>/trials.jsonl.gz
```

Inspect a full record first (the records carry `expected_candidate_count`,
`generated_trial_count`, `max_attempts: 30` and per-trial entries). Extract the
token position of every boundary at which DEER generated a trial.

**If token positions are not recorded** in the bank, do not block: re-derive
boundaries from the frozen `full_text` using the same reasoning-boundary marker
detection as `benchmark/FalseConsensus/related_work/deer.py`, and validate the
re-derivation by checking that the re-derived boundary count per problem matches
`generated_trial_count` (capped at 30). Report which path you took.

Note the **Ġ/Ċ anomaly**: Llama-8B seed-45 `full_text` is stored with BPE
metacharacters (Ġ = space, Ċ = newline). It is normalized at read time by the
DEER collector; you must normalize the same way and must **not** mutate frozen
data. This job uses development models only, so it should not arise — but if you
see those characters anywhere, normalize at read time and say so.

### 3.3 Scope and collection

- same 18 development environments, same **dev split**, 684 trajectories;
- probe style **simple@32** (Arm A's suffix — this experiment varies position,
  not wording), stop sequence `\]`, same sampling settings;
- probe positions = the boundary positions from §3.2, capped at 30 per problem
  as the DEER bank is;
- expected ≤ 30 × 684 ≈ **20,000 probes**, i.e. roughly a third of G1;
  **1–2 h** on one 3090 (reuse a G1 server once G1 finishes, or a third GPU if
  free).

Output: `results/governor_v2/development__*/boundary_simple32/`, same schema,
with `probe_style: "simple"` and a `probe_schedule: "deer_boundary"` field plus
the source bank path recorded in the manifest.

### 3.4 Replay and gates (G2)

Run the **preregistered consensus rule family** over this boundary-aligned
stream through the existing machinery
(`benchmark/FalseConsensus/governor_v2/replay_rules.py`), the existing
`protocol_v2.json` gates, and the existing token accounting. The probe-schedule
knob is now fixed to `deer_boundary`, so the swept grid is
$W \in \{1,3,5,8,12,16,24,30\}$ × $s \in \{0.6,0.8,1.0\}$ × maturity floor ×
validity × certainty.

Requirements:

- **macro-average over the 18 environments, never problem-micro** — this is a
  protocol mandate;
- confirm `replay_rules.answers_equal` is using `grading.robust_answers_equal`
  (a past bug silently used a weak grader; dev full-generation accuracy must
  come out at ≈ 82.5% — if it does not, stop and fix the grader before believing
  any number);
- charge probe output tokens to net saving exactly as the main sweep does;
- report **dev only**. Do not read the test split. Do not touch the confirmation
  models. This experiment is diagnostic and must not create the impression that
  test was consulted.

### 3.5 Analysis (G2)

`benchmark/FalseConsensus/results/boundary_consensus_v5/report.md`:

1. how many rules clear each of the three gates on dev (the number that
   matters — the prediction is 0);
2. the accuracy-drop / net-saving frontier, plotted against the committed
   fixed-grid consensus frontier and the DEER frontier on one axis;
3. max net saving among rules with drop ≤ 1.0 pp, and drop at the first rule
   reaching 10% / 20% / 30% saving — the same four quantities §5.2 reports for
   the fixed grid, so the two are directly comparable;
4. harm:rescue by window $W$ on the boundary stream, against the committed
   fixed-grid values (45:1 → 2:1);
5. a plain-language statement of which of the two hypotheses the data supports:
   *(a)* consensus still fails at DEER's own reading positions, so the failure is
   the signal; or *(b)* consensus clears a gate once read at boundaries, so the
   published result is partly about probe schedules.

**Outcome (b) is a real possibility and would be a major finding. Do not soften,
bury, or re-tune toward (a).** Report exactly what the replay produces. If you
find yourself wanting to adjust a knob to recover (a), stop and report instead.

---

## 4. Tests and integrity

Run at least:

```bash
python -m unittest benchmark.FalseConsensus.governor_v2.tests.test_governor_v2
python -m unittest discover -s benchmark/FalseConsensus/related_work/tests
git diff --check
```

plus the new unit tests for the `--probe-style` / `--problem-ids` flags and for
the boundary-position extraction. Verify JSON/CSV parseability, exact row
counts, manifest hashes, and that no raw probe file is a Git LFS pointer stub.
Verify by content hash that no pre-existing frozen artifact changed.

---

## 5. Commit and push

Create branch `v5-gpu-<date>` off `v5-preprint`. Stage **only**:

- `benchmark/FalseConsensus/governor_v2/dense_probe.py` (the minimal flag edit)
- the new collector/analysis scripts and their tests
- `benchmark/FalseConsensus/results/governor_v2/development__*/dense_certaindex32/`
- `benchmark/FalseConsensus/results/governor_v2/development__*/boundary_simple32/`
- `benchmark/FalseConsensus/results/probe_wording_v5/`
- `benchmark/FalseConsensus/results/boundary_consensus_v5/`

Print the staged file list before committing and prove nothing unrelated is
staged. If the raw probe banks are large, check the repo's existing convention
for committed banks (`results/governor_v2_ws_sweep/` is committed) and follow
it; if they exceed a sane size, commit the flattened CSVs plus manifests and
gzip the per-problem JSON, and record the decision.

End the commit message with the `Co-Authored-By` / `Claude-Session` trailers,
per repo convention. Push the branch. **Do not merge to main. Do not
force-push.** Commit and push **G1 as soon as it accepts**, without waiting for
G2.

Update `log.md` and `plan.md` with absolute dates, per repo convention.

---

## 6. Final report

Return:

1. branch name and commit SHA(s);
2. coverage and acceptance status for G1 and G2 separately;
3. GPU / server / vLLM configuration actually used, and the chat-template hash
   check result;
4. wall-clock time and probe-call counts;
5. **G1 headline**: two-wording disagreement in the first tenth and final third,
   pooled and per model, against the committed v3 values, with a one-line verdict
   on whether removing length selection changed the conclusion;
6. **G2 headline**: how many rules clear each gate on the boundary-aligned
   stream, and which of hypotheses (a)/(b) the data supports;
7. all test results;
8. deviations, limitations, and anything that surprised you;
9. exact artifact paths.

Resolve recoverable environment, dependency, endpoint, resume and aggregation
issues yourself. **Ask only if** required model weights are inaccessible, no
usable GPU exists, or proceeding would require deleting or overwriting frozen
data. Do not ask routine questions.

One standing instruction that overrides convenience: if a number comes out
looking wrong, investigate it rather than reporting it with a caveat. Every
figure in this repo has at some point been wrong in a way that a careful reader
would have caught — assume yours is too until you have checked it.
