# CLAUDE.md

Guidance for Claude Code working in this repo. **The "v4 paper state" section
below is the primary handoff — read it first.** Then "v3" for how the argument
got its present shape, and "v2" for the experimental machinery, which is
unchanged since 2026-08.

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

## v4 paper state (READ FIRST — handoff, 2026-08-07)

**The paper has been submitted to ARR and the deadline has passed.** Nothing in
the submitted PDF can be changed. Work in this repo now targets the *next*
version (camera-ready, rebuttal, or resubmission). Do not "fix" things in a
panic — see "Known defect in the submitted PDF" below for the one issue that
matters and the decision already taken on it.

### Branch and push state

Working branch **`v4`**. Three commits are **local only** — the agent sandbox
has no GitHub credentials (no `gh`, no token, no SSH key, no credential helper),
so `push` fails with `could not read Username`. Anonymous HTTPS *fetch* works:
`git -c url."https://github.com/".insteadOf="git@github.com:" fetch origin`.

```
9ae683ad  paper: replace non-existent preregistration reference with Nosek et al. 2018 PNAS
de7e2fda  paper: align Fig. 2(a) caption with the figure's own last-bin annotation
d24ad869  paper: rename gap to consensus--termination, new title, DEER-contrast scope, appendix float packing
```

Push from the host (stale locks the sandbox cannot unlink may need removing
first):
```bash
cd ~/code/Governor && rm -f .git/index.lock .git/ORIG_HEAD.lock && git push origin v4
```

### Known defect in the submitted PDF — decision already made

`custom.bib` carried a **fabricated stub entry** since the very first scaffold
commit `6f7f5181`: `preregistration_ml` = "Preregistration in Machine Learning
Research", Nosek et al., *arXiv preprint*, no identifier. **No such paper
exists.** It renders in the submitted PDF as `(Nosek et al., 2025)` on p6 and in
the References on p10.

Scope: it is the single citation supporting the *methodological* statement that
the sweep was preregistered. It backs **no** empirical claim, number, or result;
deleting it changes no argument.

Fixed in `9ae683ad` by replacing it with the canonical reference — Nosek,
Ebersole, DeHaven & Mellor, *The preregistration revolution*, PNAS
115(11):2600–2606, 2018, doi:10.1073/pnas.1708274114.

**Antony's decision: disclose honestly if a reviewer raises it**, and fix in
camera-ready. Do not re-litigate this. If asked to help draft the author
response, the honest framing is: a template stub survived to submission, it
supports no claim, the corrected version cites Nosek et al. (2018).

### Terminology — locked, do not drift

One term only. `stability` was deliberately **demoted** and is no longer a
keyword.

- **`self-consensus`** — the only formal name; defined in `01_introduction.tex`
  ¶1, which also declares the abbreviation.
- **`consensus`** — declared abbreviation, used throughout the body.
- **`agreement` / `agree`** — ordinary verbs, not terms.
- The concept is the **`consensus--termination gap`** (was
  `stability--terminality gap`; `terminality` was cut as a non-word).

**The core sentence must not become a tautology.** "Agreement establishes
consensus, not termination" is circular. The locked phrasing carries the meaning
with `persists`:

> repeated agreement establishes only that the current answer \emph{persists}
> under a fixed probing procedure, not that the reasoning has
> \emph{terminated}---a \emph{consensus--termination gap}.

Self-check after any edit — all of these must grep to **0** in
`paper/sections/*.tex` and `paper/acl_latex.tex`:
`terminality`, `probe stability`, `probe agreement`, `answer stability`,
`intermediate answer consensus`, `false consensus`, `positive control`,
`identical pipeline`.

`stable` / `settled` as ordinary adjectives describing a model or trajectory are
fine and were kept.

### Structure and freeze status

Body order: §1 Intro → §2 Related Work → §3 Experimental Setup → **§4 The
Consensus–Termination Gap** (measurement first) → **§5 The Gap Cannot Be Tuned
Away** (sweep, DEER, CertaIndex, generalization) → §6 Conclusion → Limitations.
Appendices A–F then G (`03_false_consensus.tex`, *Self-Consensus: Full
Analysis*).

Antony read and **froze**: title, abstract, §1, §2, §3, §4, §5, §6, Limitations.
The appendix was not line-read; only its figure placement was reworked.

Note the deliberate inversion: the **abstract is result-first** (sweep → DEER →
reason), the **body is mechanism-first**. §4's opening carries an explicit
bridge sentence so this is visibly intentional. Do not "fix" it.

### Claim-scoping decisions that cost real effort — do not undo

1. **harm:rescue is a range, not a headline.** Abstract, intro and conclusion say
   **2–45×**, never "up to 45×". 45:1 is `W=1`, which comes with a 65.9 pp drop
   and 92.3% saving — an operating point nobody deploys, and a reviewer who
   checks will discount the number. The intro puts the contrast in the same
   breath: the 2× end buys only **7.9%** net saving, whereas DEER holds
   **2.4–3.5×** while saving **28–32%**. §4.4 and the figure caption keep 45:1
   because they sit in the full-curve context.
2. **The DEER contrast is not a one-factor ablation.** DEER also differs in
   *when* it reads (reasoning boundaries vs. fixed schedule) and *what* it
   commits (trial answer vs. probe answer). §5.7 ("Locating the Failure") now
   carries this as a **fourth qualification**, and the section no longer says
   "what separates them is the signal" — it says the failure lies in how the
   stop is decided rather than in early exit. §5.1's subhead lost the word
   "identically". This was the paper's weakest inference; keep the hedge.
3. **Two-layer result, not a transfer-only story.** Earlier drafts framed the
   finding as "a selected policy does not transfer". That *understates* it: **0
   of 3,520 rules clear any gate on dev itself**, so nothing is ever selected.
   The 478 train in-sample winners are the second layer. Abstract and intro now
   state both.
4. **Factual trap, previously wrong, now fixed:** the 478 in-sample winners do
   **not** fail on test — **364 of them clear the conservative gate on test**
   (444 rules clear it on test overall). What is empty is **dev** (0) and
   **dev∧test jointly** (0). Never write "they survive on neither dev nor test".
5. **Taxonomy provenance stays out of the paper.** The A/D disagreement arose
   because one annotator read A as "any wrong numeric early stop"; Antony
   resolved all A/D conflicts to D under a fixed rule. That is legitimate and
   the rubric history is **deliberately absent** from the paper. Do not
   reintroduce it. The paper reports the committed adjudicated record and
   describes κ accurately as computed on the top-level coding.

### Numbers as they now stand (all re-verified against committed banks)

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
| sweep | 40 rules ≤1.0 pp, best saves 0.21%; 10/20/30% saving costs 2.66 / 6.17 / 11.76 pp | dev sweep archive |
| generalization | r=0.98 dev↔test, 0.97 32B, 0.94 Llama; 478 / 0 dev / 444 test / 364 overlap / 0 joint | `test/`, `heldout_test/` |
| gross vs net | 14.9/10.9 and 27.0/20.2 | recomputed |

`tab:deer` (14 thresholds), `tab:baselines`, §4.1's four facts, and the three
case-study probe streams (pid 68, 320, 253, 240) were all verified earlier and
are unchanged. **pid 240 fires at token 384, not 192** — that was a bug, fixed.

### Citations — audited 2026-08-07

All 18 cited entries checked title ↔ arXiv ID ↔ authors ↔ year against arXiv
pages and web search. **All correct** after the `preregistration_ml` fix.

- The **Semantic Scholar API is unreachable from the sandbox** (`.env` holds
  `S2_API_Key`, but outbound `curl` returns `http=000` — network is allowlisted).
  Use `mcp__workspace__web_fetch` on `arxiv.org/abs/<id>` plus `WebSearch`
  instead; that combination was sufficient.
- One optional nit: `dynasor_certaindex` (arXiv:2412.20993) uses the v1 title
  *Efficiently **Serving** LLM Reasoning **Programs** with Certaindex*; arXiv now
  lists it as *Efficiently **Scaling** LLM Reasoning with Certaindex*.
- `custom.bib` has 9 uncited orphan entries (`tje`, `ross1977false`,
  `wei2022cot`, `guo2017calibration`, `snell2024scaling`, `brown2024monkeys`,
  `kadavath2022know`, `kuhn2023semantic`, `huang2024selfcorrect`). Harmless —
  BibTeX only emits cited entries. `tje` and `ross1977false` went orphan when the
  TJE baseline row and the false-consensus footnote were removed.

### Figures

**Figure 1 has text baked into a pptx** and does *not* follow `.tex` edits.
Source `paper/revision_v3/make_fig1_idea.py` → `fig1_idea.pptx` → pdf. Current
state: panel (a) "Agreement ≠ termination"; badge "harm : rescue 45:1 → 2:1";
panel (c) "Early exit is not the problem"; banner "Early exit is possible —
*self-consensus* is what cannot make it safe". Regenerate with:

```bash
python3 paper/revision_v3/make_fig1_idea.py --no-pdf
cd /tmp && mkdir lo && cp .../fig1_idea.pptx /tmp/lo/ && cd /tmp/lo
HOME=/tmp/lo soffice --headless -env:UserInstallation=file:///tmp/lo/prof \
  --convert-to pdf --outdir /tmp/lo fig1_idea.pptx
```
(the script's own `to_pdf` fails because `soffice` needs a writable HOME and a
private user profile; convert in `/tmp`, then copy the pdf back.)

`fig_wording_taxonomy` panel (a) uses the **cleaned** `probe_wording.json`
(11 bins) and panel (b) reads the **adjudicated** taxonomy CSV. Both via
`report/make_v3_figures.py`.

**Appendix float packing.** `acl_latex.tex` now relaxes the float fractions
(`\dblfloatpagefraction` 0.85 etc.) and the six appendix figure blocks were moved
to the head of their section. Before this, pages held one figure each; now
Figure 6 lands on p13 instead of p15 and there are no float-only pages. If you
add or resize an appendix figure, re-check pages 12–16 visually.

**Known cosmetic issue, not fixed:** Figures 7, 8, 9 have a small grey title
line baked into the image that duplicates the caption. Removing it means
re-running `report/make_generalization_figs.py`.

### Build

Body must end on **page 8** (ACL limit; Limitations is unnumbered and does not
count). Currently p9 starts with "Limitations" — **this is tight, within a line
or two.** Any addition needs a compensating cut. 16 pages total, 0 undefined
refs/citations.

The sandbox **cannot install `inconsolata`** (no root). Compile there with
`sed -i 's/^\\usepackage{inconsolata}/%&/'` on a copy in `/tmp`; page breaks
matched the real build exactly when last compared, but **always rebuild on the
host before anything final**.

### Review artefacts

- `paper/revision_v4/REVIEW_ISSUES.md` — round 1 (A1–A13 from Antony, B1–B13
  from the data audit). All resolved.
- `paper/revision_v4/BIG_ISSUES_ROUND2.md` — round 2 (terminology, title, 45×,
  DEER scope, transfer framing). All resolved.
- `paper/REVIEW_ISSUES.md` — a copy of round 1 committed by the teammate.

### What is still open

1. **Pooled robustness check** (carried over from v3, still not done). The
   negative result leans on dev, where the same 478 train winners have median
   drop 4.50 pp vs 0.62 pp on test, traced to Qwen3-8B AMC23 (n=8) and AIME24
   (n=6) carrying equal macro weight. Recompute the headline gate **pooled over
   problems** as a robustness check. The protocol mandates macro, so pooled is
   reported as a check, never a substitution.
2. Repo hygiene: `paper/` still contains upstream ACL template files that would
   ship in a submission tarball — `acl_latex_template.tex`, `acl_lualatex.tex`,
   `formatting.md`, `anthology.bib.txt`, `tests/regression/run_tests.py` (that
   test targets `acl_natbib.bst` author formatting, unrelated to this paper).
   `paper/README.md` was clobbered by the upstream README once and has been
   restored; check it survived.
3. Possible rebuttal work: the two single-environment diagnostics (§4.2 wording,
   §4.3 taxonomy) are the most attackable parts. A genuine two-model wording
   experiment needs a **fresh un-truncated paired probe collection on GPU** —
   see the v3 note about why `probe_prompt_ablation/certaindex32` cannot be used.

### Sandbox limitations you will hit

- **Cannot `unlink` on the mount.** `git checkout`, `merge`, `commit` all fail
  partway. Workarounds that work: overwrite files in place with
  `git show HEAD:path > path`; set `export GIT_INDEX_FILE=/tmp/idx` +
  `git read-tree HEAD` + `git add`; commit via
  `git write-tree` → `git commit-tree` → write the SHA into
  `.git/refs/heads/<branch>` directly. Stale `.git/*.lock` files accumulate and
  must be removed from the host.
- **No GitHub credentials.** Fetch anonymously over HTTPS; push from the host.
- **Network is allowlisted.** `arxiv.org` works via `web_fetch`; arbitrary API
  hosts do not, from either `web_fetch` or `curl`.
- `libreoffice`/`soffice` and `python-pptx` **are** available; `pymupdf` installs
  with `pip install pymupdf --break-system-packages`.

---

## v3 research state (superseded by v4 for the paper; still the record of how the argument was built)

The v2 sweep and all frozen banks are **unchanged**. What changed in v3 is the
*argument*: the paper was restructured from "we searched exhaustively and found
nothing" to "here is **why** agreement cannot work alone, and no tuning escapes
it". v4 kept this shape and then renamed the terminology, rescoped the DEER
contrast, and fixed the numbers — read the v4 section for anything that
disagrees with what follows.

Branch history: `v3-mechanism-figures` (`bcc6a494`, `85b03059`) was merged into
the current `v4` line; a parallel teammate rewrite lives on `origin/main` and
`origin/v3-stability-terminality`. **`v4` is the live branch.**

### The claim, stated precisely

**Intermediate answer consensus cannot serve as an early-exit signal *on its
own*.** Three deliberate boundaries on that claim:

1. **"On its own" is load-bearing.** We do *not* claim agreement is worthless.
   It is cheap and it does report that the current answer has not changed.
   Combined with a signal that reflects the model's own estimate it may well be
   useful; CertaIndex composes multiple indicators for related reasons. What we
   rule out is treating agreement, alone, as evidence that reasoning has
   finished. §5.7 and the conclusion both say this explicitly — do not let an
   edit collapse it back into "consensus does not work".
2. **Consensus never claimed to raise accuracy.** Its goal is to save tokens
   *without losing* accuracy. So the interesting failure is not "it adds no
   information" — it is that it provides **no backstop**: when a stop is wrong,
   nothing catches it.
3. **We are not attacking CertaIndex.** It happens to use the signal we study.
   Tone is neutral throughout; see "CertaIndex framing" below.

### The mechanism (this is the contribution)

Three layers, in the order §5 presents them.

**(a) No independence, therefore no backstop.** Self-consistency's majority vote
can absorb an error because its paths are sampled *independently* — a wrong
answer on one path is outvoted by others that reasoned differently. Probing one
trajectory yields nothing of the kind: every probe reads the same prefix, so the
readings move together, and a majority over them cannot correct anything. This
is an argument, not an experiment, and that is fine — it is obvious once stated
and does not need to be belaboured.

**(b) What the probes agree *on* is usually a forced placeholder.** 134
hand-labelled stopped-but-wrong cases, two annotators, κ = 0.82:

| category | share | n |
|---|---|---|
| unconverged guess / placeholder | 59.7% | 80 |
| converged on a wrong value | 20.1% | 27 |
| probe format artifact (option letter etc.) | 17.2% | 23 |
| other (expression collapse, sign error) | 3.0% | 4 |

Only one stop in five is the model being wrong about something it had actually
decided. A probe does not *read* a belief, it *forces* an output; a model that
has not finished writes down what it wrote last time.

> **Annotation provenance — do not put this in the paper.** The two annotators
> originally disagreed badly on A vs D because the rubric was unclear (one read
> A as "any wrong early stop"). On review, most A-labelled cases were *not*
> converged. The record therefore uses **annotator 1's** A/D reading, where A is
> reserved for genuinely settled wrong values. κ = 0.82 is computed on the
> coarse coding both annotators share (settled-or-not / format / other). The
> rubric history is deliberately absent from the paper — do not reintroduce it.

**(c) A longer window does not fix it.** harm:rescue falls 45:1 → 2:1 across
W ∈ {1..30}, but net saving falls 92% → 8% and stops fall 668 → 121. The long
window works by *not firing*. And it cannot outlast a placeholder that persists
longer than the window — see case pid 320 below.

**Rejected framing (do not reinstate):** the parent/child analogy ("a child
asked repeatedly what they want to be") was cut by the user. Keep it out.

### Supporting experiment: probe wording versus position

Direct evidence for (b), on committed data, no GPU.
`report/compute_probe_wording.py` → `figures/gen/probe_wording.json`.

At every probe position the same frozen prefix was read with two suffixes:
- `simple`     = `**Final Answer**\n\n\[ \boxed{`
- `certaindex` = `... Oh, I suddenly got the answer to the whole problem, **Final Answer**\n\n\[ \boxed{`

Semantically near-identical; the CertaIndex one only prepends a commitment
nudge. **Say it that way** — "two neutral paraphrases" would be inaccurate,
because that preamble does push toward committing.

**Cleaning matters and is now baked into the script.** The paired bank only
re-probes to token 3072, so any trajectory longer than that has an unprobed tail
and its "position as % of length" is meaningless in late bins. Dropping those
(140) plus trajectories that hit the budget instead of finishing (19) leaves
**241 of 400 problems, 2,898 comparable positions**. Before cleaning the curve
was flatter and overall agreement read 66.7%; after, 76.0%.

| position (% of trajectory) | n | two prompts agree | probe correct |
|---|---|---|---|
| 0–5 | 34 | 41.2% | 17.6% |
| 5–10 | 179 | 47.5% | 24.0% |
| 10–15 | 161 | 59.6% | 28.6% |
| 15–20 | 150 | 52.7% | 37.3% |
| 20–30 | 340 | 60.6% | 43.8% |
| 30–40 | 316 | 69.6% | 56.6% |
| 40–50 | 325 | 82.2% | 70.8% |
| 50–60 | 321 | 87.9% | 76.0% |
| 60–70 | 299 | 87.6% | 79.9% |
| 70–85 | 422 | 90.3% | 81.8% |
| 85–100 | 351 | 88.6% | 80.9% |
| **overall** | **2,898** | **76.0%** | |

Reading: early on, two near-identical questions get different answers about half
the time; by the end they agree ~90%. If the model held a stable-but-wrong
belief early, both wordings would read back the *same* wrong value — they do
not. Use the **5–10% bin** as the "early" number in prose; the 0–5% bin is only
n = 34 because short trajectories have 1–2 probes there.

**Scope, must be stated wherever this is used:** DeepSeek-7B × MATH500 ×
seed 42, a **single environment**, not the 18-environment dev set. It is a
*supporting observation*, not a headline result.

**Do not try to extend this to two models with
`probe_prompt_ablation/certaindex32`.** That bank is **stop-truncated** (median
5 probes per problem, max position 320) because it is a CertaIndex replay that
halts at its own stop rule. Position-binned analysis on it is severely
selection-biased and produces a flat, meaningless curve. Verified and rejected
2026-08-04. A genuine two-model version needs a fresh un-truncated paired probe
collection (GPU).

### §5 case studies (main body §5.5, ~260 words; full version Appendix F)

All DeepSeek-7B / MATH500 / seed 42, probes every 64 tokens. `a×n` = answer
repeated over n consecutive probes.

- **pid 320** (gold −24/25). Stream `0×27, B×8, -24/25, B×7, E, B×6, -24/25×7`.
  Answers `0` at the **first** probe and holds it for 27 probes — nearly half a
  3,683-token trajectory — then reaches the correct value. The single best case
  in the paper: a placeholder emitted before any real work, perfectly stable,
  and long enough that **even W=24 fires and commits it**. This is the direct
  answer to "why not just use a bigger window".
- **pid 253** ("What fraction of 2 feet is 3 inches?", gold 1/8). Stream
  `3, B, 3, 24, B, D×20, 1/8`. Twenty consecutive probes return the letter `D`
  on a problem with no options. Agreement total, referring to nothing.
- **pid 240** (gold 116). Commits `52` at token 192; the trajectory ends at
  `154`. Both wrong — the honest minority case where stopping destroys nothing,
  which is the regime consensus was designed for. Included deliberately.

### CertaIndex framing (agreed wording — do not drift)

- Always write **CertaIndex (CoT)**, never bare "CertaIndex".
- We reproduce **the released Dynasor implementation at its default `mid`
  setting** (`dynasor/core/cot.py @ dbe76ad`; three consecutive equal non-empty
  probes, none hedging). `tab:baselines` is sourced from
  `related_work/certaindex_mid.py` + `results/related_work/certaindex_effort_bank/`
  (dedicated probes, 36 env, 3,420 problems) — **not** the adapted
  `governor_v2/replay_certaindex.py`, whose own docstring admits it is not the
  faithful prompt/cap configuration.
- **Their multi-path setting is ordinary self-consistency** (entropy over
  independently sampled trajectories) and nothing here bears on it. Our critique
  is confined to transplanting that statistic onto a single trajectory's
  iterations. §4.4 states this in two scope notes — keep them.
- No "collapse" / takedown language. Preferred phrasing: *the shipped default
  lands where the swept frontier says a rule at that stop rate must land.*
- We are **not** adding the paper's H̃-threshold variant. Decided: the
  released-implementation reproduction is enough.

### Exploratory experiments deliberately NOT in the paper

Full record: `paper/revision_v3/CONSENSUS_ADDON_EXPERIMENTS.md`. All run on
DEER's own boundary-trial stream, dev split, 18 environments, DEER baseline
reproducing the committed bank exactly.

1. **Conjunctive** (`conf > τ` AND last-W agree): 0/20 Pareto-dominate DEER.
   Agreement can only *delay* a stop.
2. **Disjunctive two-threshold** (`conf > τ_hi` OR (`conf > τ_lo` AND W agree)):
   extends the frontier — at the balanced gate, *identical* drop (1.944 pp) with
   **+3.79 pp more saving**. Optimal τ_lo is high (0.93–0.99), and branch A still
   does 75–90% of the work, so the honest reading is "agreement is a second-order
   refinement on a confidence signal, not a stop signal".
3. **k-tier**: k ≥ 3 does **not** beat k = 2 (+0.00/+0.08/+0.00 pp). At a matched
   floor τ = 0.93, stop accuracy *falls* with run length (0.785 → 0.668 → 0.538)
   and harm:rescue rises (3.39 → 5.16 → 9.67) — longer agreement runs at fixed
   confidence select *worse* boundaries.

**Why excluded:** all dev-only, winners chosen across 36 + 224 + 470 points with
no frozen operating point confirmed on test. Including them would hand a reviewer
a "you tuned on dev" attack. **If ever included**, freeze the balanced point
(τ_hi .995 / τ_lo .93 / W3 — the only one with drop exactly matched to DEER) and
confirm on test seeds 45/46/47 first.

**Grid-fairness trap worth remembering:** the k-tier sweep initially showed a
spurious +1.6–4.0 pp advantage for k=3 purely because k=2 was not allowed the
same low floor range. Always give the shallower configuration the same grid.

### Paper structure as it now stands (18 pp, compiles clean, 0 undefined refs)

- **§1** phenomenon → exhaustive sweep → *then* why → DEER control. The
  mechanism deliberately does **not** open the introduction; the user asked for a
  gradual build. Do not move the self-consistency argument or the annotation numbers
  back to the front.
- **§2** adds "Where agreement gets its meaning" — self-consistency's
  independence premise, and the term **self-consensus** for the single-trajectory
  case. This paragraph is the foundation for §5; keep them consistent.
- **§4** repositioned as the *exhaustive check*, not the centrepiece:
  Non-Terminal Agreement / Sweep Results / A Non-Consensus Signal /
  CertaIndex (CoT) at Its Default / Generalization.
- **§5** The Role of Independence / Probe Wording versus Position / Error
  Taxonomy / Effect of Window Size / Case Studies / Probe-Independence of the
  Accuracy Cost / Accuracy Tax versus Probe Tax / Locating the Failure.
- **Appendix** A schema · B preregistration · C reproducibility · D DEER
  threshold frontier · E per-model/per-benchmark Pareto (the three old figures)
  · F case studies · G false-consensus full analysis.
- **Subsection titles are ACL-style short noun phrases.** The previous
  sentence-claim titles ("The failure is the signal, not early exit") read as
  AI-generated. Keep noun phrases.

### Figures

Main body: `fig1_idea` (§1) · `fig_consensus_pos` (§4.1) · `fig_ws_heatmap`
(§4.2) · `fig_split_transfer` (§4.5) · `fig_harm_rescue` (§5.4) ·
`fig_taxonomy` (§5.3). Appendix E holds the three old Pareto figures.

- Figure 1 has **two variants**, both editable pptx + pdf:
  `fig1_idea` (3-panel: phenomenon / sweep / control — **the user prefers this
  one**) and `fig1_idea_b` (5-stage pipeline). Sources
  `paper/revision_v3/make_fig1_idea*.py`.
- The user reviewed and **rejected five alternative Figure-1 concepts**
  (`paper/revision_v3/concepts/`, script `fig1_concepts.py`): zoned pipeline,
  decision flowchart, trajectory hero, twin funnels, scorecard. Redesign was
  **deferred** — do not spend time on it before the deadline.
- Long explanatory text lives in captions, not inside figures:
  `paper/revision_v3/CAPTIONS.tex`.
- Data figures: `report/make_v3_figures.py`.

### Open TODOs

1. **Pooled robustness check.** The negative result leans on dev, where the same
   478 train-winners have median drop 4.50 pp vs 0.62 pp on test, traced to
   Qwen3-8B AMC23 (n=8) and AIME24 (n=6) carrying equal macro weight. Recompute
   the headline gate **pooled over problems** as a robustness check. The protocol
   mandates macro, so pooled must be reported as a check, never a substitution.
   §4.5 already states the asymmetry openly.
2. **Page budget.** Body is 11 pp against ACL's 8. The user plans to cut
   redundancy rather than drop content; §5.5/§5.6 and §4.1 overlap most.
3. Wire `probe_wording` into §5.2 with its scope caveat (table above is ready).
4. Push the branch (see top of this section).

---

## v2 research state (experimental machinery — unchanged)

Ground-truth narrative: `CORE_PAPER_FLOW.md` (5 beats). The v2 rewrite (2026-08)
replaced the v1 sweep and rewrote the paper to match it.

### The story (what the paper argues)
*Superseded in emphasis by the v3 section above — beats 1–4 are unchanged, but
beat 5 (mechanism) is now the contribution rather than a closing remark, and the
claim is scoped to consensus used* alone.

1. **False consensus is real**: intermediate probe agreement is *not* terminal —
   the answer is often still moving. `agreement != correctness`.
2. **Can any consensus rule be safe *and* saving?** A preregistered Pareto sweep
   over the consensus-signal space.
3. **No.** Not one consensus rule clears any acceptance gate (the central
   negative result).
4. **But early exit itself is possible**: swept through the *identical* pipeline
   and gates, **DEER** (a boundary-confidence signal, not consensus) clears all
   three gates. So the failure is the *signal*, not early exit.
5. **Mechanism**: consensus stops fire while the answer is still moving, so they
   destroy far more correct-in-the-end answers than they rescue wrong ones (a
   directional "accuracy tax"), and this is a systematic risk — *not* a universal
   impossibility theorem (do not overclaim beyond the searched space).

### The v2 rule space (unified two-hyperparameter consensus signal)
The consensus signal collapses to **window size `W`** (`evidence.window_probes`)
× **share threshold `s`** (`evidence.dominant_share_threshold`), expressed with
the `window_share` evidence family (`W=1` == latest probe; `s=1.0` == the last
`W` probes all agree). The old v1 families (`latest_persistence`, `entropy`,
standalone `persistence`, `history`) were dropped/merged.
- Config: `governor_v2/protocol_v2.json` (generated by `make_protocol_v2.py`).
- Two families (differ only in probe schedule): `consensus_fixed` (interval ∈
  {64,128,256,512}) and `consensus_adaptive` (event-triggered).
- Axes: W ∈ {1,3,5,8,12,16,24,30}, s ∈ {0.6,0.8,1.0}, maturity min_tokens ∈
  {0,512,1024,2048,4096}, validity ∈ {nonempty,schema}, certainty ∈ {off,on}.
- **3,520 rules** (after dropping behaviourally redundant `W=1, s≠1.0`).
- Semantics fix (important): in `replay_rules.evidence_candidate`, `window_share`
  measures share over the **full window of W probes** (empties/dissent count
  against; window must be full) — so `(W,s)` means "s of the last W probes agree".

### The gates (v2) — first drop, then saving, then psf
Applied in order on the **dev** split, all **macro-averaged over the 18
environments** (2 dev models × 3 benchmarks × 3 seeds):

| point | max total acc drop | min total net saving | psf |
|---|---|---|---|
| conservative | 1.0 pp | 10% | 0.80 |
| balanced | 2.0 pp | 20% | 0.80 |
| token_efficient | 3.5 pp | 30% | 0.70 |

The min-saving floor rejects "safe only because it never stops" rules.

### Headline results (dev, macro over 18 env, robust grader)
- Consensus: **0 / 3,520 rules clear any gate.** drop≤1.0pp → max saving 0.2%;
  saving≥10% → drop 2.66pp; ≥20% → 6.17pp; ≥30% → 11.8pp. Large windows only
  trade drop for ~zero saving.
- DEER (trial-answer-submit, threshold sweep): clears all three —
  conservative τ0.995 (−0.33pp @ 28.2%), balanced τ0.99 (1.03pp @ 29.6%),
  token_efficient τ0.97 (2.75pp @ 31.9%); accuracy-neutral τ0.9999 (−0.06 @ 20.8%).
- Full-generation baseline 82.5% (matches DEER baseline — grader fix, see below).

### Mechanism numbers
- harm:rescue (recovery destroyed : wrong banked) is **window-dependent**:
  ~45:1 at W=1 down to ~2:1 at W=30 — but the low end only comes with near-zero
  saving (W=30 fires on 121 dev problems vs 668 at W=1). DEER holds ~2.4–3.5:1
  *while* saving 28–32%. **Unified phrasing (2026-08-03, issue 1)**: abstract,
  intro, conclusion, and §5 all now say "up to **~45× at an aggressive
  latest-probe stop, ~2× at the largest windows**" — W=1 is explicitly labeled
  *latest-probe* so the big number is not read as a representative consensus value.
  The old bare "35×" is gone.

### Generalization (all on the TEST split — that is the point)
- Held-out test split (dev models, seeds 45/46/47): consensus drop dev↔test
  **r=0.98**; joint conservative gate empty for consensus (0 dev, 444 test-only
  in-sample winners, 0 both); DEER clears both splits.
- Unseen **scale** Qwen-32B (**r=0.97**) and **architecture** Llama-8B
  (**r=0.94**), 3 test seeds each: conservative gate empty for consensus on every
  model; **DEER clears the gates on both unseen models** (32B −0.24pp @ 32.4%,
  τ0.97; Llama 0.67pp @ 26.7%, τ0.99). Scale effect: on 32B a few consensus rules
  pass looser gates in-sample, but they are not dev-selected.
- **Oracle** upper bound (earliest correct probe): on the **test panels shown**
  (fig_models/fig_bench) −2 to −5 pp drop @ 40–80% saving — far in the safe corner
  neither method reaches (headroom). (The old "−10 pp @ 40–60%" was a **dev-only**
  value / understated saving; corrected 2026-08-02, verified in
  `results/governor_v2_ws_sweep/report.md` "Paper-number verification".)
- Faithful CertaIndex reproduction collapses by 56–70pp (consensus in the wild).

### Figures (main body, `paper/figures/gen/`)
- **Figure 1** = `fig_splits` (train/dev/test): consensus train-gate winners
  (orange) leave the gate on dev/test; the 3 DEER operating points (C/B/T) stay
  in it; oracle star. Replaced the old single-panel dev-Pareto.
- `fig_models` (2×2: two dev models top on test split, two held-out below) and
  `fig_bench` (3 benchmarks, test) in §4.5. All plot consensus cloud+frontier,
  DEER frontier + C/B/T stars, oracle, gate boxes.
- Regenerate: `report/make_generalization_figs.py` (oracle cached in
  `report/figures/gen/oracle_cache.json`); then copy the PDFs to `paper/figures/gen/`.
- **Figures are being overhauled (issues 7 & 8, another agent)**: all ~10 panels
  are the same saving×drop Pareto — issue 7 diversifies them; issue 8 adds a new
  Figure-1 idea/schematic. Spec: `paper/revision_v3/figure_prompts.md`. Until then
  the three Pareto PDFs above are current.

### Paper review progress (section-by-section v2 pass — COMPLETE)
Every section reviewed per-claim (credibility / strength / coherence / expression;
each substantive claim confirmed with the user before editing). **All of §1–§6 +
appendices done.** Compiles clean (**13 pp**, 0 undefined refs).
- **§4.1 rerun at 16K/32K (2026-08-03)**: the false-consensus phenomenon numbers
  were the deprecated 3072-token exploratory ones; re-run on the frozen main
  trajectories via `benchmark/FalseConsensus/false_consensus_16k.py` (robust
  grader, all 500 MATH500 ids = dev seeds 42/43/44 + confirmation seeds 45/46/47,
  1,500 trajectories; **descriptive only, does not touch the sweep or test
  commitment**). New numbers: fact1 cum 97.8% / win 90.4%; fact2 89.1% / 84.2%;
  fact3 91.0%→71.6%; **fact4 naive stop 1,477/1,500, 50.5% vs 90.7% = 40.2pp
  loss** (was 16.4pp @3072). Report: `results/governor_v2_ws_sweep/false_consensus_16k_report.txt`.
- **Abandoned DEER-inspired controller fully removed** (2026-08-03): the
  boundary-confidence fast-commit/verify "inspired" controller had limited effect
  (overlaps DEER) and is gone from the paper — deleted Appendix C
  (`08_boundary_confidence.tex`) and the orphan `07_baselines.tex` /
  `08_discussion.tex`. **DEER-as-positive-control is untouched** (that is core
  beat 4; do not confuse the two).
- **revision_v3 issues 1–6 done (2026-08-03)** — see `paper/revision_v3/issues.md`
  and `log.md` 续2: (1) harm:rescue unified; (2) intro ¶2 split into three;
  (3) one-line train/dev/test flow in §3; (4) merged §5.4+§5.5, de-duplicated
  §4.3/§4.4/§5; (5) **TJE removed** from `tab:baselines` (data kept in
  `results/related_work/aggregate/report.md`: Qwen 85.0/−0.4/2.0%; DS 60.7/−19.1/65.0%);
  (6) subsection titles de-AI-ified.
- **Pending → issues 7 & 8 (figures), handed to another agent**: prompts in
  `paper/revision_v3/figure_prompts.md`. #7 = diversify the ~10 look-alike Pareto
  panels into distinct figure types; #8 = a new Figure-1 idea/schematic of the
  5-beat `CORE_PAPER_FLOW`, drawn in PowerPoint.
- `tab:baselines` (now CertaIndex/DEER, TJE dropped) verified 2026-08-02 vs
  `results/related_work/aggregate/report.md` (robust grader; two-model full-gen
  macro 85.4/79.8 → 82.6% ≈ 82.5% main baseline).

---

## Experimental details you MUST heed

- **Grader**: `replay_rules.answers_equal` must use `grading.robust_answers_equal`
  (it now imports robustly). A v1 bug silently used a weak grader when the sweep
  ran as a module from the repo root, under-counting correctness (MATH500 baseline
  78% vs true 92%). Confirm the robust grader is active (dev full-gen ≈ 82.5%).
- **Macro, never pooled**: every headline metric is macro-averaged over the 18
  environments (protocol: "macro-average environments; never problem-micro").
  Gates, figures, and paper numbers all use this.
- **Frozen trajectories**: main reasoning is generated once and frozen; all
  methods (consensus, DEER, oracle) are *replayed* offline against frozen prefixes
  using pre-collected probe banks. Never re-run main generation to add a rule.
- **Two token views**: `main_tokens_through_stop` (paper-style) and
  `all_generated_tokens` (fair: main + probe/trial output). Net saving charges
  probe/trial output; probe *prompt* tokens are reported separately, never added.
- **test read once**, after rules/thresholds are frozen; never tune on it.
  Llama-8B and Qwen-32B are **held out** (scale/architecture confirmation only).
- **DEER = trial-answer-submit** (commit the trial answer directly), the stronger
  variant; only hyperparameter is the confidence threshold. It is a positive
  control for the signal, not a SOTA claim, not the faithful readout.
- **DEER on 3090s needs NCCL env for TP>1**: `NCCL_P2P_DISABLE=1
  NCCL_IB_DISABLE=1 NCCL_NET_PLUGIN=none` (PCIe 3090, no NVLink). 32B TP=4 bf16;
  Llama TP=1.
- **Ġ/Ċ anomaly**: Llama-8B seed-45 confirmation `full_text` is stored with BPE
  metacharacters (Ġ=space, Ċ=newline); the DEER collector normalizes them at read
  time (no frozen-data mutation). Affects only Wait-boundary detection, not
  consensus (which reads probe banks + target).
- **Small sets are noisy**: AIME24/AMC23 have few problems/seed; use 3 seeds and
  macro. Single-seed held-out numbers are unreliable.
- **The grader is order-dependent — reset `latex2sympy2.var` before every call.**
  That library keeps a module-global `var` dict. Grading the MATH500 answer
  `"8thgradeshouldhave10representatives"` overwrites it with a bare `Symbol`;
  every later `latex2sympy` call then raises inside `symbolic_equal`, which
  **silently returns False** for expressions it would otherwise grade equal
  (e.g. `\frac{9a+11}{20}` vs `\frac{11+9a}{20}`). Correctness therefore depends
  on what was graded earlier in the same process. All v3 scripts do
  `latex2sympy2.var = {}` before each call. Audit of the dev baselines: **3 of
  684 verdicts affected (0.44%, one problem across three seeds), baseline
  89.33% → 89.77%** — conservative direction, committed banks stand, no re-run
  needed. Note this is *not* the "fresh process" effect it was first mistaken
  for; a subprocess only helps because it starts with a clean `var`.
- **Probe banks differ in whether they truncate at the stop.**
  `probe_paired_2x2` and `dense_simple32` probe on a fixed schedule regardless of
  stopping (usable for position-binned analysis). `probe_prompt_ablation/
  certaindex32` and the DEER confidence banks **halt at their own stop rule**
  (median 5 probes, max position 320) — position-binned analysis on them is
  selection-biased and invalid.

## Where things live

- Config/rules: `governor_v2/protocol_v2.json`, `make_protocol_v2.py`,
  `generated/candidate_rules_v2.jsonl` (gitignored, regenerable).
- Sweep/select/confirm: `governor_v2/replay_rules.py` (sweep+select),
  `select_v2.py`, `confirm_v2.py`, `deer_threshold_sweep.py`,
  `deer_heldout_sweep.py`, `heldout_confirm.py`.
- Result bank (committed): `results/governor_v2_ws_sweep/` — `dev/`, `test/`,
  `heldout_test/` (32B/Llama, 3 seeds), `deer/`, `manifest.json`, `report.md`.
- DEER confidence banks: `results/related_work/deer_confidence_bank_cap30/` (dev)
  and `..._heldout/` (32B/Llama).
- v1 sweep archived: `governor_v2/generated/backup_v1_sweep_20260802/` (gitignored).
- Figures: `report/make_generalization_figs.py`, `make_v2_pareto.py` →
  `paper/figures/gen/`.
- **v3 analysis scripts** (all CPU, read committed banks only, deterministic):
  - `report/make_v3_figures.py` — the five data figures.
  - `report/compute_harm_rescue.py` → `harm_rescue_cache.json`. Reproduces §5's
    published 45:1 → 2:1 and 668 → 121 exactly. The convention was undocumented
    and had to be recovered by search: **`consensus_fixed`, s = 1.0, probe
    interval 128, maturity floor 512, schema validity, certainty off**, with W
    the only axis varying. Record this if §5 is ever re-derived.
  - `report/compute_consensus_position.py` → `consensus_position_cache.json`.
  - `report/compute_probe_wording.py` → `probe_wording.json` (cleaning baked in).
  - `report/compute_diversity_contrast.py` → `diversity_contrast.json`.
  - `report/compute_consensus_deer_{combo,disjunctive,tiered}.py` — the excluded
    add-on experiments.
- **v3 planning docs** under `paper/revision_v3/`: `MECHANISM_RESTRUCTURE.md`
  (the restructure rationale), `CONSENSUS_ADDON_EXPERIMENTS.md` (excluded
  experiments + the tiered-threshold follow-up idea), `FIGURE_STATUS.md`,
  `FIGURE_PLAN.md`, `FIG1_IDEA_SPEC.md`, `CAPTIONS.tex`, `concepts/`.

## Install / run the dynasor tool
```bash
pip install -e .
vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-7B --enable-prefix-caching
dynasor-chat --base-url http://localhost:8000/v1
```

## Reproduce the v2 sweep (CPU; probe banks required)
```bash
cd benchmark/FalseConsensus/governor_v2
python make_protocol_v2.py                 # protocol_v2.json + candidate_rules_v2.jsonl
# consensus dev sweep, sharded, run as a module from the repo root:
python -m benchmark.FalseConsensus.governor_v2.replay_rules sweep \
  --protocol protocol_v2.json --rules generated/candidate_rules_v2.jsonl \
  --split-manifest generated/split_manifest.json \
  --results-root ../results/governor_v2 --phase development \
  --shard-index I --shard-count 10 --output shard_I.jsonl
python deer_threshold_sweep.py --output deer_sweep.jsonl   # run from governor_v2/
python select_v2.py --consensus shard_*.jsonl --deer deer_sweep.jsonl --output sel.json
```

## Tests
```bash
python -m unittest benchmark.FalseConsensus.governor_v2.tests.test_governor_v2
python -m unittest discover -s benchmark/FalseConsensus/related_work/tests
```

## Paper
```bash
cd paper && pdflatex -interaction=nonstopmode acl_latex.tex \
  && bibtex acl_latex && pdflatex acl_latex.tex && pdflatex acl_latex.tex
```
- No `poppler`/`pdftoppm` locally; render pages for visual QA with **PyMuPDF**:
  `python3 -c "import fitz; fitz.open('acl_latex.pdf')[0].get_pixmap(matrix=fitz.Matrix(2.2,2.2)).save('/tmp/p1.png')"`.
- Narrative source of truth: `CORE_PAPER_FLOW.md`. Ignore the outdated
  `PAPER_REVISION_V2_GOAL.md` and `paper/revision_v2/` (superseded, gitignored).

## Working conventions
- After noteworthy progress, update **both `log.md` and `plan.md`**. Convert
  relative dates to absolute.
- Numbers in the paper come from committed banks; when changing analysis code,
  regenerate the affected `report.md`/figures rather than hand-editing numbers.
- Git: `main` carries the v2 work; **`v3-mechanism-figures` carries the v3
  restructure and is not yet pushed**. Commit when asked; branch off `main`
  first if told to commit while on it. End commit messages with the
  `Co-Authored-By` / `Claude-Session` trailers.
  - The agent sandbox **cannot reach github.com** (no DNS) and **cannot unlink
    files** on the mount, so stale `.git/*.lock` files accumulate and must be
    removed from the host. Working around the index lock:
    `export GIT_INDEX_FILE=/tmp/gidx && git read-tree HEAD && git add …`.
- **Remote GPU safety**: the Vast.ai instance (id 45605832) may be *stopped* but
  must **never be destroyed**. On ugcpu2 (8×3090, conda env `gov`), never evict
  another user's process/GPU.
