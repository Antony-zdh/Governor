# Grader-error hand-check — instructions

**Goal.** Verify whether the automatic grader's correct/incorrect verdict is right, on a
stratified sample of 89 baseline decisions, so we can report the grader's true
error rate (this underpins a very thin accuracy margin, so it matters).

**What you get.**
- `grader_check_review.csv` — one row per decision. Fill `HUMAN_grader_correct?` (y/n),
  and if n, `HUMAN_true_verdict` (correct/incorrect), plus optional `HUMAN_notes`.
- `grader_check_reference.html` — the gold answer, model answer, grader verdict, and the
  problem text (collapsible) for each row.

**Rule.** The model answer is *correct* iff it is **mathematically equivalent** to the gold
answer — regardless of formatting (`1/2` = `0.5` = `\frac{1}{2}`; equivalent sets/tuples;
simplified vs unsimplified). It is *incorrect* if it is a different value, or the model gave
a letter/label for a non-multiple-choice problem.

**Strata (why these rows).** Most rows are cases where the grader had to make an equivalence
judgment (graded correct but the strings differ) or where a wrong answer looked close — the
places a grader is most likely to slip. A few are random. Just judge each on its merits.

Return the filled `grader_check_review.csv`; we compute the grader error rate = fraction of
rows where `HUMAN_grader_correct? = n`, with a 95% CI.
