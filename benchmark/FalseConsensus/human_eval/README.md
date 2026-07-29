# Human-eval packages (paper §3 error taxonomy + appendix grader error)

Two independent, self-contained human-review tasks. Both use already-committed data — they
do **not** depend on any running experiment. Regenerate either package with its
`make_*_package.py` script.

## Task A — error-taxonomy review (paper §3)  →  ~30–45 min
Label the 134 stopped-but-wrong cases into 5 types (A–E). AI pre-labeled 28; the rest are fresh.
- **Send:** `CODEBOOK.md`, `taxonomy_reference.html` (open in browser), `taxonomy_review.csv`.
- **They do:** fill `HUMAN_type`, `HUMAN_confident`, `HUMAN_notes` for all 134 rows.
- **Back:** filled `taxonomy_review.csv`. We re-tally the A–E counts (currently 14/1/0/7/6 on
  the AI-labeled 28) and, importantly, whether type **E** (probe-format artifact) rate holds.

## Task B — grader-error hand-check (appendix)  →  ~20–30 min
Verify the automatic grader's verdict on a stratified sample of 89 baseline decisions.
- **Send:** `CODEBOOK_grader.md`, `grader_check_reference.html`, `grader_check_review.csv`.
- **They do:** fill `HUMAN_grader_correct?` (y/n) + `HUMAN_true_verdict` if the grader erred.
- **Back:** filled `grader_check_review.csv`. We report grader error rate = fraction wrong,
  with a 95% CI — this backs the thin accuracy margin the reviewers questioned.

## Handoff tips
- Each `*_reference.html` is self-contained (open by double-clicking; no internet needed).
- The CSVs open directly in Excel / Google Sheets.
- Two reviewers on the same sheets would let us report inter-annotator agreement (bonus, not required).
