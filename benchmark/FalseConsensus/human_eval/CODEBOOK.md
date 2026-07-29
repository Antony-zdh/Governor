# Error-taxonomy human review — instructions

**Goal.** Independently assign each of the 134 *stopped-but-wrong* cases a single
error type. These are cases where an early-stop rule committed to an answer that a probe
window agreed on, but that answer was wrong (or the full reasoning later changed it).

**What you get.**
- `taxonomy_review.csv` — one row per case. Fill three columns: `HUMAN_type` (A/B/C/D/E),
  `HUMAN_confident` (y/n), `HUMAN_notes` (free text; note any case that fits two types).
- `taxonomy_reference.html` — open in a browser; every case with the problem, the gold
  answer, the wrong stopped-on answer, the full probe stream, and (collapsible) the full
  model reasoning. Read this to judge the type.

**Categories (assign the single best fit).**
- **A. Numeric collapse** — the trajectory stably converges to a WRONG number.
- **B. Expression collapse** — converges to a wrong NON-numeric expression (formula/set/etc.).
- **C. Sign error** — the answer is right in magnitude but wrong in sign.
- **D. Derivation gap** — a dropped root/case, an unverified or unfinished step, a misread.
- **E. Format/option hallucination** — a NON-multiple-choice problem stably emitting a
  letter (e.g. "B", "D"). This is a probe-mechanism artifact, not a model belief.

**Tips.**
- The `ai_type`/`ai_reason` columns are a first-pass AI guess for 28 cases — you may overrule.
- If the wrong answer is a bare letter on a non-MC problem, it is almost always **E**.
- If unsure between D and A/B, ask: was the *value* just wrong (A/B) or did the model skip a
  required case/step (D)? Use `HUMAN_notes` for genuine ties.
- ~15 min for the clear ones; spend reading time only on the ambiguous ones.

Return the filled `taxonomy_review.csv`. We tally the type counts and, if your labels differ
materially from the AI first-pass, your labels win (this is the human review of record).
