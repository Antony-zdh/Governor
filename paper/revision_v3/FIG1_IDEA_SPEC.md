# Figure 1 — idea figure: drawing specification (issue 8)

Target: ACL `figure*` (double-column), **7.0 in × 2.75 in**, vector, no raster.
Built as editable `.pptx` (one slide sized 7.0×2.75 in, all native shapes and
text boxes) → exported to `paper/figures/gen/fig1_idea.pdf`.

Source narrative: `CORE_PAPER_FLOW.md`, beats 1–5.

---

## 0. Design intent

The reader must get three things in one glance, in this order:

1. **What breaks** — probes agree while the answer is still moving.
2. **How hard we looked** — 3,520 preregistered rules, gates fixed in advance,
   and *nothing* survives.
3. **Why it's the signal, not the idea** — the same machinery, run on a
   non-consensus signal, passes.

The figure is a left-to-right argument, not a system diagram. Nothing in it is
an architecture; every box is a step in a claim.

**One-line takeaway, set as a band across the bottom:**
> Early exit is possible — the consensus *signal* is what cannot make it safe.

---

## 1. Palette (matches `report/make_generalization_figs.py`, colourblind-safe)

| role | hex | used for |
|---|---|---|
| ink | `#1F2328` | all body text, arrows |
| muted ink | `#6B7280` | secondary labels, axis text |
| **consensus / failure** | `#F59E0B` fill, `#B45309` text | consensus rule space, the ✗ verdict |
| failure accent | `#DC2626` | the wrong probe answers, "0 / 3,520" |
| **DEER / success** | `#059669` fill, `#065F46` text | boundary-confidence branch, ✓ verdict |
| correct answer | `#059669` | the green probe/final answer |
| panel fill | `#F8F9FA` | panel backgrounds |
| panel border | `#D9DDE1`, 0.75 pt | panel outlines |
| gate shading | `#E5E7EB` | the sieve/gate glyph |

Fonts: **Helvetica / Arial**. Panel titles 9 pt bold, body 7.5 pt, small
annotations 6.5 pt, the bottom band 8.5 pt bold. Math in text form (`W`, `s`,
`τ`) — no LaTeX.

---

## 2. Layout

```
┌───────────────────────┬────────────────────────┬───────────────────────┐
│  A  The bet fails     │  B  We searched hard   │  C  It's the signal   │
│     (~30% width)      │     (~38%)             │     (~32%)            │
├───────────────────────┴────────────────────────┴───────────────────────┤
│  Early exit is possible — the consensus SIGNAL is what cannot make it safe │
└────────────────────────────────────────────────────────────────────────┘
```

Panels are three rounded rectangles (corner radius 0.04 in), fill `#F8F9FA`,
border `#D9DDE1`, separated by 0.10 in gutters. Bottom band is full width,
0.30 in tall, fill `#1F2328`, text white.

Between panels A→B and B→C: a chevron arrow (`#6B7280`, 1.25 pt) sitting in the
gutter at mid-height, with the connecting question set above it in 6.5 pt
italic muted ink:

- A→B: *"so can any consensus rule be safe and saving?"*
- B→C: *"is early exit itself impossible?"*

These two questions are beats 2 and 4 of `CORE_PAPER_FLOW` and are what turn
three panels into an argument.

---

## 3. Panel A — "Agreement is not terminality"

Subtitle (7 pt, muted): *the probe stream of one real trajectory*

**A horizontal token axis** at the panel's vertical centre: a thin `#6B7280`
line, left end labelled `0`, right end labelled `generated tokens`, small tick
marks. Above the axis sit **11 small rounded squares** (0.15 in), one per probe,
evenly spaced, each containing its probe answer in 6 pt:

```
 37   37   37   37   37   37   37   37   —   41   46
 └──────── red, identical ─────────┘   grey  amber  green
                  ▲
             ✗ STOP HERE
        "8 probes agree — commit"
```

- squares 1–8: fill `#FEE2E2`, border `#DC2626`, text `#991B1B`, value `37`
- square 9: fill `#F3F4F6`, border `#D1D5DB`, an em-dash (an invalid probe)
- square 10: fill `#FEF3C7`, border `#F59E0B`, value `41`
- square 11: fill `#D1FAE5`, border `#059669`, text `#065F46`, value **`46`**,
  drawn 1.3× larger with a small `✓` above it and the label
  **`final answer (correct)`** in 6.5 pt `#065F46`

Under square 5, a `▲` marker in `#DC2626` with a two-line callout:
**`consensus fires`** (7 pt bold `#991B1B`) / `stops on a wrong answer`
(6.5 pt `#6B7280`).

A brace or light bracket spans squares 5→11 with the label
**`the answer was still moving`** in 7 pt italic `#1F2328`.

**Badge**, bottom-right of the panel, a small pill (fill `#FEF3C7`, border
`#F59E0B`): **`harm : rescue ≈ 45 : 1`** with `at an aggressive stop` beneath in
5.5 pt. *(Pending issue 1 — if the paper agent settles on the range phrasing,
change to `45:1 → 2:1` and see §6 below.)*

> **Exemplar is real, not invented.** DeepSeek-R1-Distill-Qwen-7B, MATH500
> problem 68, seed 42, dense 64-token probes: 10 consecutive probes read `37`,
> gold is `46`, and the trajectory's own final answer is correct. Use the true
> stream if the drawn version reads cleanly; otherwise this schematised version
> is faithful to it and the caption should say "schematic of a real trajectory
> (MATH500 #68)". Pid 253 (`D` × 20 probes against gold `1/8`) is the stronger
> alternative if we want the format-hallucination point in Figure 1.

---

## 4. Panel B — "3,520 rules, gates fixed in advance, nothing survives"

Subtitle (7 pt, muted): *preregistered sweep on frozen trajectories*

Vertical flow, four rows, each 0.34 in tall, centred:

**Row 1 — the evidence base.** A wide flat box, fill white, border `#D9DDE1`:
`18 frozen environments` (8 pt bold) / `2 models × 3 benchmarks × 3 seeds`
(6.5 pt muted). A small snowflake or lock glyph at its left edge to signal
*frozen — replayed, never re-generated*.

**Row 2 — the rule space.** A miniature **W × s grid**, 8 columns × 3 rows of
0.055 in cells, fill `#FDE68A`, border `#F59E0B`, with `W = 1…30` beneath and
`s = 0.6/0.8/1.0` to the left in 5.5 pt. To its right, in `#B45309`:
**`3,520 consensus rules`** (8.5 pt bold).
This grid must be visually the *same object* as Figure 3's heatmap — same
orientation, same axis labels — so the reader recognises it later.

**Row 3 — the gates.** A trapezoid (sieve) in `#E5E7EB` with `#9CA3AF` border,
narrowing downward, labelled inside in 6.5 pt:
`drop ≤ 1.0 pp` / `saving ≥ 10%` / `psf ≥ 0.80`, and to its right in 6 pt
muted italic: **`fixed before we looked`**. Three small amber dots enter the top
of the sieve; **none** exit the bottom.

**Row 4 — the verdict.** A solid box, fill `#B45309`, white text:
**`0 / 3,520`** (13 pt bold) with `clear any gate` (7 pt) beneath.
Immediately under, in 6.5 pt `#6B7280`, the two-sided squeeze that makes the
result readable at a glance:
`drop ≤ 1 pp → 0.2% saved` · `save 10% → 2.7 pp lost`

---

## 5. Panel C — "The same machinery, a different signal"

Subtitle (7 pt, muted): *identical pipeline, gates, and token accounting*

**Row 1 — the contrast, as two labelled inputs into one pipe.** Two small
rounded boxes side by side feeding a single grey pipe glyph:

- left: fill `#FEF3C7`, border `#F59E0B` — `consensus` / `"do recent probes agree?"` (6 pt)
- right: fill `#D1FAE5`, border `#059669` — `DEER` / `"is the model confident at a reasoning boundary?"` (6 pt)

The pipe is drawn as a narrow grey rounded rectangle labelled in 6 pt white
`same sweep · same gates · same accounting`. This is the controlled-experiment
point and must be unmissable — it is what licenses the whole claim.

**Row 2 — the two verdicts,** as a stacked pair of result chips:

| | |
|---|---|
| `✗` chip, `#B45309` | `consensus  0 / 3 gates` |
| `✓` chip, `#059669` | `DEER  3 / 3 gates` — `−0.3 pp @ 28% saved` |

**Row 3 — generalization strip.** A single row of four small check chips
(fill `#ECFDF5`, border `#059669`, text `#065F46`, 6 pt), preceded by the label
`holds on:` in 6.5 pt muted:

`held-out test ✓` · `4× scale (32B) ✓` · `new architecture (Llama) ✓` · `3 benchmarks ✓`

with, beneath in 6 pt `#B45309`: `consensus: gate stays empty on every one`.

---

## 6. Caption (draft — paper agent to finalise wording)

> **Figure 1: The argument in one picture.** *(a)* Intermediate probe agreement
> is not terminal: on a real trajectory the model emits the same wrong answer
> for eight consecutive probes before its own continued reasoning recovers the
> correct one, so a consensus stop destroys the recovery. *(b)* We test whether
> *any* consensus rule escapes this: a preregistered sweep of 3,520 rules
> (window size W × share threshold s, plus operational knobs) replayed on 18
> frozen environments, against acceptance gates fixed before the sweep was run.
> None clears any gate — capping the accuracy drop at 1 pp permits 0.2% token
> saving, and demanding 10% saving costs 2.7 pp. *(c)* The failure is the
> *signal*, not early exit: swept through the identical pipeline, gates, and
> token accounting, a boundary-confidence method (DEER) clears all three gates
> and holds on a held-out split, at 4× scale, and on a different architecture,
> where consensus's gate stays empty.

---

## 7. Dependencies on the paper agent (issues 1–6)

| item in this spec | depends on |
|---|---|
| Panel A badge `45 : 1` | **issue 1** — if the abstract moves to the range, redraw as `45:1 → 2:1 (only where it stops firing)` and point the reader at Figure 6 |
| Panel B "frozen / preregistered" wording | **issue 3** — should mirror the new one-sentence train/dev/test statement verbatim |
| Panel C pipe label | **issue 4** — must use whatever §4/§5 settle on for the controlled-comparison phrasing |
| all panel titles | **issue 6** — keep them plain and declarative; no "Unveiling"/"Towards" register |

Nothing in the figure depends on Table 3 / TJE (issue 5).

---

## 8. Build notes

- `python-pptx`, slide size 7.0 × 2.75 in; every element a native
  `MSO_SHAPE` or text box (no images) so it stays editable in PowerPoint.
- Export: LibreOffice headless → PDF, then crop to the slide bounds.
- Keep all text ≥ 5.5 pt at final size (ACL floor for legibility).
- Deliverables: `paper/figures/gen/fig1_idea.pptx` (editable source, committed)
  and `paper/figures/gen/fig1_idea.pdf` (included by LaTeX).
