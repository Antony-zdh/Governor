#!/usr/bin/env python3
"""Build the human grader-error-rate check package (paper appendix).

Samples the frozen dev baseline grading decisions and exports a stratified set
for a human to hand-verify the grader's correct/incorrect verdict, so we can
report the grader's measured error rate. Strata oversample the risky calls:
  - graded CORRECT but answer strings differ  -> equivalence-judgment (false-positive risk)
  - graded WRONG but answer strings are close  -> possible missed equivalence (false-negative risk)
  - random baseline                            -> base-rate estimate
Deterministic (fixed seed). Reproducible from committed frozen baselines.
"""
import json, csv, glob, gzip, random, re, html
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
SEED = 20260729
N_EQUIV, N_CLOSE, N_RANDOM = 34, 26, 30      # ~90 total
DEV = [
    "development__deepseek-ai-deepseek-r1-distill-qwen-7b__{b}__seed_42",
    "development__qwen-qwen3-8b__{b}__seed_42",
]
BENCH = ["math500", "amc23", "aime24"]

def load(fp):
    o = gzip.open if fp.endswith(".gz") else open
    return json.load(o(fp, "rt"))

records = []
for tmpl in DEV:
    for b in BENCH:
        root = FC/"results/governor_v2"/tmpl.format(b=b)/"main"/"traj"
        for fp in glob.glob(str(root/"problem_*.json*")):
            r = load(fp)
            model = "deepseek-7b" if "deepseek" in tmpl else "qwen3-8b"
            records.append(dict(problem_id=r["problem_id"], model=model, benchmark=b,
                                problem=r["problem"], target=str(r["target"]),
                                final_answer=str(r.get("final_answer")),
                                final_correct=bool(r["final_correct"])))
print(f"loaded {len(records)} baseline grading decisions")

def norm(s):
    s = s.lower()
    s = re.sub(r"\\boxed|\\left|\\right|\\!|\\,|\\ |\$|\\text|[{}\s]", "", s)
    s = s.replace("\\frac", "").replace("\\dfrac", "")
    return s

def jacc(a, b):
    A, B = set(norm(a)), set(norm(b))
    return len(A & B)/len(A | B) if (A | B) else 0.0

for r in records:
    r["_same"] = norm(r["final_answer"]) == norm(r["target"])
    r["_jacc"] = jacc(r["final_answer"], r["target"])

equiv = [r for r in records if r["final_correct"] and not r["_same"]]          # correct, strings differ
close = [r for r in records if (not r["final_correct"]) and r["_jacc"] >= 0.5]  # wrong, but close
rng = random.Random(SEED)
rng.shuffle(equiv); rng.shuffle(close)
sample = equiv[:N_EQUIV] + close[:N_CLOSE]
chosen_ids = {(r["model"], r["benchmark"], r["problem_id"]) for r in sample}
pool = [r for r in records if (r["model"], r["benchmark"], r["problem_id"]) not in chosen_ids]
rng.shuffle(pool)
sample += pool[:N_RANDOM]
rng.shuffle(sample)
print(f"strata: equiv={min(len(equiv),N_EQUIV)} close={min(len(close),N_CLOSE)} random={N_RANDOM} -> {len(sample)}")

# ---- CSV ----
with open(HERE/"grader_check_review.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["row", "model", "benchmark", "problem_id", "gold_target",
                "model_final_answer", "grader_verdict",
                "HUMAN_grader_correct?[y/n]", "HUMAN_true_verdict[correct/incorrect]", "HUMAN_notes"])
    for i, r in enumerate(sample, 1):
        w.writerow([i, r["model"], r["benchmark"], r["problem_id"], r["target"],
                    r["final_answer"], "correct" if r["final_correct"] else "incorrect",
                    "", "", ""])

# ---- HTML reference (problem text for ambiguous equivalence calls) ----
parts = ["""<meta charset='utf-8'><style>
body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}
h2{border-top:2px solid #ccc;padding-top:1rem}.meta{background:#f5f5f7;border-radius:8px;padding:.6rem .9rem;margin:.4rem 0}
pre{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.8rem;font:13px/1.45 ui-monospace,monospace}
code{background:#eee;padding:0 .3em;border-radius:3px}b.g{color:#080}b.r{color:#b00}</style>
<h1>Grader-error hand-check — reference</h1>
<p>For each row in <code>grader_check_review.csv</code>: decide whether the grader's
<code>grader_verdict</code> is <b>right</b>. Mark <code>HUMAN_grader_correct?</code> y/n; if n,
put the <code>HUMAN_true_verdict</code>. Two answers count as the same iff mathematically
equivalent (e.g. <code>1/2</code>=<code>0.5</code>=<code>\\frac{1}{2}</code>; <code>(3,\\pi/2)</code>
order/format aside). Use the problem text below only when equivalence is unclear.</p>"""]
for i, r in enumerate(sample, 1):
    v = "g" if r["final_correct"] else "r"
    parts.append(f"<h2>Row {i} — {r['model']} / {r['benchmark']} / problem {r['problem_id']}</h2>")
    parts.append(f"<div class='meta'>gold: <b>{html.escape(r['target'])}</b> &nbsp;|&nbsp; "
                 f"model answer: <b>{html.escape(r['final_answer'])}</b> &nbsp;|&nbsp; "
                 f"grader said: <b class='{v}'>{'correct' if r['final_correct'] else 'incorrect'}</b></div>")
    parts.append(f"<details><summary>problem text</summary><pre>{html.escape(r['problem'])}</pre></details>")
(HERE/"grader_check_reference.html").write_text("\n".join(parts), encoding="utf-8")

(HERE/"CODEBOOK_grader.md").write_text(f"""# Grader-error hand-check — instructions

**Goal.** Verify whether the automatic grader's correct/incorrect verdict is right, on a
stratified sample of {len(sample)} baseline decisions, so we can report the grader's true
error rate (this underpins a very thin accuracy margin, so it matters).

**What you get.**
- `grader_check_review.csv` — one row per decision. Fill `HUMAN_grader_correct?` (y/n),
  and if n, `HUMAN_true_verdict` (correct/incorrect), plus optional `HUMAN_notes`.
- `grader_check_reference.html` — the gold answer, model answer, grader verdict, and the
  problem text (collapsible) for each row.

**Rule.** The model answer is *correct* iff it is **mathematically equivalent** to the gold
answer — regardless of formatting (`1/2` = `0.5` = `\\frac{{1}}{{2}}`; equivalent sets/tuples;
simplified vs unsimplified). It is *incorrect* if it is a different value, or the model gave
a letter/label for a non-multiple-choice problem.

**Strata (why these rows).** Most rows are cases where the grader had to make an equivalence
judgment (graded correct but the strings differ) or where a wrong answer looked close — the
places a grader is most likely to slip. A few are random. Just judge each on its merits.

Return the filled `grader_check_review.csv`; we compute the grader error rate = fraction of
rows where `HUMAN_grader_correct? = n`, with a 95% CI.
""", encoding="utf-8")

print("wrote grader_check_review.csv, grader_check_reference.html, CODEBOOK_grader.md")
