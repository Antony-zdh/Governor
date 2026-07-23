"""Stage 8 (prep) - select the fixed 100-problem subset for the Improved
Probe Comparison (plan.md SS6.3). Runs entirely offline against the existing
Stage 1 logs (probes.csv + traj/*.json) - no model server needed. The GPU
part (run_probe_variants.py) consumes subset.json produced here.

plan.md SS6.3 says only: "easy / medium / hard 分层；包含空答案、字母伪影、
翻盘案例". The exact selection rule below is my own concrete interpretation,
documented here rather than left implicit:

  1. Guarantee up to SPECIAL_QUOTA problems each from three special
     categories (a problem can land in more than one, dedup keeps it once):
       - has_empty_probe:  at least one empty probe answer anywhere in the
         problem's trajectory
       - has_single_letter_probe: at least one probe whose normalized
         answer is a single letter A-D (multiple-choice-shaped artifact)
       - has_flip: a 3-consecutive-equal-nonempty run of probe answers that
         is followed by a different answer later (the "flip" case from
         Stage 6's consistent3_then_switch group, computed per-problem here)
  2. Fill the remaining slots with a MATH-level-stratified random sample
     (proportional to the full 500-problem set's level distribution) drawn
     from problems NOT already selected.
  3. Dedup, fixed seed=42, target total = 100 (documented exactly, not
     silently rounded).
"""

import argparse
import json
import os
import random
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from analyze import eq  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "TokenDeprivation"))
from utils import load_dataset  # noqa: E402

SINGLE_LETTER_RE = re.compile(r"^[A-Da-d]$")
SPECIAL_QUOTA = 15
TARGET_TOTAL = 100
SEED = 42


def has_flip(probe_answers):
    for i in range(len(probe_answers) - 3):
        a, b, c, d = probe_answers[i : i + 4]
        if a == "" or b == "" or c == "":
            continue
        if eq(a, b) and eq(b, c) and not eq(c, d) and d != "":
            return True
    return False


def compute_flags(df):
    flags = {}
    for pid, g in df.sort_values("probe_id").groupby("problem_id"):
        answers = [str(a) if pd.notna(a) else "" for a in g["probe_answer"]]
        flags[pid] = {
            "has_empty": any(a == "" for a in answers),
            "has_single_letter": any(SINGLE_LETTER_RE.match(a) for a in answers),
            "has_flip": has_flip(answers),
        }
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="math500")
    ap.add_argument(
        "--input", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage1_logging")
    )
    ap.add_argument("--output", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--total", type=int, default=TARGET_TOTAL)
    args = ap.parse_args()
    os.makedirs(args.output, exist_ok=True)

    df = pd.read_csv(os.path.join(args.input, "probes.csv"))
    dataset = load_dataset(args.dataset)
    level_of = {i: item.get("level") for i, item in enumerate(dataset)}
    subject_of = {i: item.get("subject", "unknown") for i, item in enumerate(dataset)}

    flags = compute_flags(df)
    all_pids = sorted(flags.keys())

    rng = random.Random(SEED)

    def pick(cands, k):
        cands = sorted(cands)
        rng.shuffle(cands)
        return cands[:k]

    selected = {}  # pid -> set of reasons

    for cat in ["has_empty", "has_single_letter", "has_flip"]:
        cands = [pid for pid in all_pids if flags[pid][cat]]
        for pid in pick(cands, SPECIAL_QUOTA):
            selected.setdefault(pid, set()).add(cat)

    remaining_quota = args.total - len(selected)
    if remaining_quota > 0:
        pool = [pid for pid in all_pids if pid not in selected]
        # stratified-by-level proportional sample from the remaining pool
        by_level = {}
        for pid in pool:
            by_level.setdefault(level_of.get(pid), []).append(pid)
        total_pool = len(pool)
        picked = []
        # proportional allocation with largest-remainder rounding
        raw_alloc = {lvl: len(ids) / total_pool * remaining_quota for lvl, ids in by_level.items()}
        alloc = {lvl: int(v) for lvl, v in raw_alloc.items()}
        shortfall = remaining_quota - sum(alloc.values())
        remainders = sorted(raw_alloc.items(), key=lambda kv: kv[1] - int(kv[1]), reverse=True)
        for lvl, _ in remainders[:shortfall]:
            alloc[lvl] += 1
        for lvl, ids in by_level.items():
            picked.extend(pick(ids, alloc.get(lvl, 0)))
        for pid in picked:
            selected.setdefault(pid, set()).add("level_stratified_fill")

    # if rounding left us short/over, adjust deterministically
    selected_ids = list(selected.keys())
    if len(selected_ids) > args.total:
        selected_ids = pick(selected_ids, args.total)
    elif len(selected_ids) < args.total:
        pool = [pid for pid in all_pids if pid not in selected]
        selected_ids += pick(pool, args.total - len(selected_ids))
        for pid in selected_ids:
            selected.setdefault(pid, set())

    subset = []
    for pid in sorted(selected_ids):
        subset.append(
            {
                "problem_id": pid,
                "level": level_of.get(pid),
                "subject": subject_of.get(pid),
                "reasons": sorted(selected[pid]),
                "num_probes": int((df["problem_id"] == pid).sum()),
            }
        )

    out_path = os.path.join(args.output, "subset.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(subset, f, ensure_ascii=False, indent=2)

    # summary report
    lvl_counts = pd.Series([s["level"] for s in subset]).value_counts().sort_index()
    reason_counts = {}
    for s in subset:
        for r in s["reasons"]:
            reason_counts[r] = reason_counts.get(r, 0) + 1
    total_probe_calls_per_design = sum(s["num_probes"] for s in subset)

    lines = []
    lines.append("# Stage 8 subset selection report\n")
    lines.append(f"Selected {len(subset)} problems (target {args.total}), seed={SEED}.\n")
    lines.append("## Level distribution\n")
    lines.append(lvl_counts.to_string())
    lines.append("\n\n## Reason counts (a problem can have multiple)\n")
    for r, c in sorted(reason_counts.items()):
        lines.append(f"- {r}: {c}")
    lines.append(
        f"\n\nTotal existing-probe checkpoints across the subset: {total_probe_calls_per_design} "
        f"(this is how many checkpoints each new probe design (P1_32/P1_64/P2/P3/P4) will be "
        f"re-run on -> ~{total_probe_calls_per_design * 5} total new completion calls for 5 designs)."
    )
    with open(os.path.join(args.output, "subset_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {out_path} and subset_report.md")
    print(f"n={len(subset)}, total checkpoints={total_probe_calls_per_design}")


if __name__ == "__main__":
    main()
