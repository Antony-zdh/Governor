#!/usr/bin/env python3
"""Build the ONE-FILE interactive grader-error hand-check page (paper appendix).

Samples the frozen dev baseline grading decisions and exports a stratified set
for a human to hand-verify the grader's correct/incorrect verdict, so we can
report the grader's measured error rate. Strata oversample the risky calls:
  - graded CORRECT but answer strings differ  -> equivalence-judgment (false-positive risk)
  - graded WRONG but answer strings are close  -> possible missed equivalence (false-negative risk)
  - random baseline                            -> base-rate estimate
Deterministic (fixed seed). Reproducible from committed frozen baselines.

Output (this dir):
  taskB_grader.html   self-contained: instructions + all sampled rows + in-page
                      judging + one-click CSV export. This is the only file to send.
"""
import json, glob, gzip, random, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_interactive import render_page

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

COLUMNS = ["row", "model", "benchmark", "problem_id", "gold_target",
           "model_final_answer", "grader_verdict",
           "HUMAN_grader_correct?[y/n]", "HUMAN_true_verdict[correct/incorrect]", "HUMAN_notes"]

FIELDS = [
    {"key": "HUMAN_grader_correct", "label": "grader 判对了吗 (必填)", "type": "select", "options": [
        {"value": "", "label": "— 选择 —"}, {"value": "y", "label": "y 判对了"},
        {"value": "n", "label": "n 判错了"}]},
    {"key": "HUMAN_true_verdict", "label": "若判错→正确判定应为", "type": "select", "options": [
        {"value": "", "label": "—"}, {"value": "correct", "label": "correct"},
        {"value": "incorrect", "label": "incorrect"}]},
    {"key": "HUMAN_notes", "label": "备注（可选）", "type": "text"},
]

records_out = []
for i, r in enumerate(sample, 1):
    verdict = "correct" if r["final_correct"] else "incorrect"
    records_out.append({
        "row": i, "model": r["model"], "benchmark": r["benchmark"], "pid": r["problem_id"],
        "gold": r["target"], "ans": r["final_answer"], "correct": bool(r["final_correct"]),
        "problem": r["problem"],
        "csv": [i, r["model"], r["benchmark"], r["problem_id"], r["target"],
                r["final_answer"], verdict],
    })

INTRO = f"""
<p><b>目标：</b>核对自动 grader 的 <code>correct/incorrect</code> 判定对不对，共 {len(sample)} 条(分层抽样)，用来报告 grader 的真实错误率(它撑着一个很薄的准确率边际，很关键)。</p>
<p><b>怎么做：</b>每条给出 <b>正解</b>、<b>模型答案</b>、<b>grader 判定</b>;判断这个判定对不对。选 <code>grader 判对了吗 y/n</code>;若 <b>n</b>，再选正确判定 <code>correct/incorrect</code>。等价性不明时展开题目看。进度自动存浏览器，刷新不丢，标完点顶栏 <b>下载 CSV</b> 交回。</p>
<p><b>判定规则：</b>模型答案与正解<b>数学等价</b>即为 <i>correct</i>，不看格式(<code>1/2</code> = <code>0.5</code> = <code>\\frac{{1}}{{2}}</code>;集合/元组等价即可，次序/写法不计)。值不同、或非选择题却给了字母/标签，则为 <i>incorrect</i>。</p>
<p><b>为什么是这些行：</b>大多是 grader 需要做等价判断(判对但字符串不同)或错答但很接近的情形——最容易判错的地方;少量随机。逐条按事实判断即可。</p>
"""

html = render_page(title="grader 判分核对 (Task B)", intro_html=INTRO,
                    columns=COLUMNS, fields=FIELDS, data=records_out,
                    task_id="grader", file_prefix="grader_check_review")
out = HERE/"taskB_grader.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out.name}  ({len(sample)} rows, {out.stat().st_size} bytes)")
