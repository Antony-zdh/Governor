#!/usr/bin/env python3
"""Build the human-review package for the false-consensus error taxonomy (paper Sec 3).

Inputs (committed):
  results/stage1_logging/analysis/false_consensus_cases.json   (134 stopped-but-wrong cases)
  results/stage1_logging/analysis/classification.json          (AI initial labels for 28)
Outputs (this dir):
  taxonomy_review.csv        one row per case; reviewer fills human_type + human_notes
  taxonomy_reference.html    self-contained; each case w/ problem, probes, full reasoning
  CODEBOOK.md                category definitions + instructions
"""
import json, csv, html
from pathlib import Path
from itertools import groupby

HERE = Path(__file__).resolve().parent
FC = HERE.parent
cases = json.load(open(FC/"results/stage1_logging/analysis/false_consensus_cases.json"))
cls = json.load(open(FC/"results/stage1_logging/analysis/classification.json"))
ai = {c["problem_id"]: c for c in cls["cases"]}
cases.sort(key=lambda c: c["problem_id"])

def rle(seq):
    out = []
    for k, g in groupby(seq):
        n = len(list(g))
        out.append(f"{k}×{n}" if n > 1 else f"{k}")
    return ", ".join(out)

# ---- CSV (data entry) ----
with open(HERE/"taxonomy_review.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["problem_id", "target_gold", "stop_answer_wrong", "final_answer",
                "final_correct", "n_probes", "probe_stream_rle",
                "ai_type", "ai_reason", "HUMAN_type[A-E]", "HUMAN_confident[y/n]", "HUMAN_notes"])
    for c in cases:
        a = ai.get(c["problem_id"], {})
        w.writerow([c["problem_id"], c["target"], c.get("stop_answer"), c.get("final_answer"),
                    c.get("final_correct"), len(c.get("probe_answers", [])),
                    rle(c.get("probe_answers", [])), a.get("type", ""), a.get("reason", ""),
                    "", "", ""])

# ---- HTML reference ----
CATS = [("A", "Numeric collapse — stable convergence to a WRONG number"),
        ("B", "Expression collapse — wrong non-numeric expression"),
        ("C", "Sign error"),
        ("D", "Derivation gap — dropped root/case, unverified/unfinished step"),
        ("E", "Format/option hallucination — non-MC problem emitting a letter (probe artifact)")]
parts = ["""<meta charset='utf-8'><style>
body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#111}
h2{border-top:2px solid #ccc;padding-top:1rem;margin-top:2rem}
.meta{background:#f5f5f7;border-radius:8px;padding:.6rem .9rem;margin:.5rem 0}
.wrong{color:#b00}.right{color:#080}.ai{background:#fff7e6;border-left:3px solid #e0a800;padding:.4rem .8rem;margin:.4rem 0}
pre{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.8rem;font:13px/1.45 ui-monospace,monospace}
details>summary{cursor:pointer;color:#06c;margin:.4rem 0}code{background:#eee;padding:0 .3em;border-radius:3px}
</style>
<h1>False-consensus error taxonomy — case reference</h1>
<p>Assign each case ONE type (A–E). Definitions:</p><ul>"""]
for k, d in CATS:
    parts.append(f"<li><b>{k}</b> — {html.escape(d)}</li>")
parts.append("</ul><p>Record your label in <code>taxonomy_review.csv</code> (columns "
             "<code>HUMAN_type</code>, <code>HUMAN_confident</code>, <code>HUMAN_notes</code>). "
             "The AI's initial guess (28 cases) is shown in orange — confirm or overrule it.</p>")
for c in cases:
    a = ai.get(c["problem_id"], {})
    fc = "right" if c.get("final_correct") else "wrong"
    parts.append(f"<h2>Problem {c['problem_id']}</h2>")
    parts.append(f"<div class='meta'>gold target: <b>{html.escape(str(c['target']))}</b> &nbsp;|&nbsp; "
                 f"stopped-on (WRONG): <b class='wrong'>{html.escape(str(c.get('stop_answer')))}</b> &nbsp;|&nbsp; "
                 f"full-reasoning answer: <b class='{fc}'>{html.escape(str(c.get('final_answer')))}</b> "
                 f"({'correct' if c.get('final_correct') else 'incorrect'})</div>")
    parts.append(f"<div class='meta'>probe stream ({len(c.get('probe_answers',[]))}): "
                 f"{html.escape(rle(c.get('probe_answers',[])))}</div>")
    if a:
        parts.append(f"<div class='ai'>AI initial label: <b>{a.get('type')}</b> — {html.escape(a.get('reason',''))}</div>")
    parts.append(f"<p><b>Problem:</b></p><pre>{html.escape(c['problem'])}</pre>")
    parts.append(f"<details><summary>full model reasoning ({len(c.get('full_text',''))} chars)</summary>"
                 f"<pre>{html.escape(c.get('full_text',''))}</pre></details>")
(HERE/"taxonomy_reference.html").write_text("\n".join(parts), encoding="utf-8")

# ---- CODEBOOK ----
(HERE/"CODEBOOK.md").write_text(f"""# Error-taxonomy human review — instructions

**Goal.** Independently assign each of the {len(cases)} *stopped-but-wrong* cases a single
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
""", encoding="utf-8")

print(f"wrote taxonomy_review.csv ({len(cases)} rows), taxonomy_reference.html, CODEBOOK.md")
print(f"AI-prelabeled: {len(ai)}; to-label-fresh: {len(cases)-len(ai)}")
