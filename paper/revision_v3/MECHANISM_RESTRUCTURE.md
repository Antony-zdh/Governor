# Restructuring the paper around mechanism

Figure agent, 2026-08-03. Proposal — nothing in `sections/` changed yet.

---

## 1. The problem with the current spine

As it stands the paper reads: *someone proposed consensus early exit; we
reproduced it carefully; it does not work; here is a very thorough search
proving it does not work.* The sweep is rigorous, but rigour is spent almost
entirely on establishing **that** it fails. A reviewer can fairly say: a
negative replication of one heuristic, with a positive control attached.

The mechanism material — the part that would make this a contribution rather
than a report — currently occupies about a page of §5 and is largely asserted:
"agreement reports what the model has said recently, not whether its reasoning
has finished." True, but unmeasured.

**Proposed spine:** the failure is not that consensus is a badly tuned
heuristic. It is that *the word "consensus" is doing work it has not earned*.
Self-consistency's guarantee comes from **independence between reasoning
paths**. Probe-based early exit reads **one** path repeatedly and calls the
resulting autocorrelation "consensus". Everything else in the paper — the
empty rule space, the directional accuracy tax, the placeholder annotations —
follows from that one substitution.

That is a claim about *why*, it is falsifiable, and we can now measure it.

---

## 2. Pillar 1 — consensus without independence carries no information (NEW, measured)

Self-consistency \citep{wang2023selfconsistency} samples a **diverse** set of
reasoning paths and marginalises over them; its stated intuition is that "a
complex reasoning problem typically admits multiple different ways of thinking
leading to its unique correct answer." Agreement is evidence *because the paths
are independent*.

Certaindex is explicit that its multi-path certaindex is semantic entropy over
$n$ independently sampled paths. For internalised CoT it reuses the same
$\tilde{\mathcal{H}}$ over "answers from different iterations" of a **single**
path. That substitution is the category error: iterations of one trajectory
share a prefix, so they are not independent draws.

**We can measure the cost of the substitution directly**, because we have three
seeds per problem. On the dev split (228 problems, 684 trajectories, baseline
accuracy 89.3%):

| agreement of three... | fires on | correct when it fires |
|---|---|---|
| **independent trajectories** (self-consistency, $k{=}3$) | 87.3% | **97.5%** |
| consecutive probes, *first* agreement (self-consensus, $W{=}3$) | 99.3% | **40.5%** |
| consecutive probes, *last three* (best case for it) | 88.3% | 89.6% |

Read the three rows together:

1. Independent agreement is worth **+8.2 pp over baseline** — it is real evidence.
2. Single-trajectory agreement, at the moment an online rule must act, is worth
   **−48.8 pp** — it is worse than not stopping at all.
3. Most damningly, single-trajectory agreement at its *most favourable*
   position — the last three probes of a finished trajectory — is correct
   **89.6%** of the time against an **89.3%** baseline. Within-trajectory
   agreement carries **essentially zero information beyond the final answer
   itself**. It cannot be fixed by moving where you read it.

That third row is the paper's mechanism in one number. It says the problem is
not timing, not thresholding, and not the probe schedule: it is that repeated
reads of one trajectory are not independent draws, so their agreement is not
evidence. Self-consistency's diversity is not a nice-to-have — it is the entire
source of the signal.

Script: `report/compute_diversity_contrast.py` → `figures/gen/diversity_contrast.json`.
**This wants a figure** (three bars, baseline as a reference line) and probably
belongs early in §5, before the harm:rescue curve.

*Caveats to state:* $k{=}3$ self-consistency costs 3× the tokens, so this is not
a fair efficiency comparison and we must not present it as one. The claim is
narrowly about *what agreement means*, not about which method is cheaper.

---

## 3. Pillar 2 — what the model is actually agreeing on (have it, under-used)

The 134 hand-labelled stopped-but-wrong cases ($\kappa = 0.82$): **60%**
unconverged guess or placeholder, **17%** probe-format artifact, **20%**
genuinely converged on a wrong value, 3% other.

This answers the obvious follow-up to Pillar 1 — *why* is a repeated answer so
uninformative? Because periodic probing does not read a belief, it **forces an
output**. A model that has not finished reasoning still has to write something
in the box; the cheapest thing to write is the same placeholder as last time.
Stability of a forced answer is stability of the *forcing*, not of the belief.

The parent/child analogy in `CORE_PAPER_FLOW` is exactly right and should
survive into the paper in one sentence: asked repeatedly what they want to be
when they grow up, a child who has not decided will keep naming the same thing,
and the parent will mistake repetition for conviction.

**This also predicts the window effect**, which closes the loop with Pillar 3: a
longer window is a longer buffer in which a placeholder can be overturned, so it
reduces false consensus — but it cannot manufacture independence, so the
systematic risk is unchanged. And on genuinely hard problems, where the model
needs many tokens before its first real candidate, even a long window sits
entirely inside the placeholder regime.

---

## 4. Pillar 3 — the window trap (have it, keep as is)

Already measured: harm:rescue falls 45:1 → 2:1 across $W$, but net saving falls
92% → 8% with it, and the number of problems stopped falls 668 → 121. The
long-window "fix" works by not firing. Keep `fig_harm_rescue` and §5.1 as they
are; just re-point the prose so it reads as a *consequence* of Pillars 1–2
rather than as a standalone finding.

---

## 5. Proposed section order for §5

1. **The substitution** — self-consistency needs independence; probe consensus
   has none. (Pillar 1, new table/figure.) *This is the thesis.*
2. **What gets agreed on** — forced placeholders, not beliefs. (Pillar 2,
   `fig_taxonomy`.) *Why independence is missing in practice.*
3. **Why widening the window cannot fix it** — the buffer helps and then stops
   helping, at the cost of all the savings. (Pillar 3, `fig_harm_rescue`.)
4. **The accuracy tax is intrinsic to the trajectory** — existing §5.2, now a
   corollary rather than the main event.
5. **The failure is the signal, not early exit** — existing merged §5.4, with
   DEER as the controlled contrast.

§4 (the sweep) then becomes what it should be: the *exhaustive check* that no
tuning escapes a mechanism we have already explained, rather than the paper's
centre of gravity.

---

## 6. CertaIndex reproduction — audit, and it needs fixing

I checked our replay against both the Certaindex paper and the shipped Dynasor
code. **Our claim of a "faithful" reproduction is currently too strong.**

**What we actually replay.** Two artifacts exist and it matters which one
`tab:baselines` uses:

- `governor_v2/replay_certaindex.py` — the *adapted* replay, reusing our
  `simple@32` probes. Its own docstring concedes it is "not the end-to-end
  faithful CertaIndex prompt/cap configuration." **Not the table's source.**
- `related_work/certaindex_mid.py` against
  `results/related_work/certaindex_effort_bank/` — dedicated CertaIndex probes
  (interval 64, 36 environments, 3,420 problems), the faithful prompt and the
  shipped stop rule, pinned to `dynasor/core/cot.py @ dbe76ad`. **This is what
  `tab:baselines` reports**, per `results/related_work/aggregate/report.md`.

So the reproduction is genuinely faithful to the **shipped implementation**:
`should_early_exit` at `effort_level("mid") = (3, 64)` — stop at the first point
where 3 consecutive probes are non-empty, mutually equal under `eqaul_group`,
and "certain" (no hedging word from
`["wait","hold","but","okay","no","hmm"]`). That is a stronger position than I
first assumed, and the aggregate report already carries the right disclaimer:
"这些结论只针对冻结轨迹复现，不反推原论文端到端结果."

**Where it diverges from the paper:**

| | Certaindex paper (ICoT case study, §6.7) | our replay |
|---|---|---|
| stopping signal | normalised entropy $\tilde{\mathcal{H}}$ over answers from successive iterations, **thresholded** | 3-window equality + certainty heuristic |
| model | Qwen-QwQ | DeepSeek-R1-Distill-Qwen-7B, Qwen3-8B |
| benchmark | GSM8K | MATH500, AMC23, AIME24 |
| probe cap | 20 tokens (Dynasor default) | faithful cap in the effort bank; 32 only in the *adapted* replay |
| reported outcome | −14% tokens, "without accuracy loss" | −56 to −70 pp accuracy |

The gap between "no accuracy loss" and "−70 pp" is exactly what a reviewer will
attack, and three of the four rows above are plausible explanations that have
nothing to do with our thesis. GSM8K in particular is much easier than AIME24;
answers stabilise early there, which is the regime where consensus *should*
work.

**Recommended fixes, in order of importance:**

1. **Relabel precisely.** Not "a faithful CertaIndex reproduction" but
   *a faithful reproduction of Dynasor's shipped CoT early-exit rule at its
   default `mid` effort level (`dynasor/core/cot.py` @ `dbe76ad`)*. One clause,
   and it becomes unattackable: we are reproducing an artifact, we name it, and
   we do not claim to have re-run the paper end to end.
2. **Add the entropy-threshold readout.** The paper's ICoT algorithm is a
   threshold on $\tilde{\mathcal{H}}$, not the patience heuristic; the existing
   analysis (`report/analyze_certaindex_effort_frontier.py`) only sweeps the
   four effort levels (patience 8/5/3/2), which is the same heuristic at
   different windows. **Confirmed feasible on CPU**: the effort bank stores raw
   per-checkpoint probe answers, so $\tilde{\mathcal{H}}$ over the answers seen
   so far, swept over a threshold grid, is a re-analysis of committed data. This
   gives us the paper-algorithm row next to the as-shipped row, and pre-empts
   "you tested their code, not their method."
3. **Probe cap** — the effort bank already uses the faithful configuration, so
   this only needs a sentence confirming it, and a note that the 32-token cap
   appears solely in the adapted replay we do *not* report.
4. **Add one easy benchmark** (GSM8K) or explicitly caveat that the collapse is
   measured on harder benchmarks than the original case study, and say what we
   expect on GSM8K. Being first to say it defuses it.
5. **Soften the framing** throughout: the contribution is the mechanism, not a
   takedown. "The shipped default sits exactly where the swept frontier says it
   must" is both more accurate and more useful than "CertaIndex collapses."

---

## 7. Work items

| # | item | status |
|---|---|---|
| 1 | `compute_diversity_contrast.py` — self-consistency vs self-consensus | **done**, numbers above |
| 2 | figure for Pillar 1 (three bars + baseline line) | not started |
| 3 | rewrite §5 in the order of §5 above | not started |
| 4 | reframe §4 as "no tuning escapes the mechanism" | not started |
| 5 | relabel CertaIndex → Dynasor shipped heuristic | not started |
| 6 | entropy-threshold ($\tilde{\mathcal{H}}$) readout from the effort bank | **confirmed feasible, CPU-only** |
| 7 | probe cap 32 → 20, or justify | not started |
| 8 | GSM8K run, or explicit caveat | needs a decision (GPU) |
| 9 | cite Wang et al. 2023 for the diversity premise; add to §2 | not started |
| 10 | pooled-data robustness check (from earlier) | still open |

Items 1–5 and 9 need no GPU. Items 6–8 may.

**Sources**

- Wang et al., *Self-Consistency Improves Chain of Thought Reasoning in Language
  Models*, ICLR 2023 — <https://arxiv.org/abs/2203.11171>
- Fu, Chen et al., *Efficiently Scaling LLM Reasoning with Certaindex* —
  <https://arxiv.org/abs/2412.20993> (ICoT case study §6.7; multi-path
  semantic-entropy certaindex §3.1)
