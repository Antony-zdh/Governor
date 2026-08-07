# Preprint hardening — defect log

Branch `v5-preprint`. Standard: **hostile reviewer** — a reader who wants a
reason not to believe the paper. Items are listed even when they will probably
clear, because "probably clears" is not a defensible state for a preprint.

Status values: `open` · `running` · `settled-ok` (checked, paper needs no
change) · `settled-fix` (checked, paper must change) · `fixed`.

Cost columns are what it takes to *settle* the item, not to write the fix.

---

## Round 1 — inferential foundations (all CPU, committed banks only)

| # | Defect | Status | Compute | Wall clock |
|---|---|---|---|---|
| D1 | harm:rescue null baseline is asserted, not derived | open | CPU, 1 core | ~30 min |
| D2 | gross saving never reported for the safe rules | open | CPU, 1 core | ~20 min |
| D3 | pooled-vs-macro robustness check never run | open | CPU, ~8 cores | ~1–2 h |
| D4 | κ=0.82 scope vs the reported taxonomy percentages | open | CPU, 1 core | ~20 min |
| D5 | "preregistered" provenance not independently verifiable | open | CPU, 1 core | ~15 min |

### D1 — the 1:1 null is probably wrong

**Claim at risk.** Abstract: "never approaching the $1{:}1$ of sampling noise";
§4.4: "Pure sampling noise predicts a $\approx1{:}1$ ratio".

**Attack.** The ratio is computed over stops where early commitment *changes*
correctness. Final accuracy is ~85%. If the committed answer were statistically
independent of the final one with stop-accuracy $q$, the expected ratio is
$\frac{P(\text{final correct})(1-q)}{P(\text{final wrong})\,q}$ — for
$q{=}0.5$ that is $\approx5.7{:}1$, not $1{:}1$. Under that null, 45:1 is still
a large effect but **2:1 at $W{=}30$ sits below chance**, which would mean large
windows are *better* than a coin flip rather than merely rarely firing. A
reviewer who does this arithmetic on the back of an envelope reaches a different
conclusion from the paper's.

**Settles it.** Recompute, using the exact §4.4 slice
(`consensus_fixed`, $s{=}1.0$, interval 128, maturity 512, schema validity,
certainty off), for every $W$: final-correct rate, stop-correct rate among
fired problems, and the base-rate-adjusted expected ratio. Report observed
ratio against that null, not against 1:1. Also report a permutation null
(shuffle stop verdicts within environment) as a non-parametric check.

**Fix if confirmed.** Rewrite the null in abstract/§4.4/conclusion. The
directional-cost claim likely survives at small $W$; the $W{=}30$ end must be
re-described.

### D2 — the saving gate is evaluated only net, and only DEER escapes the probe tax

**Claim at risk.** §5.2: "only 40 rules keep the total drop at or below the
conservative 1.0 pp cap, and the most any of them saves is 0.2%". `tab:grossnet`
reports gross-vs-net only for the *save*≥10% and ≥20% points, never for the safe
rules.

**Attack.** Consensus pays a 32-token probe every 64 tokens; DEER reads at
reasoning boundaries. The 10% saving floor is therefore applied to two signals
under different overhead regimes. "0/3520 clears any gate" could in part be an
accounting artifact. Limitations concedes the probe tax may "move some rules to
positive net savings" — a reviewer will ask why that sentence is in Limitations
rather than in a table.

**Settles it.** Compute **gross** saving for all 40 rules with drop ≤1.0 pp, and
the full gross-saving frontier at each gate's drop cap. State the max gross
saving among safe rules. Additionally: recompute DEER's saving with consensus's
probe tax charged to it (an upper-bound-fair comparison).

**Fix if confirmed.** Add a gross-saving row to `tab:grossnet` for the safe
rules, and state the max-gross number explicitly in §5.2. If max gross saving
among safe rules is ≥10%, the headline needs a scope qualifier.

### D3 — the dev negative result may be a macro-weighting artifact

**Claim at risk.** "0 of 3,520 rules clear any gate on dev." Carried over from
v3 and still not done.

**Attack.** The same 478 train winners have median drop 4.50 pp on dev but
0.62 pp on test, traced to Qwen3-8B AMC23 ($n{=}8$) and AIME24 ($n{=}6$) dev
cells carrying equal macro weight. A 6-problem cell moves 16.7 pp per problem.
The emptiest gate in the paper is the one most exposed to this.

**Settles it.** Recompute the three gates **pooled over problems** as a
robustness check, dev and test. The protocol mandates macro, so pooled is
reported as a check and never substituted. Also report per-environment drop
distributions for the conservative gate and a leave-one-environment-out
sensitivity.

**Fix if confirmed.** If pooled also yields 0/3,520, add one sentence and a
table to Appendix D — this becomes a *strength*. If pooled admits rules, the
negative result must be restated as macro-specific, which is a substantial
rewrite of §5.2 and the abstract.

### D4 — κ is reported next to percentages it was not computed on

**Claim at risk.** Figure 2(b) caption and §4.3: "$61.2\%$ … $18.7\%$ …
$17.9\%$ … ($\kappa{=}0.82$ on the top-level coding)".

**Attack.** κ is computed on the coarse three-way coding
(substantive / format / other). The headline split that carries the argument is
*within* "substantive": not-converged (61.2%) vs settled-wrong (17.9%) — exactly
the A/D boundary where the two annotators disagreed and which was resolved by
adjudication under a fixed rule. Presenting 0.82 adjacent to the finer numbers
invites the reading that the finer numbers have that reliability. Given that the
submitted PDF already carries one citation defect, this is an integrity item,
not a presentation item.

**Settles it.** Compute raw agreement and κ on the *fine* coding from
`results/human_eval/`; report both values. Verify what fraction of the 134 cases
required adjudication on the A/D boundary.

**Fix if confirmed.** Report both κ values explicitly, name the adjudication in
one clause, and state that the not-converged vs settled-wrong split is the
adjudicated record. Taxonomy *provenance* stays out (locked decision) — but the
reliability of the reported split cannot.

### D5 — "preregistered" must survive a check

**Claim at risk.** The word appears in the title-adjacent abstract, §1, §5 and
the appendix, and is load-bearing rhetorically.

**Attack.** A reader who clones the repo will ask when the protocol and gates
were committed relative to the first sweep run. If the appendix text postdates
the sweep, the adjective is unsupported — and the reader already knows about the
fabricated `preregistration_ml` stub.

**Settles it.** `git log --follow` on `governor_v2/protocol_v2.json`,
`make_protocol_v2.py` and the gate definitions; compare the earliest commit
timestamp against the earliest sweep artifact in
`results/governor_v2_ws_sweep/manifest.json`. Record the SHAs and dates.

**Fix if confirmed.** If ordering is clean, cite the SHA and date in
Appendix B — this converts a rhetorical adjective into a verifiable one. If the
ordering is not clean, downgrade the wording to what the record supports.

---

## Round 2/3 — GPU-dependent (dispatched to ugcpu2, see `GOAL_UGCPU2_V5.md`)

| # | Defect | Status | Compute | Wall clock |
|---|---|---|---|---|
| G1 | §4.2 wording result rests on 1 model, 241 short trajectories, 3072-token cap | running | 2 × RTX 3090 (one per model), bf16 | 2–4 h, cap 6 h |
| G2 | the DEER contrast is not signal-isolated | running | 1–2 × RTX 3090 | 1–2 h |

### G1 — the wording diagnostic is the softest load-bearing evidence

**Claim at risk.** §4.2 and Figure 2(a): two wordings disagree 54% in the first
tenth, 10% in the final third. This is the paper's most direct evidence that
early agreement is probe-elicited rather than a settled belief.

**Attack.** One environment (DeepSeek-7B × MATH500 × seed 42), a 3,072-token
re-probe cap against 16K/32K main trajectories, and therefore only the
241 of 400 trajectories short enough to be covered end to end — i.e. the result
is measured on a *length-selected* subsample. The paper says all of this
honestly, which converts it from a hidden flaw into an admitted one, but a
hostile reviewer will still refuse to let a single length-selected environment
carry a contribution bullet.

**Settles it.** Collect a `dense_certaindex32` probe bank at the same 64-token
schedule against the **frozen 16K/32K main trajectories**, both development
models, three benchmarks, three seeds, **dev split** (684 trajectories). It
pairs 1:1 with the existing `dense_simple32` bank, so no simple-arm recollection
is needed and no main generation is touched.

**Fix if confirmed.** Replace the exploratory numbers in §4.2 with the
18-environment two-model version and delete the scope caveat. If the effect
shrinks on Qwen3-8B, report both models separately and rescope the claim.

*Note:* the §4.3 taxonomy (D4/G1's sibling) can be re-labelled on the new bank,
but the labelling itself is human work and is not part of the GPU job.

### G2 — DEER may win on *where* it reads, not on *what* it reads

**Claim at risk.** §5.7: "the failure lies in how the stop is decided rather
than in early exit". Already carries four qualifications, including that the
contrast is not a one-factor ablation.

**Attack.** Conceding the confound in prose is weaker than removing it. DEER
reads at reasoning boundaries and commits a freshly generated trial answer;
consensus reads on a fixed 64-token grid and commits a probe answer. Three
factors differ at once. A reviewer can claim the whole result is a
*timing* effect.

**Settles it.** Evaluate consensus **at DEER's own boundary positions**: extract
boundary token positions from `results/related_work/deer_confidence_bank_cap30/`
and collect simple@32 probes at exactly those positions, then run the windowed
consensus rules on that boundary-aligned stream through the same gates. This
holds *when* fixed and varies only *what* is read. It is the single
highest-value new experiment in the plan: it converts the paper's weakest
inference into a measured one.

**Fix if confirmed.** If boundary-aligned consensus still clears no gate, §5.7's
third qualification becomes a positive result and the DEER contrast is
signal-isolated on the timing axis. If it *does* clear a gate, the paper's
central claim needs restating as a claim about probe schedules — a major
revision, and better discovered now than by a reviewer.

---

## Round 4 — presentation (CPU, no experiments)

Not yet enumerated. Known entries: duplicated grey titles baked into Figures
7/8/9; Figure 1 text lives in a pptx and does not follow `.tex`; 9 orphan
`custom.bib` entries; upstream ACL template files still in `paper/`
(`acl_latex_template.tex`, `acl_lualatex.tex`, `formatting.md`,
`anthology.bib.txt`, `tests/regression/`); `dynasor_certaindex` cites the v1
arXiv title. Page-limit pressure disappears for a preprint, which frees room for
every hedge Rounds 1–3 require.
