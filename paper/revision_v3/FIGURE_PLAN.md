# v3 Figure Plan (issues 7 & 8)

Author: figure agent. Created 2026-08-03. Status: **proposal, pre-handoff**
(paper agent still working issues 1–6; section numbers below may shift).

---

## 1. Diagnosis of the v2 figure set

| # | File | Panels | Plot type | Section |
|---|---|---|---|---|
| 1 | `figures/gen/fig_splits.pdf` | 3 (train/dev/test) | saving-vs-drop scatter | §1 |
| 2 | `figures/gen/fig_models.pdf` | 4 (DS-7B, Qwen3-8B, 32B, Llama) | saving-vs-drop scatter | §4.5 |
| 3 | `figures/gen/fig_bench.pdf` | 3 (MATH500, AMC23, AIME24) | saving-vs-drop scatter | §4.5 |

**10 panels, 1 plot type, 0 variation.** Two structural problems:

1. **Redundancy.** Figures 2–3 make the *same* claim as Figure 1 ("consensus
   scatter stays out of the gate box, DEER stars stay in") seven more times.
   A reader learns nothing new after panel 3.
2. **The paper's central phenomenon has no figure at all.** "False consensus"
   — probe agreement forming while the answer is still moving — is carried
   entirely by prose numbers (§4.1 facts 1–4, §5.1 harm:rescue). The one thing
   a reader should *see* is the only thing we never draw.

Beat 5 of `CORE_PAPER_FLOW.md` (the mechanism: placeholder answers, window as
buffer) is likewise text-only.

---

## 2. Proposed v3 figure set

Six main-body figures, **six distinct plot types**, Pareto scatters reduced from
10 panels to 3.

| # | Working title | Type | Section | Status |
|---|---|---|---|---|
| **1** | Idea figure: the argument in one picture | hand-drawn (PPTX) schematic | §1 | **new** — issue 8 |
| **2** | False consensus in the raw probe stream | answer-identity ribbon + aggregate curve | §4.1 | **new** |
| **3** | The safe-and-saving corner is empty across the whole rule space | W×s heatmap pair | §4.2 | **new** |
| **4** | Selection → generalization | saving-vs-drop scatter, 3 panels | §4.5 | **keep** `fig_splits` |
| **5** | Generalization at a glance | dev↔test correlation + gate-clearance forest | §4.5 | **new**, replaces `fig_models`+`fig_bench` |
| **6** | The window trap: harm:rescue vs. what you actually save | twin-axis line/bar | §5.1 | **new** |
| A.x | per-model / per-benchmark Pareto panels | scatter | Appendix | **demote** `fig_models`, `fig_bench` |
| A.y | What consensus stops on (error taxonomy) | stacked bar + κ | Appendix | **conditional** — see §4 |

---

## 3. Figure specifications

### Figure 1 — Idea figure (issue 8)

Full spec in **`FIG1_IDEA_SPEC.md`** (this directory). Built as an editable
`.pptx` + exported PDF so it can be adjusted in PowerPoint.

---

### Figure 2 — False consensus in the raw probe stream  *(new; §4.1)*

**What it argues (beat 1).** Agreement is not terminality. The reader sees a
long, perfectly stable run of identical probe answers that is *wrong*, followed
by the trajectory recovering on its own. This is the paper's premise, shown
rather than asserted.

**Panel (a) — answer-identity ribbon.** x = generated tokens (0 → stop);
y = ~8–10 exemplar trajectories, one horizontal strip each. Each 64-token probe
is a cell coloured by:

- **green** — probe answer matches gold
- **red** — probe answer is a specific wrong value (saturation encodes *run
  identity*, so a long stable wrong consensus reads as one solid block)
- **hatched grey** — empty / invalid probe

Overlays per row: ▼ marker where a `W=3, s=1.0` rule fires (the first stable
agreement); ● at the trajectory's own final answer. The visual punchline is a
solid red block with a ▼ on it, followed by green.

**Verified exemplars** (DeepSeek-7B / MATH500 / seed 42, dense 64-token probes,
robust grader; `results/governor_v2/development__…__math500__seed_42/`):

| pid | stable wrong run | consensus answer | gold | final |
|---|---|---|---|---|
| 253 | **20 probes** from t=384 | `D` | `1/8` | correct |
| 320 | 27 probes from t=64 | `0` | `-24/25` | correct |
| 68 | 10 probes from t=128 | `37` | `46` | correct |
| 75 | 8 probes from t=64 | `B` | `11/36` | correct |
| 483 | 14 probes from t=64 | `2` | `8/15` | correct |
| 361 | 14 probes from t=64 | `8√3` | `16√3` | correct |

pid 253 and 75 double as the **type-E format hallucination** the appendix
describes (a bare option letter on a non-multiple-choice problem) — worth
labelling in the caption.

**Base rate for the caption:** in this single environment, **126 of 400**
problems show an early ≥3-probe wrong consensus followed by a correct final
answer. (Recompute across all 18 dev environments before citing.)

**Panel (b) — aggregate.** P(current probe answer = trajectory's own final
answer) vs. fraction of trajectory generated, one curve per dev model, with the
§4.1 fact-3 buckets (<512: 91.0%, 512–1024: 92.5%, 1024–2048: 92.2%, >2048:
71.6%) as an inset bar. Shows the ribbon is representative, not cherry-picked.

**Data:** `dense_simple32/probes.csv` (token_position, probe_answer,
is_certain) joined to `main/traj/problem_*.json` (final_answer, final_correct,
target); grading via `governor_v2.grading.robust_answers_equal`.

---

### Figure 3 — The corner is empty across the whole rule space  *(new; §4.2)*

**What it argues (beat 3).** The negative result is not "the scatter cloud
misses a box" — it is a *structured* property of the two-hyperparameter space.
Every cell fails, and the reader can see the trade-off gradient that forces it.

Two heatmaps over the sweep's own axes, **W ∈ {1,3,5,8,12,16,24,30}** ×
**s ∈ {0.6,0.8,1.0}** (each cell = 160 rules, marginalising the operational
knobs):

**(a) Best net saving achievable subject to macro drop ≤ 1.0 pp** (the
conservative cap). Recomputed from `dev/consensus_dev_train.jsonl.gz`:

```
        s=0.6    s=0.8    s=1.0
W= 1       —        —      none
W= 3     none     none     none
W= 5     none     none     none
W= 8     none     none     none
W=12     none     none     none
W=16     none     none     none
W=24     none     none     none
W=30     none     none    0.21%      <- gate floor is 10%
```

One cell in twenty-two is non-empty, and it is 0.21% against a 10% floor.

**(b) Minimum macro drop subject to net saving ≥ 10%** (the saving floor):

```
        s=0.6      s=0.8      s=1.0
W= 1       —          —      22.25pp
W= 3   20.34pp    11.76pp    11.76pp
W= 5   17.52pp    11.05pp     8.01pp
W= 8   13.02pp     7.61pp     4.91pp
W=12    6.56pp     4.39pp     4.10pp
W=16   11.24pp     5.89pp     2.82pp
W=24    4.50pp     6.64pp     2.66pp
W=30    5.37pp     6.69pp     3.52pp
```

Every cell exceeds the 1.0 pp cap; the best is 2.66 pp (matches the §4.2
sentence "the first rule to save 10% already costs 2.66 pp" — the number is
*derived* by the figure rather than asserted). Cells at/below the cap get a
gate-coloured border; there are none.

**Verified:** both grids recomputed 2026-08-03 from the committed bank, macro
over 18 dev environments. Column `s=0.6/0.8` at `W=1` is empty by construction
(behaviourally redundant, dropped from the sweep).

**Payoff:** this figure alone can carry §4.2, freeing the dev panel of Figure 4
to be about *selection* rather than about the negative result.

---

### Figure 4 — Selection → generalization  *(keep `fig_splits`)*

Unchanged, and it earns its place: it is the only figure that shows the
train-selected orange rules *moving out of* the gate box. One canonical Pareto
figure in the paper is right; seven is not.

Minor asks: drop the redundant "dev" panel only if §4.2 is fully carried by
Figure 3 *and* the paper agent's train/dev/test framing (issue 3) makes the
two-panel train→test story self-contained. Recommend keeping all three.

---

### Figure 5 — Generalization at a glance  *(new; replaces `fig_models` + `fig_bench`)*

Seven scatter panels compressed into one two-panel figure carrying strictly
more information than they did.

**(a) Rank-preservation scatter.** x = per-rule macro accuracy drop on dev,
y = same rule's drop on the held-out set; one colour per held-out set (test
split r=0.98, Qwen-32B r=0.97, Llama-8B r=0.94), identity line, r annotated in
the legend. This is the actual claim of §4.5 — currently three bare numbers with
no figure — and it is a *correlation* plot, not another Pareto cloud.

**(b) Gate-clearance forest.** One row per environment axis (DS-7B, Qwen3-8B,
Qwen-32B, Llama-8B, MATH500, AMC23, AIME24, test split). For each row, two
markers: best consensus rule and DEER at the conservative gate, positioned on a
net-saving axis, filled if the row's drop ≤ 1.0 pp and hollow otherwise. Every
consensus marker lands hollow or near 0%; every DEER marker lands filled at
26–32%. Known values to reproduce: consensus best-under-1.0pp = 0.2% (dev),
0.6% (32B), 9.3% (Llama, hollow-adjacent — check drop); DEER = 28.2% dev,
32.4% @ τ0.97 (32B), 26.7% @ τ0.99 (Llama).

The 7 original panels move to the appendix verbatim (they are genuinely useful
as per-environment evidence, just not as main-body real estate).

**Honesty note to preserve:** the report flags that DEER's advantage is largest
on Qwen3-8B/MATH500 and weak/noisy on DeepSeek-7B/AIME24. Panel (b) must show
that, not hide it — the AIME24 row should visibly be the noisy one.

---

### Figure 6 — The window trap  *(new; §5.1)*

**What it argues (beat 5, and it fixes issue 1).** The harm:rescue ratio is
*window-dependent*, and the only way to shrink it is to stop firing. Currently
this is a fragile prose sentence with two different numbers (45:1 in §5, "up to
35×" in the abstract) — a figure makes the whole curve the claim, so no single
number has to carry it.

Twin-axis plot, x = window size W (1 → 30):

- **left axis (log):** harm:rescue ratio, consensus — falls ≈45:1 → ≈2:1
- **right axis:** net token saving (%) *and* number of dev problems stopped
  (668 at W=1 → 121 at W=30), shaded to show it collapsing in lockstep
- **horizontal band:** DEER's ≈2.4–3.5:1 at its three operating points, drawn
  at its *actual* saving (28–32%) — the visual point being that DEER sits at
  consensus's best ratio *and* consensus's best saving simultaneously, which no
  consensus W does
- **dashed line at 1:1** = the sampling-noise null

**Recommendation for issue 1:** once this figure exists, quote the *range*
everywhere ("≈45:1 at a latest-probe stop, falling to ≈2:1 only where the rule
almost never fires") and delete the bare "35×" from the abstract. The
discrepancy disappears because no single scalar is load-bearing.

---

### Appendix figure — What consensus stops on (error taxonomy)

**Conditional — do not build yet.** `taxonomy_review_1.csv` and
`taxonomy_review_2.csv` (134 cases, 2 annotators) disagree badly:

| | A | B | C | D | E |
|---|---|---|---|---|---|
| annotator 1 | 27 | 3 | 1 | 80 | 23 |
| annotator 2 | 72 | 6 | 1 | 28 | 27 |

A and D are essentially transposed between the two raters, so κ will be poor and
a stacked bar would be misleading. The A/D boundary (numeric collapse vs.
derivation gap) evidently needs a sharper rubric or adjudication
(`human_eval/adjudicate_reviews.py`) before this becomes a figure. **Flagged for
the paper agent** — §3's error-taxonomy paragraph currently cites a *different*,
28-case AI-assisted pass, so nothing in the paper depends on this yet.

Type E (format/option hallucination) is the robust cell — both raters agree
(23 vs 27, ~1 in 5) — and it is already visible in Figure 2 via pids 253/75, so
the type-E point can be made there without the taxonomy figure.

---

## 4. Open questions for the paper agent

1. **Section numbering** after the §4.3/4.4/§5.4/5.5 merge (issue 4) — Figures 3
   and 6 need final homes.
2. **Table 3 / TJE removal** (issue 5): does any figure reference TJE? Current
   answer: no main-body figure does; `report/analyze_tje_threshold_frontier.py`
   output is not in the paper.
3. **Fig 4 dev panel**: keep 3 panels or drop to train→test? Depends on how §4.2
   ends up leaning on Figure 3.
4. **Abstract number** (issue 1): confirm the switch from "up to ~35×" to the
   range, so Figure 6's caption and the abstract agree.

## 5. Build order

1. Figure 1 (independent of issues 1–6) — **in progress**
2. Figure 3 (data verified, self-contained)
3. Figure 2 (needs a cross-environment recount of the 126/400 base rate)
4. Figure 6 (needs harm:rescue recomputed per W from the replay)
5. Figure 5 (needs test + heldout banks joined on rule_id)
6. Re-verify every number against `results/governor_v2_ws_sweep/report.md`
