# Consensus as an add-on to a confidence signal — experiment record

2026-08-03. **Not necessarily going into the paper.** Recorded so the numbers
are not lost and the follow-up is specified.

Both experiments run entirely on **DEER's own boundary-trial stream**
(`results/related_work/deer_confidence_bank_cap30/full/`, dev split, 18
environments), so consensus is evaluated over the same events DEER stops on.
No alignment with the 64/128-token consensus probe bank is involved, which
removes the main confound and is the *favourable* case for the hypothesis.

DEER baseline reproduces the committed bank exactly in both runs
(τ0.995 → 0.333 pp / 28.21%; τ0.99 → 1.028 pp / 29.56%; τ0.97 → 2.750 pp / 31.94%).

---

## Experiment 1 — conjunctive rule (negative)

**Rule:** stop when `conf > τ_c` **AND** the last $W$ trial answers agree.

**Result: 0 / 20 points Pareto-dominate any DEER operating point.** Requiring
agreement can only *delay* a stop, so it trades saving away for accuracy along a
strictly worse frontier.

| W | τ_c | drop pp | saving % | vs DEER |
|---|---|---|---|---|
| 1 | 0.995 | 0.333 | 28.21 | ≡ DEER C (sanity check) |
| 2 | 0.97 | 0.278 | 25.84 | 0.06 pp safer, **2.4 pp less saving** |
| 2 | 0.99 | 0.056 | 23.63 | 0.28 pp safer, **4.6 pp less saving** |
| 3 | 0.97 | 0.056 | 19.35 | **8.9 pp less saving** |

**Why the premise failed.** The hypothesis was that the model sits at moderate
confidence on a repeated answer before committing. It does not: at boundaries
*before* DEER (τ0.995) commits, median confidence is **0.0** and only 17.6%
exceed 0.9. There is little moderate-confidence headroom to exploit.

**And agreement adds nothing on top of confidence.** Confidence already
separates correct from wrong trials (mean 0.857 vs 0.371); among $W{=}3$
agreeing boundaries the *wrong* ones still average 0.384 — essentially identical
to wrong trials generally. Along $W{=}1$ alone, harm:rescue falls 25:1 → 3:1 as
τ rises; adding $W$ mostly removes stops (stop rate .707 → .503) rather than
removing *bad* stops.

Script: `report/compute_consensus_deer_combo.py` →
`figures/gen/consensus_deer_combo.json`.

---

## Experiment 2 — disjunctive two-threshold rule (qualified positive)

**Rule:** stop at the first boundary where **either**
(A) `conf > τ_hi` — the plain DEER branch, **or**
(B) `conf > τ_lo` **and** the last $W$ trial answers agree, with `τ_lo < τ_hi`.

Branch A alone is DEER at τ_hi, so the rule **can only stop earlier**; saving is
guaranteed not to regress. The open question is purely what the extra, earlier
B-stops cost in accuracy.

**Result: still 0 / 36 Pareto-dominate DEER at the same τ_hi** — every extra
early stop costs a little accuracy. **But the decisive comparison inverts:**
could simply *lowering τ_hi* have bought that saving more cheaply? No.

Verified against a **60-point dense DEER curve** (0.30–0.999999, fine mesh near
1.0), because the original 13-point curve was too sparse and linear interpolation
across the convex 30–56% region would have flattered the disjunctive rule.
**36/36** coarse-grid points reach their saving at a lower drop than DEER alone;
**214/260** points are not weakly dominated by any DEER threshold.

Best saving under each gate's drop cap:

| gate | DEER alone | disjunctive | Δ saving |
|---|---|---|---|
| conservative (≤1.0 pp) | 29.27% @ 0.333 pp | **30.74%** @ 0.556 pp (τ_hi .9925 / τ_lo .97 / W2) | **+1.47 pp** |
| balanced (≤2.0 pp) | 30.85% @ 1.944 pp | **34.64%** @ 1.944 pp (.995/.93/W3) | **+3.79 pp** |
| token_efficient (≤3.5 pp) | 31.94% @ 2.750 pp | **36.57%** @ 3.204 pp (.9925/.93/W2) | **+4.63 pp** |

The **balanced** row is the cleanest claim: *identical* drop (1.944 pp),
**+3.79 pp more saving**. A genuine frontier extension, not an interpolation
artefact.

**Branch-B breakdown.** At τ_lo = 0.99 / W2, branch B fires 39 times and is
**39 correct / 0 wrong**. Pooled over the fine sweep, **83.6%** of B-stops
(14,371/17,181) land on an answer the trajectory's own final answer agrees with.
Of the B-stops that pre-empted a *later* DEER stop, the large majority (e.g.
105/110) would have been correct under DEER too — i.e. B mostly banks the *same
correct answer earlier*, which is close to free saving. Pooled harm:rescue at
gate-passing points is 1.4:1–3.0:1, the band DEER itself occupies (2.4–3.5:1),
not the 45:1 of consensus alone.

Sanity checks (all pass): `τ_lo == τ_hi` ≡ plain DEER (6/6, bit-identical);
`W == 1` ≡ plain DEER at τ_lo (6/6); saving never regresses vs DEER-at-τ_hi
(0 violations in 260 points).

Script: `report/compute_consensus_deer_disjunctive.py` →
`figures/gen/consensus_deer_disjunctive.json`.

### How to phrase this if it is used

The optimal τ_lo lands at **0.93–0.99**, not the ~0.9 we guessed, and branch A
still does 75–90% of the stopping work. So branch B is not "moderate-confidence
agreement" — it is "already-quite-confident agreement". The honest claim is:

> Agreement is a useful **second-order refinement on top of a confidence
> signal** — worth roughly +1.5 pp saving at the conservative gate and +3.8 pp
> at the balanced gate — but it is not a stop signal in its own right.

This is strictly weaker than "consensus works" and does not contradict the
paper's negative result: consensus alone still clears no gate.

### Blocking caveat if it goes in the paper

**The winning (τ_hi, τ_lo, W) was selected on dev**, across 36 + 224 points. The
protocol says test is read once after freezing. To claim a real improvement we
must freeze **one** operating point and confirm on test (seeds 45/46/47), ideally
also on held-out 32B/Llama. Recommended freeze: the **balanced** point
(τ_hi .995 / τ_lo .93 / W3), the only one with drop exactly matched to DEER.

Also unquantified: per-environment CIs / paired tests. +1.47 pp is a macro mean
over 18 environments and AIME24/AMC23 are small per seed.

---

## Experiment 3 — $k$-tier thresholds (negative: diminishing returns)

Generalise the two-branch disjunction to $k$ tiers, each with its own confidence
floor and its own required run length, monotone in both:

> stop if `conf > τ_1`
> **or** the last 2 trials agree and all exceed `τ_2`
> **or** the last 3 trials agree and all exceed `τ_3`
> … with `τ_1 > τ_2 > τ_3 > …`

Intuition: the more corroboration a candidate answer has, the less confidence
any single reading needs to carry. Experiment 2 is the $k{=}2$ case.

**Result: one extra tier captures all of the value; $k{\ge}3$ does not beat
$k{=}2$.** Once $k{=}2$ is given the *same* floor range as the deeper tiers
(τ_2 down to 0.93), $k{=}3$ and $k{=}4$ lose or tie at 5 of 6 gate × semantics
cells.

Best saving under each gate's drop cap (dev, macro over 18 env):

| gate | DEER (dense 58-pt curve) | best $k{=}2$ | best $k{=}3$ | best $k{=}4$ |
|---|---|---|---|---|
| conservative (≤1.0 pp) | 29.27% @ 0.333 pp | **30.74%** @ 0.556 pp | 30.62% | 30.20% |
| balanced (≤2.0 pp) | 30.85% @ 1.944 pp | 33.75% @ 1.944 pp | **34.72%** @ 1.944 pp | 34.46% |
| token_efficient (≤3.5 pp) | 31.94% @ 2.750 pp | **36.57%** @ 3.204 pp | 36.41% | 34.88% |

(best-of-both-semantics per cell). Versus Experiment 2's headline the deltas are
**+0.00 / +0.08 / +0.00 pp** — a tie. The whole gain over DEER is the one already
reported in Experiment 2.

**Q1 (Pareto).** 27 / 470 configs Pareto-dominate plain DEER at their own τ_1
(saving strictly up, drop no worse) — but the gains are small (≤ +3.1 pp saving)
and sit in the very-high-τ_1 corner where DEER alone saves little. Both $k{=}2$
and $k{=}3$ appear among them; $k$ is not what makes a config a winner.

**Why more tiers do not help — the mechanism.** Pooled over all 373 configs with
a breakdown, marginal stop quality degrades monotonically with tier depth:

| tier | stops | accuracy | harm:rescue |
|---|---|---|---|
| 1 (run 1) | 160,116 | **0.960** | 2.30 |
| 2 (run 2) | 28,361 | 0.887 | 2.20 |
| 3 (run 3) | 10,495 | 0.784 | 2.96 |
| 4 (run 4) | 5,106 | **0.597** | 6.03 |

And this is **not** just the lower floors: at a *matched* floor τ = 0.93,
accuracy is 0.785 (tier 2) → 0.668 (tier 3) → 0.538 (tier 4). Longer agreement
runs at a fixed confidence floor select *worse* boundaries, not better ones —
the same directional accuracy tax the paper documents for consensus alone. So
agreement does not accumulate evidence; a deeper tier mostly identifies places
where the model repeated a low-confidence answer.

**Sanity checks (34/34 pass).** $k{=}1$ ≡ plain DEER bit-identically at 7
thresholds; all-τ-equal ≡ plain DEER for $k \in \{2,3,4\}$ at 3 thresholds;
$k{=}2$ reproduces Experiment 2's `variant_all_lo` on all 18 shared points;
saving monotone non-decreasing in $k$ over 1,168 prefix comparisons, 0
violations. DEER reproduces the committed bank exactly at 14 thresholds.

**Semantics.** The full grid was swept under both readings of "all $j$ exceed
τ_j" — `strict` (every boundary in the run must clear the floor; ≡ Experiment
2's `variant_all_lo`) and `last_only` (only the committing boundary; ≡
Experiment 2's default). `last_only` saves more at higher drop; the $k$ ordering
is the same under both.

Script: `report/compute_consensus_deer_tiered.py` →
`figures/gen/consensus_deer_tiered.json`.

### Caveat (same as Experiment 2, but larger)

All of this is **dev-only, in-sample selection over 470 configurations**. It is
exploratory. Nothing here should be claimed without freezing one operating point
and confirming on test. The practical upshot is a *negative* one that reduces
the temptation to search further: the $k$-tier generalisation adds search
freedom without adding frontier, so **Experiment 2's 2-tier rule is the right
stopping point** for this family.

---

## Bug found along the way — grader is order-dependent (needs a wider audit)

`latex2sympy2` has a **module-global `var` dict**. Grading the MATH500 answer
`"8thgradeshouldhave10representatives"` clobbers `var` from a `dict` into a bare
`Symbol`. Every subsequent `latex2sympy` call then raises
`TypeError: argument of type 'Symbol' is not iterable`, so `symbolic_equal`
**silently returns False** for expressions it would otherwise grade correctly —
e.g. `\frac{9a+11}{20}` vs `\frac{11+9a}{20}` flips True → False.

**Correctness therefore depends on whether unrelated garbage was graded earlier
in the same process.** This is what I had previously mis-attributed to
"fresh-process" state; the real cause is this global.

Both new scripts reset `var = {}` before every grader call and are
order-independent by construction, reproducing the committed bank exactly. **But
the committed banks were produced without this guard**, so a targeted audit is
warranted: re-grade a sample of the frozen results with the guard on and check
whether any accuracy figure moves.
