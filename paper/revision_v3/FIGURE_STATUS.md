# v3 figures — status, and four things the paper agent needs to know

Figure agent, 2026-08-03. Companion to `FIGURE_PLAN.md` (design rationale) and
`FIG1_IDEA_SPEC.md` (Figure 1 drawing spec).

---

## Delivered

| file | what it argues | where | source |
|---|---|---|---|
| `figures/gen/fig1_idea.pptx/.pdf` | **Fig 1 variant A** — 3-panel argument | §1 | `revision_v3/make_fig1_idea.py` |
| `figures/gen/fig1_idea_b.pptx/.pdf` | **Fig 1 variant B** — 5-stage pipeline | §1 | `revision_v3/make_fig1_idea_b.py` |
| `figures/gen/fig_consensus_pos.pdf` | consensus fires early, and early is where it is worst | §4.1 | `report/make_v3_figures.py` |
| `figures/gen/fig_ws_heatmap.pdf` | the whole $(W,s)$ surface fails, not just the cloud's edge | §4.2 | `report/make_v3_figures.py` |
| `figures/gen/fig_split_transfer.pdf` | a rule must clear the gate on every split; none does | §4.5 | `report/make_v3_figures.py` |
| `figures/gen/fig_harm_rescue.pdf` | the window only lowers the ratio by refusing to fire | §5.1 | `report/make_v3_figures.py` |
| `figures/gen/fig_taxonomy.pdf` | what consensus actually stops on (human annotation) | §5 | `report/make_v3_figures.py` |

Both Fig 1 variants are editable `.pptx` (native shapes and text, no images) with
PDF exports. Per your decision, `fig_models` and `fig_bench` move to the
appendix; `fig_split_transfer` replaces `fig_splits` as the main-body selection
figure, so the main body keeps **zero** redundant Pareto scatters.

New compute (results cached as JSON next to the figures):

- `report/compute_harm_rescue.py` → `figures/gen/harm_rescue_cache.json`
- `report/compute_consensus_position.py` → `figures/gen/consensus_position_cache.json`

Five distinct plot families now: schematic, line-with-gap, heatmap pair,
split slopegraph, twin-axis log/bar.

---

## 1. The negative result rests almost entirely on the dev split — and two tiny environments in it

This is the thing most likely to be attacked in review, and the new
`fig_split_transfer` makes it visible, so it needs a decision rather than a
caption tweak.

Macro drop over all 3,520 rules, dev models, selection budgets:

| split | median drop | median saving |
|---|---|---|
| train | 5.38 pp | 32.5% |
| **dev** | **13.19 pp** | 27.1% |
| test | 6.47 pp | 36.9% |

The 478 rules that clear the conservative gate in-sample on train behave the
same way: median drop **4.50 pp on dev** but **0.62 pp on test**, and
**364 of 478 clear the gate on test**. The joint gate is still empty (0/478),
which is what the paper claims — but "0 on dev, 364 on test" is a very
different-feeling sentence from "consensus never works."

Where the dev penalty comes from (median drop per environment):

| environment | n / seed | dev | test |
|---|---|---|---|
| Qwen3-8B · AMC23 | 8 | **29.17 pp** | 0.00 pp |
| Qwen3-8B · AIME24 | 6 | **27.78 pp** | 22.22 pp |
| Qwen3-8B · MATH500 | 100 | 6.00 pp | 3.33 pp |
| DeepSeek-7B · AMC23 | 8 | 8.33 pp | −4.17 pp |
| DeepSeek-7B · MATH500 | 100 | 3.33 pp | 4.33 pp |

Two environments of 8 and 6 problems carry the same macro weight as a
100-problem one, and they happen to be brutal on dev and mild on test. This is
consistent with the standing "small sets are noisy" caveat, but the caveat is
currently a methods aside rather than something the headline is hedged against.

**Done:** §4.5 now states the dev/test asymmetry and its source explicitly rather
than letting a reviewer find it, and keeps the joint-gate framing as the headline.

### TODO (open) — re-confirm the negative result on pooled data

Macro-averaging is what gives an 8-problem environment the same weight as a
100-problem one, so the whole dev penalty could be an artefact of the weighting
rather than of the split. Before submission, recompute the headline gate result
**pooled over problems** (problem-micro, or equivalently weighting each
environment by its problem count) and check that:

1. no consensus rule clears the conservative gate on dev under pooling either;
2. the dev/test drop gap narrows — if it largely closes, say so in §4.5 and
   report pooled as the robustness check;
3. DEER's three operating points still clear all three gates under pooling.

The protocol mandates macro ("macro-average environments; never problem-micro"),
so pooled numbers must be reported as a *robustness check*, not as a
substitution — otherwise it reads as post-hoc metric shopping. Everything needed
is in `dev/consensus_dev_train.jsonl.gz` (each row carries `n`), so this is a
re-aggregation, not a re-run.

---

## 2. §5.1's harm:rescue numbers reproduce exactly — and the convention is now recorded

The published values (≈45:1 at $W{=}1$, ≈2:1 at $W{=}30$, 668 vs 121 dev
problems stopped) were not reproducible from any committed script; the
window-walking convention lived only in the numbers. I recovered it by search:

> `consensus_fixed`, share threshold $s=1.0$, probe interval **128**,
> maturity floor **512**, **schema** validity, certainty off — $W$ the only
> axis that varies.

That gives **668 stops at 45.125:1** for $W{=}1$ and **121 stops at 2.0:1** for
$W{=}30$ — exact matches. DEER's operating points likewise reproduce at
**3.0 / 2.4 / 3.5:1**, matching the `log.md` entry.

Full curve (dev, 18 environments), now committed in
`figures/gen/harm_rescue_cache.json`:

| W | 1 | 3 | 5 | 8 | 12 | 16 | 24 | 30 |
|---|---|---|---|---|---|---|---|---|
| harm:rescue | 45.1 | 25.7 | 13.3 | 8.6 | 5.7 | 4.3 | 2.6 | 2.0 |
| problems stopped | 668 | 639 | 603 | 525 | 420 | 311 | 193 | 121 |
| net saving | 92% | 75% | 53% | 37% | 27% | 21% | 12% | 8% |

**Ask:** the appendix should name this rule, since the whole §5.1 curve is
conditional on it. The figure caption states it, but the paper should too.

Your issue-1 resolution ("~45× at an aggressive **latest-probe** stop, ~2× at
the largest windows") is consistent with this and with both Fig 1 variants.
Note the $W{=}1$ rule here is a latest-probe stop with a 512-token maturity
floor, not a bare latest-probe stop — worth a half-clause if you want to be
exact.

---

## 3. A grader-state trap worth adding to CLAUDE.md

Replaying DEER **in the same Python process** after the consensus replays
inflates DEER's accuracy drop by ~0.7 pp (τ=0.995: 1.06 pp instead of the
banked 0.33 pp) while leaving token saving bit-identical. In a fresh
interpreter it reproduces `deer_threshold_sweep.jsonl.gz` exactly.

`compute_harm_rescue.py` now runs the DEER leg in a subprocess for this reason.
Since the symptom is a plausible-looking wrong number rather than a crash, and
it is the same family as the v1 grader-import bug already documented, it belongs
in the "Experimental details you MUST heed" section.

---

## 4. The human error taxonomy now supports the mechanism directly

The A/D boundary was read differently by the two annotators, so the record uses
annotator 1's reading of it, where **A** is reserved for cases in which the model
really had settled on a wrong numeric value and **D** for cases where it had not
settled at all. Adjudicated distribution over all 134 stopped-but-wrong cases:

| category | share | n |
|---|---|---|
| **D** unconverged guess / placeholder | 59.7% | 80 |
| **A** converged on a wrong value | 20.1% | 27 |
| **E** probe format artifact | 17.2% | 23 |
| other (expression collapse, sign error) | 3.0% | 4 |

Reliability is reported on the coarse coding both annotators share
(settled-or-not / format / other): **κ = 0.82**, n = 134.

Read this way, only about one stop in five is the model being wrong about
something it had actually decided. The remaining ~77% are answers the probe
*compelled* — which is beat 5 of `CORE_PAPER_FLOW` measured rather than argued.

Two things the caption states and §5 should too: the cases were collected under a
**short** window (three consecutive agreeing certain probes, five-probe
unanimity), which is exactly the regime where unconverged answers dominate, and
that ties this figure directly to `fig_harm_rescue` — a larger window buys back
accuracy only by declining to fire. §3 currently cites a preliminary 28-case
AI-assisted pass and should be replaced by this 134-case double-annotated result.

---

## Notes on the figures themselves

**`fig_consensus_pos`** uses position as a *fraction of each trajectory's own
length*, which controls for problem difficulty. The result is sharper than the
absolute-token binning in §4.1: consensus formed in the first 10% of a
trajectory is right **27.5%** of the time against **85.2%** for the same
problems run to completion, and **338 of 679** consensuses form there. Bins with
n < 20 are drawn with open markers; the 80–100% bin is n=3 and should not be
read.

**`fig_ws_heatmap`** summarises each cell by its two extreme members — the
safest rule (colour = drop, annotation = the saving it buys) and the most
economical rule (colour = saving, annotation = the drop it costs) — because
that is exactly the pair a gate interrogates. Best safe cell: $W{=}30, s{=}1.0$
at 0.8 pp drop for **−1%** saving. Best economical cell: $W{=}1$ at 98% saving
for **73 pp**. Zero cells clear the conservative gate.

**Figure 1 variant A** draws the *real* probe stream of MATH500 #68
(DeepSeek-7B, seed 42): ten consecutive certain probes reading `37` against gold
`46`, then recovery to `46` held for the final 47 probes. Variant B follows your
`figure_prompts.md` five-stage spec, with real dev-split points in the stage 3/4
insets. Both are editable in PowerPoint.

All long explanatory text has been moved out of the figures and into
**`CAPTIONS.tex`** (this directory), ready to paste into `sections/*.tex`:
every figure now carries only a short centred title and the labels needed to
read it.

**Still open:** the `\includegraphics` blocks are not yet inserted into
`sections/*.tex` — I held off until you confirm which Fig 1 variant wins and
where §4.2/§5.1 land after the section merge.
