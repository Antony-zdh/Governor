"""Stage 6a — sample probe-validity audit cases for human annotation.

Reads Stage 1 output (probes.csv + traj/*.json) and samples cases from the
6 groups in plan.md §4.2:
  1. probe_answer == final_answer
  2. probe_answer != final_answer (non-empty)
  3. probe_answer is a single letter (A-D style)
  4. probe_answer == "" (empty / truncated probe)
  5. 3 consecutive equal non-empty answers, then the next probe disagrees
     ("3-consistent-then-switch")
  6. 3 consecutive equal non-empty answers, holding all the way to the last
     probe ("3-consistent-then-holds")

For each sampled (problem_id, probe_id), reconstructs the exact reasoning
prefix at that probe's token_position by re-tokenizing the trajectory's
full_text with the real model tokenizer and slicing the first N tokens —
traj/*.json only stores the final full_text, not per-checkpoint prefixes,
so this is the only way to get what the model had actually generated at
that moment (character-based estimation would be inaccurate).

Outputs:
  probe_audit_cases.jsonl  one case per line, full context per plan.md §4.3
  annotate.html            self-contained annotation tool with the cases
                            embedded inline (no server / fetch needed)
"""

import argparse
import json
import os
import random
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from analyze import eq, load  # noqa: E402

SINGLE_LETTER_RE = re.compile(r"^[A-Da-d]$")


def build_case(pid, probe_id, group_names, df_p, traj, tokenizer, tok_cache, continuation_chars=3000):
    row = df_p[df_p["probe_id"] == probe_id].iloc[0]
    probes = traj["probes"]
    probe_meta = next(p for p in probes if p["probe_id"] == probe_id)

    if pid not in tok_cache:
        ids = tokenizer.encode(traj["full_text"], add_special_tokens=False)
        tok_cache[pid] = ids
    ids = tok_cache[pid]

    tok_pos = int(row["token_position"])
    prefix_ids = ids[: min(tok_pos, len(ids))]
    reasoning_prefix = tokenizer.decode(prefix_ids)
    continuation_ids = ids[min(tok_pos, len(ids)) :]
    continuation = tokenizer.decode(continuation_ids)
    truncated = len(continuation) > continuation_chars
    if truncated:
        continuation = continuation[:continuation_chars] + "\n...[truncated]"

    all_probe_ids = sorted(p["probe_id"] for p in probes)
    idx = all_probe_ids.index(probe_id)
    lo, hi = max(0, idx - 3), min(len(all_probe_ids), idx + 4)
    context_probes = []
    for pi in all_probe_ids[lo:hi]:
        r = df_p[df_p["probe_id"] == pi].iloc[0]
        context_probes.append(
            {
                "probe_id": int(pi),
                "token_position": int(r["token_position"]),
                "answer": r["probe_answer"],
                "is_certain": bool(r["is_certain"]),
                "is_current": pi == probe_id,
            }
        )

    return {
        "case_id": f"{pid}_{probe_id}",
        "problem_id": int(pid),
        "probe_id": int(probe_id),
        "sample_groups": group_names,
        "problem": traj["problem"],
        "reference_answer": traj["target"],
        "token_position": tok_pos,
        "reasoning_prefix": reasoning_prefix,
        "probe_prompt_suffix": "**Final Answer**\n\n\\[ \\boxed{",
        "probe_raw_output": probe_meta["probe_text"],
        "probe_answer_normalized": row["probe_answer"],
        "is_certain": bool(row["is_certain"]),
        "context_probes": context_probes,
        "final_continuation": continuation,
        "continuation_truncated": truncated,
        "final_answer": traj["final_answer"],
        "final_correct": bool(traj["final_correct"]),
        "num_probes_total": len(probes),
    }


def find_switch_and_hold_cases(df_p):
    """Scan a problem's probes in order for 3-consistent-then-{switch,holds}."""
    rows = df_p.sort_values("probe_id")
    ans = rows["probe_answer"].tolist()
    pid_list = rows["probe_id"].tolist()
    switch, holds = [], []
    n = len(ans)
    for i in range(n - 2):
        window = ans[i : i + 3]
        if any(a == "" for a in window):
            continue
        if not all(eq(a, window[0]) for a in window[1:]):
            continue
        # stable run of >=3 found at i..i+2; the case is the 3rd probe (i+2)
        case_probe_id = pid_list[i + 2]
        if i + 3 < n and ans[i + 3] != "" and not eq(ans[i + 3], window[0]):
            switch.append(case_probe_id)
        elif i + 3 >= n:
            holds.append(case_probe_id)
        else:
            # continues but through empties/agreement further out; check if it
            # ever holds cleanly to the end without disagreement
            rest = ans[i + 2 :]
            nonempty_rest = [a for a in rest if a != ""]
            if all(eq(a, window[0]) for a in nonempty_rest):
                holds.append(case_probe_id)
    return switch, holds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage1_logging"))
    ap.add_argument("--output-dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--model", default="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
    ap.add_argument("--per-group", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)

    print("Loading probes.csv + traj/*.json ...")
    df, trajs = load(args.input)

    groups = {
        "probe_eq_final": [],
        "probe_neq_final": [],
        "single_letter": [],
        "empty": [],
        "consistent3_then_switch": [],
        "consistent3_then_holds": [],
    }

    for pid, df_p in df.groupby("problem_id"):
        for _, row in df_p.iterrows():
            ans = row["probe_answer"]
            key = (pid, row["probe_id"])
            if ans == "":
                groups["empty"].append(key)
                continue
            if SINGLE_LETTER_RE.match(ans):
                groups["single_letter"].append(key)
            if eq(ans, row["final_answer"]):
                groups["probe_eq_final"].append(key)
            else:
                groups["probe_neq_final"].append(key)
        switch, holds = find_switch_and_hold_cases(df_p)
        groups["consistent3_then_switch"].extend((pid, p) for p in switch)
        groups["consistent3_then_holds"].extend((pid, p) for p in holds)

    print("Group sizes (before sampling):")
    for g, items in groups.items():
        print(f"  {g}: {len(items)}")

    case_groups = {}
    for g, items in groups.items():
        random.shuffle(items)
        for key in items[: args.per_group]:
            case_groups.setdefault(key, []).append(g)

    print(f"\nUnique sampled cases: {len(case_groups)}")

    print(f"Loading tokenizer {args.model} ...")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model)

    tok_cache = {}
    cases = []
    for (pid, probe_id), group_names in sorted(case_groups.items()):
        traj = trajs[pid]
        df_p = df[df["problem_id"] == pid]
        case = build_case(pid, probe_id, group_names, df_p, traj, tokenizer, tok_cache)
        cases.append(case)

    out_jsonl = os.path.join(args.output_dir, "probe_audit_cases.jsonl")
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Wrote {len(cases)} cases to {out_jsonl}")

    build_html(cases, os.path.join(args.output_dir, "annotate.html"))
    print(f"Wrote {os.path.join(args.output_dir, 'annotate.html')}")


def build_html(cases, out_path):
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "annotate_template.html")
    with open(template_path, encoding="utf-8") as f:
        template = f.read()
    data_json = json.dumps(cases, ensure_ascii=False)
    html = template.replace("/*__CASES_JSON__*/", data_json)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
