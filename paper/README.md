# False Consensus — paper source

ACL-style LaTeX source for *False Consensus: The Limits of Confidence-Based
Early Exit in Reasoning LLMs*. Narrative follows
`benchmark/FalseConsensus/PAPER_STORYLINE.md`.

## Build

```bash
cd paper
pdflatex -interaction=nonstopmode acl_latex.tex
bibtex acl_latex
pdflatex -interaction=nonstopmode acl_latex.tex
pdflatex -interaction=nonstopmode acl_latex.tex
```

Produces `acl_latex.pdf` (currently 12 pages). Requires the `multirow` package to
be **absent** or the preamble line removed (it is not used). Tested with TeX Live
2025 `pdflatex` + `bibtex`.

## Layout

- `acl_latex.tex` — main file; `\input`s each section.
- `sections/` — one file per part (`00_abstract` … `A_appendix`).
- `custom.bib` — references. Entries tagged `VERIFY` (on the line *above* the
  entry, since BibTeX has no `%` comments) need bibliographic checking.
- `acl.sty`, `acl_natbib.bst` — official ACL style (unmodified).

## Status markers

- `\pending{...}` renders in **red** and marks numbers/claims not yet frozen
  (baselines, held-out confirmation, cells not re-verified this pass). Grep:
  ```bash
  grep -rn "pending" sections/
  ```
- Everything else is a verified/frozen number (see `PAPER_STORYLINE.md` §4 for
  the FROZEN/PENDING ledger).

## What is frozen vs pending (summary)

| Section | Content | State |
|---|---|---|
| 3 False Consensus | Stage 1–5 numbers (MATH500, DeepSeek-7B) | FROZEN |
| 4 Method | preregistered protocol, gates, splits | FROZEN |
| 5 Results | 17,712 rules, 1.85pp floor, 4.87pp, family frontier, adaptive table | FROZEN (dev) |
| 5 Results | main comparison table (Governor/baseline cells) | PENDING |
| 6 Mechanism | accuracy-tax/probe-tax split (concept) | FROZEN; gross/net + direction-of-effect numbers PENDING |
| 7 Baselines | CertaIndex/Entropy/Patience | PENDING (colleague run + our repro) |
| — | held-out confirmation (test, Llama-8B, 32B) | PENDING |

Locally computable pending cells (Governor operating points, full-gen macro
accuracy, gross/net) can be filled from `../benchmark/FalseConsensus/governor_v2/
generated/sweep_*.jsonl.gz` without new GPU runs.
