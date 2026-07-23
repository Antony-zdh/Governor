"""Stage 7 x Stage 8 cross-check: does an improved probe design change the
outcome of Stage 7's two selected operating-point rules?

Stage 7 (results/stage7_pareto/report.md) picked two usable operating points
from its 142-config sweep, both from the `consecutive` family, using the
existing P0 probe signal:

  Conservative: consec_p8_mt1024_cert1 (patience=8, min_tokens=1024,
                require_certain=True, validity_mode=nonempty_only)
  Balanced:     consec_p6_mt1024_cert0 (patience=6, min_tokens=1024,
                require_certain=False, validity_mode=nonempty_only)

(Aggressive wasn't usable -- 25% accuracy -- so it's not re-tested here.)

This script re-runs those exact same two rules, unchanged, but swaps the
probe-answer/certainty signal feeding them: P0 (original 10-token boxed
probe) vs the Stage 8 probe_variants.csv designs (P1_32/P1_64/P2/P3/P4),
all evaluated on the same 100-problem Stage 8 subset (checkpoints are
identical across designs by construction -- Stage 8 reissued probes at
P0's existing checkpoint positions, so `tok` arrays line up 1:1).

P0's numbers here will NOT match Stage 7's report.md (that was n=500;
this is the 100-problem subset only) -- P0-on-subset is recomputed as the
fair baseline for this comparison, not reused from the n=500 report.

`is_certain` for P1-P4 is computed the same way logging_run.py computes it
for P0 (absence of UNCERTAIN_WORDS in the raw probe/response text) rather
than substituted with `parse_ok`, since `is_certain` and `parse_ok` measure
different things (hedging language vs. format-following) and conflating them
would bias the require_certain=True (Conservative) condition.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from analyze import load  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "replay"))
from sweep_stop_rules import (  # noqa: E402
    aggregate,
    make_correct_of,
    precompute_problems,
    run_config,
)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "TokenDeprivation"))
from utils import load_dataset  # noqa: E402

UNCERTAIN_WORDS = ["wait", "hold", "but", "okay", "no", "hmm"]

PROBE_OUTPUT_TOKENS = {"P0": 10, "P1_32": 32, "P1_64": 64, "P2": 40, "P3": 50, "P4": 40}

CONFIGS = [
    {
        "config_id": "consec_p8_mt1024_cert1",
        "family": "consecutive",
        "label": "Conservative: 8-consecutive, min_tok=1024, certain=True",
        "patience": 8,
        "min_tokens": 1024,
        "require_certain": True,
        "validity_mode": "nonempty_only",
    },
    {
        "config_id": "consec_p6_mt1024_cert0",
        "family": "consecutive",
        "label": "Balanced: 6-consecutive, min_tok=1024, certain=False",
        "patience": 6,
        "min_tokens": 1024,
        "require_certain": False,
        "validity_mode": "nonempty_only",
    },
]


def build_variant_problems(variant_df, design, p0_problems_by_pid, raw_targets):
    """Build the same per-problem dict shape precompute_problems() produces,
    but with ans/cert coming from a Stage 8 probe_variants.csv design instead
    of P0. tok/final_correct/etc are reused from the P0 problem (checkpoints
    and ground truth are identical across designs)."""
    sub = variant_df[variant_df["design"] == design]
    problems = []
    for pid, g in sub.groupby("problem_id"):
        if pid not in p0_problems_by_pid:
            continue
        g = g.sort_values("probe_id")
        p0 = p0_problems_by_pid[pid]
        ans = [str(a) if pd.notna(a) else "" for a in g["answer"]]
        cert = [not any(w in str(r).lower() for w in UNCERTAIN_WORDS) for r in g["raw_output"]]
        tok = list(g["token_position"])
        if len(tok) != len(p0["tok"]):
            # shouldn't happen (same checkpoints by construction) but guard anyway
            continue
        problems.append(
            {
                "pid": pid,
                "tok": tok,
                "ans": ans,
                "cert": cert,
                "entropy": p0["entropy"],
                "dominant_cum": p0["dominant_cum"],
                "correct_of": p0["correct_of"],
                "tokens_used_full": p0["tokens_used_full"],
                "num_probes": len(g),
                "final_correct": p0["final_correct"],
                "final_answer": p0["final_answer"],
                "probe1_correct": bool(p0["correct_of"](ans[0])) if ans else False,
            }
        )
    return problems


def aggregate_with_probe_cost(cfg, results, problems_by_pid, probe_output_tokens):
    row = aggregate(cfg, results, problems_by_pid)
    row["avg_probe_output_tokens"] = row["avg_probe_calls"] * probe_output_tokens
    row["avg_total_generated_tokens"] = row["avg_main_tokens"] + row["avg_probe_calls"] * probe_output_tokens
    return row


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    stage1_dir = os.path.join(here, "..", "results", "stage1_logging")
    variants_path = os.path.join(here, "..", "results", "stage8_probe_compare", "probe_variants.csv")
    subset_path = os.path.join(here, "subset.json")
    out_dir = os.path.join(here, "..", "results", "stage8_probe_compare")

    import json

    with open(subset_path, encoding="utf-8") as f:
        subset_pids = {item["problem_id"] for item in json.load(f)}

    print("Loading P0 (Stage 1) data ...")
    df, trajs = load(stage1_dir)
    raw_targets = {i: item["answer"] for i, item in enumerate(load_dataset("math500"))}
    df_subset = df[df["problem_id"].isin(subset_pids)]

    p0_problems = precompute_problems(df_subset, trajs, raw_targets)
    p0_problems_by_pid = {p["pid"]: p for p in p0_problems}
    print(f"P0 subset problems: {len(p0_problems)}")

    print("Loading Stage 8 probe_variants.csv ...")
    variants_df = pd.read_csv(variants_path, keep_default_na=False)

    all_rows = []
    designs = ["P0", "P1_32", "P1_64", "P2", "P3", "P4"]
    for design in designs:
        if design == "P0":
            problems = p0_problems
        else:
            problems = build_variant_problems(variants_df, design, p0_problems_by_pid, raw_targets)
        problems_by_pid = {p["pid"]: p for p in problems}
        for cfg in CONFIGS:
            results = run_config(cfg, problems)
            row = aggregate_with_probe_cost(cfg, results, problems_by_pid, PROBE_OUTPUT_TOKENS[design])
            row["design"] = design
            row["n_problems_used"] = len(problems)
            all_rows.append(row)

    results_df = pd.DataFrame(all_rows)
    cols = ["design", "config_id", "n_problems_used", "overall_accuracy", "stop_coverage",
            "correct_stop_rate", "false_stop_rate", "avg_main_tokens", "avg_probe_output_tokens",
            "avg_total_generated_tokens", "correct_to_wrong_truncation",
            "wrong_to_correct_recovery_truncated"]
    results_df = results_df[cols]
    out_csv = os.path.join(out_dir, "stage7_rules_x_stage8_probes.csv")
    results_df.to_csv(out_csv, index=False)

    lines = []
    lines.append("# Stage 7 winning rules re-tested with Stage 8 probe designs\n")
    lines.append(
        "Same two rule configs Stage 7 selected as usable operating points "
        "(Conservative/Balanced, `consecutive` family), unchanged -- only the "
        "probe-answer/certainty signal feeding them is swapped, on the same "
        "100-problem Stage 8 subset. P0-on-subset is recomputed here as the "
        "fair baseline (Stage 7's report.md numbers were n=500, not directly "
        "comparable).\n"
    )
    for cfg in CONFIGS:
        sub = results_df[results_df["config_id"] == cfg["config_id"]].set_index("design")
        lines.append(f"## {cfg['label']} (`{cfg['config_id']}`)\n")
        lines.append(sub.to_string())
        lines.append("")
        p0_acc = sub.loc["P0", "overall_accuracy"]
        p0_tok = sub.loc["P0", "avg_total_generated_tokens"]
        p0_cov = sub.loc["P0", "stop_coverage"]
        for d in ["P1_32", "P1_64", "P2", "P3", "P4"]:
            if d not in sub.index:
                continue
            r = sub.loc[d]
            lines.append(
                f"- **{d}** vs P0: accuracy {r['overall_accuracy']:.1%} "
                f"({r['overall_accuracy'] - p0_acc:+.1%}), coverage {r['stop_coverage']:.1%} "
                f"({r['stop_coverage'] - p0_cov:+.1%}), total tokens {r['avg_total_generated_tokens']:.0f} "
                f"({r['avg_total_generated_tokens'] - p0_tok:+.0f})"
            )
        lines.append("")

    report = "\n".join(lines)
    out_md = os.path.join(out_dir, "stage7_rules_x_stage8_probes_report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\nWrote {out_csv} and {out_md}")


if __name__ == "__main__":
    main()
