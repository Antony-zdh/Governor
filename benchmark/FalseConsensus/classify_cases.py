"""Stage 3: classification of false-consensus cases (Type A-E from plan.md).

Types:
  A 数字坍缩   consensus on a wrong number (arithmetic / derivation slip)
  B 表达式坍缩 consensus on a wrong expression / wrong simplification
  C 符号错误   sign / inequality-direction error
  D 推导遗漏   missing case, missing root, extraneous root kept, misread question
  E 格式问题   probe-format artifacts (e.g. answering "B"/"D" letters to a
              non-multiple-choice problem)

The assignment below was made by reading each exported case (problem text,
probe answers, target); it is a preliminary AI-assisted pass over the Stage 1
run and should be spot-checked manually (plan.md: 人工分类).
"""

import json
import os
import sys
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# problem_id -> (type, short reason)
CLASSIFICATION = {
    4: ("D", "misread the speed graph; long premature 'Carla' consensus, recovered"),
    9: ("A", "consensus on wrong values 8/144, target 4"),
    11: ("E", "converged to letter 'D' on a non-multiple-choice problem"),
    14: ("E", "letter 'D' consensus mid-run on a non-MC problem"),
    18: ("A", "wrong angle values 32/56, target 28"),
    19: ("A", "consensus on a=2, target a=3"),
    22: ("A", "consensus on 4, target 5"),
    23: ("D", "kept extraneous root x=7 without checking, target 5"),
    25: ("D", "reported only n=1, missed n=-2 (target '1,-2')"),
    33: ("E", "hallucinated options, converged to letter 'B'"),
    34: ("A", "consensus on 45, target -125 (binomial term slip)"),
    36: ("D", "reported only root 3, missed 5 and 7"),
    39: ("A", "wrong GCF -> consensus 143, target 23"),
    43: ("A", "consensus on 130, target 70*sqrt(2)"),
    46: ("D", "had correct 6, revised to 12 and held it (overthinking)"),
    58: ("A", "arithmetic slip 9801 vs 9901"),
    59: ("A", "inclusion-exclusion slip -> 13, target 5"),
    64: ("A", "consensus on 16/0, target 35/64"),
    68: ("A", "consensus on 37/32, target 46"),
    73: ("E", "letter 'D' consensus on a non-MC problem"),
    74: ("B", "collapsed expression to 0, target cot x"),
    75: ("E", "letter 'B'/'D' consensus on a non-MC problem"),
    76: ("A", "consensus on 2, target 0"),
    89: ("A", "consensus on 63, target gcd=21"),
    90: ("D", "answered the division result 15 instead of the multiplier 3/2"),
    92: ("E", "letter consensus on a non-MC problem"),
    95: ("A", "consensus on 3, target -4"),
    96: ("D", "reported only root 1, missed the other real root"),
}

# English labels for figures (server fonts lack CJK glyphs)
TYPE_NAMES = {
    "A": "A Wrong number",
    "B": "B Wrong expression",
    "C": "C Sign error",
    "D": "D Missing case / step",
    "E": "E Format artifact (MC letters)",
}
# dataviz categorical palette, slots 1-5 (light)
TYPE_COLORS = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a", "D": "#eda100", "E": "#e87ba4"}


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "results/stage1_logging/analysis"
    cases_path = os.path.join(out_dir, "false_consensus_cases.json")
    with open(cases_path, encoding="utf-8") as f:
        cases = {c["problem_id"]: c for c in json.load(f)}

    missing = sorted(set(cases) - set(CLASSIFICATION))
    extra = sorted(set(CLASSIFICATION) - set(cases))
    if missing:
        print("WARNING: unclassified cases:", missing)
    if extra:
        print("WARNING: classified but not exported:", extra)

    counts = Counter(t for t, _ in CLASSIFICATION.values())
    labels = [k for k in "ABCDE" if counts.get(k)]

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.pie(
        [counts[k] for k in labels],
        labels=[f"{TYPE_NAMES[k]}\n{counts[k]} ({counts[k] / sum(counts.values()):.0%})" for k in labels],
        colors=[TYPE_COLORS[k] for k in labels],
        startangle=90,
        counterclock=False,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 10, "color": "#0b0b0b"},
    )
    ax.set_title("Figure 3 · False consensus types (n=%d)" % sum(counts.values()))
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig3_types_pie.png"), dpi=200)

    out = {
        "counts": {TYPE_NAMES[k]: counts.get(k, 0) for k in "ABCDE"},
        "cases": [
            {"problem_id": pid, "type": t, "reason": r}
            for pid, (t, r) in sorted(CLASSIFICATION.items())
        ],
    }
    with open(os.path.join(out_dir, "classification.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out["counts"], ensure_ascii=False, indent=2))
    print("Wrote fig3_types_pie.png and classification.json to", out_dir)


if __name__ == "__main__":
    main()
