# CLAUDE.md

Guidance for Claude Code working in this repo. **Read "v5 preprint state" first
— it is the live handoff.** Everything below it is reference: locked decisions
you must not undo, the experimental machinery, and where things live.

## What this repository is

Two overlapping projects share this tree:

1. **`dynasor/`** — the upstream Dynasor pip package (certainty-based early exit
   for reasoning models). Stable, installable, mostly unchanged. See `README.md`.
2. **`benchmark/FalseConsensus/`** — the *active research*, a paper titled
   **"Stable Answers, Unfinished Reasoning: Why Self-Consensus Is Not a Safe
   Early-Exit Signal."** Almost all ongoing work is here and in `paper/`.

When a request mentions "the paper", "the sweep", "gates", "DEER", "consensus",
or "Governor", it concerns project #2.

---

## v5 preprint state (READ FIRST — handoff, 2026-08-07)

**The paper has been submitted to ARR; the deadline has passed and the submitted
PDF cannot change.** The current goal is a **preprint**, so the work is to make
the paper as solid as possible before public release. There is no page limit on
a preprint — this removes the v4 page pressure and frees room for hedges and
robustness tables.

### Working rule — do not modify the paper without approval

**Antony approves every paper edit individually.** Find problems, settle them
with data, record them — but do not touch anything under `paper/sections/`,
`paper/acl_latex.tex`, or `paper/custom.bib` until he says so for that specific
item. Diagnostics, analysis scripts and notes under `paper/revision_v5/` are
free to write.

### Branches

`main` now contains **every** branch: `v4`, `v3-mechanism-figures`,
`origin/v3-stability-terminality`, `origin/ugcpu2-batch-20260729`, and the six
superseded `origin/main` paper commits (merged at `6a22a59c` with v4's tree
taken verbatim; audited — no path exists on any branch that is absent from v4,
except 12 intentional deletions).

**`v5-preprint` is the live branch.** Work there.

### The review plan

Standard: **hostile reviewer** — a reader who wants a reason not to believe the
paper. `paper/revision_v5/DEFECT_LOG.md` is the tracking file; every item
records the claim at risk, the attack, what settles it, compute cost, and
status. Read it before starting anything.

Round 1 (CPU, committed banks) is nearly done — D2, D3, D4, D5 settled, D6
found, **D1 still open**. Rounds 2–4 are scoped in the log.

### Round 1 results — usable numbers, none yet written into the paper

**D2 `settled-fix`, favourable.** Applying all three gates on **gross** saving
(i.e. forgiving the probe tax entirely) still yields **0/3,520**. Max gross
saving among the 40 rules with drop ≤1.0 pp is **2.07%** against a 10% floor
(net 0.21%). Gross cost curve: **1.91 / 3.85 / 8.06 pp** at 10/20/30% saving
(net: 2.66 / 6.17 / 11.76). The probe tax is not why the corner is empty — this
is currently conceded in Limitations and should be promoted to a result.

**D3 `settled-fix`, favourable with a caveat.** Pooled-over-problems still gives
**0/3,520** on all three gates, and leave-one-environment-out gives 0 for all 18
environments — the negative result depends on no single environment. The 478
train winners reproduce exactly; on dev their median drop is 4.50 pp macro,
1.75 pp pooled, and 0 clear the gate under either weighting. **But** pooling is
much more permissive: 634 rules under 1.0 pp (vs 40), max saving among them
**9.13%** — only 0.87 pp short of the 10% floor. So the gate is empty either
way, but "far under the floor" is a macro-specific statement. §5.2's phrasing
needs scoping and the near-miss should be reported.

**D4 `settled-ok` — closed by Antony, do not reopen.** Adjudicating annotator
2's A/D conflicts to D under a fixed rule is legitimate, needs no declaration,
and is not a defect. For the record if a reviewer raises it: κ=0.8175 on the
top-level three-way coding (what the paper reports, correctly scoped in both
places it appears), 0.286 on the five-way coding, and 0.000 on the A-vs-D
distinction restricted to the 100 cases both raters called substantive; 61 of
134 A/D conflicts were adjudicated. Posture is the same as the
`preregistration_ml` stub: **disclose honestly if asked, do not volunteer.**
One wording micro-edit awaits approval — §1's contribution bullet cites κ=0.82
without the "top-level coding" qualifier the other two sites carry.

**D5 `settled-ok`, with an obligation.** The preregistration framework and its
commitments predate collection: `ccd56536` (2026-07-26) already carries
`pooling: macro-average environments; never raw-problem micro-average`,
psf 0.8, test-read-once and the heldout policy; `6556a81c` (2026-07-27) has all
three operating points; the negative result was recorded at `1a60f095`
(2026-07-27). That is **stronger than the paper claims.** Two things must be
stated, though: `protocol_v2.json` ships in the *same commit* as the v2 sweep
results (`98a26dc0`, 2026-08-02), so git alone cannot order them; and the
2026-07-26 caps were per-model 1.5 pp / per-benchmark 2.0 pp, **not** the
published total 1.0/2.0/3.5 pp with saving floors. Appendix B should carry the
SHA table.

**D6 `settled-fix` — new, and a release blocker.**
`grading.robust_answers_equal` **degrades silently** when `dynasor` is not
importable: the `from grading import robust_answers_equal` line succeeds, the
evaluator underneath is missing, and everything falls back to a numeric path
where `answers_equal("0.5", r"\frac{1}{2}")` returns **False** with no warning.
This is the v1 weak-grader bug in a new costume — it cost real time to diagnose
(harm counts came out 317 vs the committed 361 at W=1 while stop counts matched
exactly). Also `latex2sympy2` is incompatible with modern antlr4 runtimes and
needs **`antlr4-python3-runtime==4.7.2`**; the default pip resolution throws
`Could not deserialize ATN`. A reader who clones without `pip install -e .` gets
systematically low accuracy and no error — the easiest possible path to a
"could not reproduce" report on a paper whose selling point is full release.
Fix: hard-fail (or at minimum warn) in `replay_rules.answers_equal`, pin the
dependency in Appendix C, and turn the informal "dev full-gen ≈ 82.5%" check
into an assertion.

### D1 — the one round-1 item still open

**Claim at risk:** the abstract and §4.4 say sampling noise predicts a
$\approx1{:}1$ harm:rescue ratio. It does not. The ratio is computed among
problems a rule stops, and most trajectories end correct, so the base-rate null
is $p(1-q)/((1-p)q)$ with $p=P(\text{final correct}\mid\text{stopped})$ and
$q=P(\text{stop correct}\mid\text{stopped})$ — well above 1.

`benchmark/FalseConsensus/report/compute_harm_rescue_null.py` computes the full
2×2 per window, the base-rate null and a within-environment permutation null.
**Run it on the host with the grader properly installed** and check it
reproduces the committed cache first (`harm_rescue_cache.json`: W=1 harm 361 /
rescue 8 / 668 stops; W=30 harm 8 / rescue 4 / 121 stops). A degraded-grader run
gave 317/8 at W=1 — if you see numbers like that, the grader is broken, not the
result.

Expect the conclusion to survive with the null corrected: the direction of the
effect is large at every window. The wording in the abstract, §4.4 and the
conclusion will need to change from "1:1" to the computed null.

### GPU work dispatched

`paper/revision_v5/GOAL_UGCPU2_V5.md` is a self-contained GOAL for the agent on
**ugcpu2** (8 × RTX 3090). Two independent experiments:

- **G1** — collect `dense_certaindex32` against the frozen 16K/32K main
  trajectories, 18 dev environments, dev split, 684 trajectories, ≈57k probes,
  pairing 1:1 with the committed `dense_simple32`. 2 × 3090, 2–4 h. This removes
  the length selection and single-environment scope behind §4.2's wording result
  (currently 1 model, 241 of 400 trajectories, 3,072-token re-probe cap).
- **G2** — collect simple@32 probes at **DEER's own boundary positions** and
  replay the preregistered consensus family there through the same gates. 1–2 ×
  3090, 1–2 h. This holds *when* fixed and varies only *what* is read, turning
  §5.7's admitted confound into a measurement. **A result where consensus
  clears a gate on the boundary-aligned stream is a real possibility and must be
  reported as found, not tuned away.**

---

## Locked decisions — do not drift, do not undo

These cost real effort in v3/v4. Changing any of them needs Antony's explicit
agreement.

### Terminology

One term only. `stability` was deliberately demoted and is no longer a keyword.

- **`self-consensus`** — the only formal name; defined in `01_introduction.tex`
  ¶1, which also declares the abbreviation.
- **`consensus`** — declared abbreviation, used throughout the body.
- **`agreement` / `agree`** — ordinary verbs, not terms.
- The concept is the **`consensus--termination gap`**.

**The core sentence must not become a tautology.** "Agreement establishes
consensus, not termination" is circular. The locked phrasing carries the meaning
with `persists`:

> repeated agreement establishes only that the current answer \emph{persists}
> under a fixed probing procedure, not that the reasoning has
> \emph{terminated}---a \emph{consensus--termination gap}.

Self-check after any edit — all of these must grep to **0** in
`paper/sections/*.tex` and `paper/acl_latex.tex`: `terminality`,
`probe stability`, `probe agreement`, `answer stability`,
`intermediate answer consensus`, `false consensus`, `positive control`,
`identical pipeline`. `stable` / `settled` as ordinary adjectives are fine.

### Claim scoping

1. **harm:rescue is a range, not a headline.** Abstract, intro and conclusion
   say **2–45×**, never "up to 45×". 45:1 is `W=1`, which comes with a 65.9 pp
   drop and 92.3% saving — an operating point nobody deploys. The intro puts the
   contrast in the same breath: the 2× end buys only **7.9%** net saving,
   whereas DEER holds **2.4–3.5×** while saving **28–32%**. §4.4 and the figure
   caption keep 45:1 because they sit in full-curve context.
2. **The DEER contrast is not a one-factor ablation.** DEER also differs in
   *when* it reads and *what* it commits. §5.7 carries this as a **fourth
   qualification** and the section says the failure lies in how the stop is
   decided rather than in early exit. Keep the hedge — G2 exists to earn the
   right to weaken it.
3. **Two-layer result, not a transfer-only story.** **0 of 3,520 rules clear any
   gate on dev itself**, so nothing is ever selected. The 478 train in-sample
   winners are the second layer. Abstract and intro state both.
4. **Factual trap, previously wrong:** the 478 in-sample winners do **not** fail
   on test — **364 of them clear the conservative gate on test** (444 clear it
   on test overall). What is empty is **dev** (0) and **dev∧test jointly** (0).
   Never write "they survive on neither dev nor test".
5. **Taxonomy provenance stays out of the paper.** See D4 above.
6. **CertaIndex framing.** Always **CertaIndex (CoT)**, never bare
   "CertaIndex". We reproduce the released Dynasor implementation at its default
   `mid` setting (`dynasor/core/cot.py @ dbe76ad`). `tab:baselines` is sourced
   from `related_work/certaindex_mid.py` + `results/related_work/certaindex_effort_bank/`
   — **not** `governor_v2/replay_certaindex.py`, whose own docstring admits it is
   not the faithful configuration. Their **multi-path setting is ordinary
   self-consistency** and nothing here bears on it; §4.4 states this in two scope
   notes. No "collapse"/takedown language. We are **not** adding the paper's
   H̃-threshold variant.
7. **Structure.** §1 Intro → §2 Related Work → §3 Experimental Setup → **§4 The
   Consensus–Termination Gap** (measurement first) → **§5 The Gap Cannot Be
   Tuned Away** → §6 Conclusion → Limitations; appendices A–F then G. The
   **abstract is result-first, the body is mechanism-first** — §4's opening
   carries an explicit bridge sentence so this is visibly intentional. Do not
   "fix" it. Subsection titles are ACL-style **short noun phrases**, not
   sentence-claims.

### Known defect in the submitted PDF — decision already made

`custom.bib` carried a **fabricated stub** since the first scaffold commit:
`preregistration_ml` = "Preregistration in Machine Learning Research", Nosek et
al., arXiv, no identifier. **No such paper exists.** It renders in the submitted
PDF as `(Nosek et al., 2025)` on p6 and in the References on p10. It supports
**no** empirical claim. Fixed in `9ae683ad` by citing Nosek, Ebersole, DeHaven &
Mellor, *The preregistration revolution*, PNAS 115(11):2600–2606, 2018,
doi:10.1073/pnas.1708274114. **Antony's decision: disclose honestly if a
reviewer raises it, fix in camera-ready. Do not re-litigate.**

---

## Numbers as they stand (verified against committed banks)

| claim | paper | source |
|---|---|---|
| two wordings disagree, first tenth | 54% | 53.51%, n=213 |
| two wordings disagree, final third | 10% | 10.47%, n=773 |
| Fig. 2(a) annotations | 41% earliest bin, 46% first tenth, 89% last bin | 41.20 / 46.49 / 88.60 |
| paired bank coverage | 241 of 400 trajectories, 2,898 positions | `probe_wording.json` |
| taxonomy | D 61.2% / E 18.7% / A 17.9% / other 2.2%, κ=0.82 | `results/human_eval/adjudicated/` |
| harm:rescue | 2–45× | 45.1 → 2.0 across W |
| 2× end net saving | 7.9% | 7.92% (W=30, 121 stops) |
| DEER | 2.4–3.5× @ 28–32% | 3.0 / 2.4 / 3.5 @ 28.2 / 29.6 / 31.9 |
| sweep | 40 rules ≤1.0 pp, best saves 0.21%; 10/20/30% saving costs 2.66 / 6.17 / 11.76 pp | dev sweep archive (reverified 2026-08-07) |
| generalization | r=0.98 dev↔test, 0.97 32B, 0.94 Llama; 478 / 0 dev / 444 test / 364 overlap / 0 joint | `test/`, `heldout_test/` |
| gross vs net | 14.9/10.9 and 27.0/20.2 | recomputed |

New in v5, not yet in the paper: gross-gate 0/3,520 and 2.07% gross ceiling
(D2); pooled 0/3,520, LOEO 0/18, pooled 634 rules @ 9.13% ceiling (D3).

`tab:deer` (14 thresholds), `tab:baselines`, §4.1's four facts, and the case
studies (pid 68, 320, 253, 240) were verified earlier and are unchanged.
**pid 240 fires at token 384, not 192.**

### Citations — audited 2026-08-07

All 18 cited entries checked title ↔ arXiv ID ↔ authors ↔ year. **All correct**
after the `preregistration_ml` fix. Optional nit: `dynasor_certaindex`
(arXiv:2412.20993) uses the v1 title *Efficiently **Serving** LLM Reasoning
**Programs** with Certaindex*; arXiv now lists *Efficiently **Scaling** LLM
Reasoning with Certaindex*. `custom.bib` has 9 uncited orphan entries — harmless,
BibTeX only emits cited entries. The Semantic Scholar API was unreachable; use
`arxiv.org/abs/<id>` plus web search instead.

---

## Experimental details you MUST heed

- **Install the package before running anything.** `pip install -e .` plus
  `regex`, `latex2sympy2`, and **`antlr4-python3-runtime==4.7.2`**. Then confirm
  the robust grader is live: `answers_equal("0.5", r"\frac{1}{2}")` must be
  `True` and dev full-generation accuracy must be ≈ **82.5%**. See D6 — this
  fails *silently*.
- **The grader is order-dependent — reset `latex2sympy2.var = {}` before every
  call.** That library keeps a module-global `var` dict. Grading the MATH500
  answer `"8thgradeshouldhave10representatives"` overwrites it with a bare
  `Symbol`; every later `latex2sympy` call then raises inside `symbolic_equal`,
  which **silently returns False**. All v3 scripts do the reset. Audit of the dev
  baselines: 3 of 684 verdicts affected (0.44%), baseline 89.33% → 89.77% —
  conservative direction, committed banks stand.
- **Macro, never pooled.** Every headline metric is macro-averaged over the 18
  environments (protocol mandate). Pooled may be reported as a robustness check
  (D3), never as a substitution.
- **Frozen trajectories.** Main reasoning is generated once and frozen; all
  methods are *replayed* offline against frozen prefixes using pre-collected
  probe banks. Never re-run main generation to add a rule.
- **Two token views.** `main_tokens_through_stop` (paper-style) and
  `all_generated_tokens` (fair: main + probe/trial output). Net saving charges
  probe/trial output; probe *prompt* tokens are reported separately, never added.
- **Test is read once**, after rules and thresholds are frozen; never tune on it.
  Llama-8B and Qwen-32B are held out (scale/architecture confirmation only).
- **DEER = trial-answer-submit** (commit the trial answer directly), the stronger
  variant; only hyperparameter is the confidence threshold. It is a control for
  the signal, not a SOTA claim, not the faithful readout.
- **Probe banks differ in whether they truncate at the stop.**
  `probe_paired_2x2` and `dense_simple32` probe on a fixed schedule regardless of
  stopping (usable for position-binned analysis). `probe_prompt_ablation/certaindex32`
  and the DEER confidence banks **halt at their own stop rule** (median 5 probes,
  max position 320) — position-binned analysis on them is selection-biased and
  invalid. This is why G1 has to collect a new bank.
- **Small sets are noisy.** AIME24/AMC23 have few problems per seed (dev splits
  of 6 and 8); use 3 seeds and macro. Single-seed held-out numbers are
  unreliable.
- **DEER on 3090s needs NCCL env for TP>1**: `NCCL_P2P_DISABLE=1
  NCCL_IB_DISABLE=1 NCCL_NET_PLUGIN=none` (PCIe 3090, no NVLink). 32B TP=4 bf16;
  7B/8B are single-GPU and need none of this.
- **Ġ/Ċ anomaly**: Llama-8B seed-45 confirmation `full_text` is stored with BPE
  metacharacters (Ġ=space, Ċ=newline); normalize at read time, never mutate
  frozen data.
- **Remote GPU safety**: the Vast.ai instance (id 45605832) may be *stopped* but
  must **never be destroyed**. On ugcpu2 (8×3090, conda env `gov`), never evict
  another user's process/GPU.

---

## Where things live

- **v5 review**: `paper/revision_v5/DEFECT_LOG.md` (tracking file),
  `GOAL_UGCPU2_V5.md` (GPU dispatch).
- Config/rules: `governor_v2/protocol_v2.json`, `make_protocol_v2.py`,
  `generated/candidate_rules_v2.jsonl` (gitignored, regenerable),
  `generated/problem_ids/<bench>__{train,dev,test}.txt`,
  `generated/split_manifest.json`.
- Sweep/select/confirm: `governor_v2/replay_rules.py` (sweep+select),
  `select_v2.py`, `confirm_v2.py`, `deer_threshold_sweep.py`,
  `deer_heldout_sweep.py`, `heldout_confirm.py`, `dense_probe.py` (probe
  collector — G1 extends this).
- Result bank (committed): `results/governor_v2_ws_sweep/` — `dev/`, `test/`,
  `heldout_test/`, `deer/`, `manifest.json`, `report.md`. Frozen trajectories
  and probe banks: `results/governor_v2/<phase>__<model>__<bench>__seed_NN/`
  with `main/traj/`, `dense_simple32/`, `adaptive_simple32/`.
- DEER confidence banks: `results/related_work/deer_confidence_bank_cap30/`
  (dev) and `..._heldout/`.
- Human labels: `results/human_eval/` and `results/human_eval/adjudicated/`.
- Analysis scripts (CPU, read committed banks, deterministic) in `report/`:
  `make_v3_figures.py` (the five data figures), `compute_harm_rescue.py`
  (+ `_null.py`, new in v5), `compute_consensus_position.py`,
  `compute_probe_wording.py`, `compute_diversity_contrast.py`,
  `compute_consensus_deer_{combo,disjunctive,tiered}.py` (excluded add-ons),
  `make_generalization_figs.py`.
- Narrative source of truth: `CORE_PAPER_FLOW.md`. Ignore
  `PAPER_REVISION_V2_GOAL.md` and `paper/revision_v2/` (superseded).
- v3/v4 planning docs under `paper/revision_v3/` and `paper/revision_v4/` —
  historical; `REVIEW_ISSUES.md` and `BIG_ISSUES_ROUND2.md` are all resolved.

### The harm:rescue slice, recorded because it had to be recovered by search

§4.4's published curve uses **one rule per W**: `consensus_fixed`, s = 1.0,
probe interval 128, maturity floor 512, schema validity, certainty off, with W
the only axis varying. `compute_harm_rescue.py` reproduces 45.1:1 / 668 stops at
W=1 and 2.0:1 / 121 stops at W=30 exactly.

---

## Figures

Main body: `fig1_idea` (§1) · `fig_wording_taxonomy` (§4.2/4.3) ·
`fig_harm_rescue` (§4.4). Appendix: `fig_consensus_pos`, `fig_ws_heatmap`,
`fig_split_transfer`, and the per-model/per-benchmark Pareto figures.

- **Figure 1 has text baked into a pptx** and does *not* follow `.tex` edits.
  Source `paper/revision_v3/make_fig1_idea.py` → `fig1_idea.pptx` → pdf:
  ```bash
  python3 paper/revision_v3/make_fig1_idea.py --no-pdf
  cd /tmp && mkdir lo && cp .../fig1_idea.pptx /tmp/lo/ && cd /tmp/lo
  HOME=/tmp/lo soffice --headless -env:UserInstallation=file:///tmp/lo/prof \
    --convert-to pdf --outdir /tmp/lo fig1_idea.pptx
  ```
  (the script's own `to_pdf` fails because `soffice` needs a writable HOME and a
  private profile.) Antony **rejected five alternative Figure-1 concepts**
  (`paper/revision_v3/concepts/`); do not redesign unasked.
- `fig_wording_taxonomy` panel (a) reads the cleaned `probe_wording.json`
  (11 bins), panel (b) the adjudicated taxonomy CSV. Both via
  `report/make_v3_figures.py`. **G1 will replace panel (a)'s data.**
- **Appendix float packing**: `acl_latex.tex` relaxes the float fractions and the
  six appendix figure blocks sit at the head of their section. If you add or
  resize an appendix figure, re-check pages 12–16 visually.
- **Known cosmetic issue, not fixed:** Figures 7, 8, 9 have a small grey title
  line baked into the image that duplicates the caption. Removing it means
  re-running `report/make_generalization_figs.py`.
- Long explanatory text lives in captions, not inside figures:
  `paper/revision_v3/CAPTIONS.tex`.

---

## Build, install, run

```bash
# package + grader deps (REQUIRED before any replay — see D6)
pip install -e . regex latex2sympy2 "antlr4-python3-runtime==4.7.2"

# paper
cd paper && pdflatex -interaction=nonstopmode acl_latex.tex \
  && bibtex acl_latex && pdflatex acl_latex.tex && pdflatex acl_latex.tex

# tests
python -m unittest benchmark.FalseConsensus.governor_v2.tests.test_governor_v2
python -m unittest discover -s benchmark/FalseConsensus/related_work/tests

# reproduce the v2 sweep (CPU; probe banks required), from the repo root
python -m benchmark.FalseConsensus.governor_v2.replay_rules sweep \
  --protocol protocol_v2.json --rules generated/candidate_rules_v2.jsonl \
  --split-manifest generated/split_manifest.json \
  --results-root ../results/governor_v2 --phase development \
  --shard-index I --shard-count 10 --output shard_I.jsonl
```

The ACL body had to end on page 8 for submission; **that constraint is gone for
the preprint.** No `poppler`/`pdftoppm` locally — render pages for visual QA with
PyMuPDF:
`python3 -c "import fitz; fitz.open('acl_latex.pdf')[0].get_pixmap(matrix=fitz.Matrix(2.2,2.2)).save('/tmp/p1.png')"`

## Working conventions

- After noteworthy progress, update **both `log.md` and `plan.md`**. Convert
  relative dates to absolute.
- Numbers in the paper come from committed banks; when changing analysis code,
  regenerate the affected `report.md`/figures rather than hand-editing numbers.
- Commit when asked; end commit messages with the `Co-Authored-By` /
  `Claude-Session` trailers. Work on `v5-preprint`.
- If a number looks wrong, investigate it rather than reporting it with a
  caveat. Every figure in this repo has at some point been wrong in a way a
  careful reader would have caught.
