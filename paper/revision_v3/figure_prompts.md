# Figure-revision prompts (issues 7 & 8)

For a separate agent. Context: the paper is **"False Consensus: Why Intermediate
Agreement Is Not a Safe Early-Exit Signal for Reasoning LLMs."** Narrative =
`CORE_PAPER_FLOW.md` (5 beats). Current figures are **all** token-saving ×
accuracy-drop Pareto scatter/frontier panels (`figures/gen/fig_splits.pdf`,
`fig_models.pdf` 2×2, `fig_bench.pdf` 3-panel → ~10 near-identical panels). Data
+ existing plot code: `benchmark/FalseConsensus/report/make_generalization_figs.py`,
`report/make_v2_pareto.py`; committed banks under
`benchmark/FalseConsensus/results/governor_v2_ws_sweep/` (dev/test/heldout),
`report/figures/gen/oracle_cache.json`, and the §4.1 replay
`results/governor_v2_ws_sweep/false_consensus_16k_report.txt`. Read the
`dataviz` skill before drawing. All numbers must come from committed banks.

---

## Issue 7 — diversify the figure set (execute)

**Problem.** ~10 panels are the same Pareto scatter; visually monotonous and
under-uses the evidence. **Goal:** keep ONE canonical Pareto and replace the rest
with figures that each carry a *distinct* claim from a different visual family.

**Keep exactly one Pareto** as the generalization anchor (prefer the current
Figure 1 `fig_splits`, train→dev→test). Consolidate `fig_models`/`fig_bench` into
a single small-multiple or move to appendix; do not keep three separate Pareto
figures in the main body.

**Add these, each tied to a beat (pick the 4–5 highest-impact):**

1. **"The answer is still moving" (beat 1, phenomenon).** For ~4–6 representative
   MATH500 problems, plot the probe answer vs. token position as a step/lane
   chart: color each probe by whether it equals the *final* answer; mark the
   naive-stop firing point and the true settle point. Shows recovery visually.
   Data: dense probe banks + `false_consensus_16k.py` logic.
2. **Harm-to-rescue vs. window (beat 5, mechanism).** Line/bar of the
   recovery-destroyed : wrong-banked ratio across `W∈{1,3,5,8,12,16,24,30}`
   (~45:1 → ~2:1) with a second axis / paired bars for net saving and fire count
   — makes the "low ratio only where saving≈0" trade-off legible. (Compute the
   per-W ratio from the sweep; not yet in a committed report — recompute and save.)
3. **Accuracy vs. consensus-formation time (beat 1, fact 3).** Binned bar of
   final accuracy by the token at which consensus forms (<512 … >2048: 91%→72%),
   with n per bin. From `false_consensus_16k_report.txt` (extend the script to
   emit per-bin counts).
4. **CertaIndex collapse (beat 3/4).** Simple grouped bar: accuracy and stop-rate
   for Full-gen vs. CertaIndex vs. DEER (from `tab:baselines`) — the "shipped
   consensus method pays the tax in full" in one glance.
5. **Selection → generalization as movement (beat 2–4).** Instead of a static
   scatter, draw arrows from each train-gate-winning consensus rule's train
   position to its dev/test position (drop ↑, saving ↓, leaving the gate box),
   with the three DEER operating points staying inside — a "candidates fall out,
   DEER holds" motion chart.

**Constraints:** consistent color language across all figures (consensus =
grey/orange and *fails*; DEER = green and *clears*; oracle = purple; gate boxes
shaded). Colorblind-safe, works in grayscale. Regenerate from committed banks;
save new scripts under `report/` and PDFs to `paper/figures/gen/`. Update the
`\includegraphics`/captions in `sections/01_introduction.tex` and
`sections/05_results.tex`, then recompile (`pdflatex … acl_latex`).

---

## Issue 8 — Figure 1 as an idea/schematic figure (drawing description)

**Deliverable:** a schematic "what we did" figure (the visual of
`CORE_PAPER_FLOW.md`), drawn in **PowerPoint**, exported to
`paper/figures/idea_figure.pdf`, and placed as the new Figure 1 in the
introduction (demote the current Pareto `fig_splits` to §4.5 or keep as Figure 2).
A reader should grasp the whole logic in one glance.

**Layout: left→right pipeline of 5 stages, each a labeled panel with an icon and
a one-line takeaway.**

1. **Phenomenon (agreement ≠ terminality).** A reasoning trajectory as a long
   arrow; periodic probe "pins" reading off a boxed answer; the read-off answer
   *changes* along the way (e.g., `B → 7 → 12 → 12`), a red "stop here?" marker
   at an early agreement, and the true final answer `12` at the end. Caption:
   *"Probes agree while the answer is still moving."*
2. **The question.** A 2-D knob panel for the consensus rule space: window size
   `W` × share threshold `s` (→ 3,520 rules). Caption: *"Can any consensus rule
   be safe *and* saving?"*
3. **Preregistered sweep + gates → NO.** A small Pareto inset (saving × drop)
   with three shaded gate boxes in the safe corner and the consensus cloud/
   frontier missing all of them. Big result stamp: **0 / 3,520 clear any gate.**
4. **Same pipeline, different signal → YES.** The identical gate boxes with the
   DEER frontier + three green stars (C/B/T) *inside* them. Caption: *"The failure
   is the signal, not early exit."* Show DEER and consensus entering the *same*
   gate box to stress the controlled comparison.
5. **Mechanism.** A small cartoon: probing *forces* the model to emit a
   placeholder/guess before it has settled (a thought bubble "…not sure yet" but
   the box says "12"); a longer window = a longer buffer but the systematic risk
   remains. Caption: *"Forced probing masks the model's true estimate."*

**Style:** horizontal flow with arrows between stages; consistent palette
(consensus grey/orange = fails; DEER green = clears; gate boxes light-shaded);
large readable stage titles + one-line captions; minimal text. Keep it one row
(single-column) or a 2×3 grid if width-constrained. Export vector PDF; embed as
`\includegraphics[width=\textwidth]{figures/idea_figure.pdf}` with a caption that
names the five beats. Recompile and check it renders full-width without
overflowing the column.
