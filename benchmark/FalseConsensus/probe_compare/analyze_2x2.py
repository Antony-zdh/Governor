"""Analyze the paired simple/certaindex re-probe experiment.

This is the offline follow-up for plan.md §6.6:

1. Reproduce the headline timing × readout 2×2.
2. Repeat the 2×2 on the intersection of problems where both timing rules
   trigger, so the timing comparison is paired on the same problems.
3. Analyze trigger-set differences and compare each stopped answer with the
   answer reached by continuing the logged trajectory to its end.

No model calls are made.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pandas as pd


FC_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = FC_DIR.parents[1]
sys.path.insert(0, str(REPO_DIR))

from dynasor.core.evaluator import math_equal, strip_string  # noqa: E402


VARIANTS = ("simple__10", "certaindex__10")
STYLE = {"simple__10": "simple", "certaindex__10": "certaindex"}


@lru_cache(maxsize=None)
def eq(a: str, b: str) -> bool:
    """Cached mathematical-answer equivalence."""
    a, b = str(a), str(b)
    if a == b:
        return True
    try:
        return bool(math_equal(a, b))
    except Exception:
        return False


def normalized(answer: object) -> str:
    answer = str(answer)
    try:
        return strip_string(answer)
    except Exception:
        return answer.strip()


def answer_equal(a: object, b: object) -> bool:
    return eq(normalized(a), normalized(b)) or eq(str(a), str(b))


def unwrap_text(answer: object) -> str:
    match = re.fullmatch(r"\s*\\text\{(.*)\}\s*", str(answer), flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def correct(answer: object, target: object) -> bool:
    """Mirror the answer checks used by the Stage-7 replay."""
    answer, target = str(answer), str(target)
    if answer_equal(answer, target):
        return True
    deprefixed = re.sub(r"^\s*[a-zA-Z]\s*\\in\s*", "", target)
    if deprefixed != target and answer_equal(answer, deprefixed):
        return True
    target_text = unwrap_text(target)
    return target_text != "" and answer.strip().lower() == target_text.lower()


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def find_first_stop(stream: pd.DataFrame, patience: int) -> dict | None:
    """Return the first Dynasor-style unanimous, certain, nonempty stop."""
    stream = stream.reset_index(drop=True).sort_values("probe_id").reset_index(drop=True)
    for end in range(patience - 1, len(stream)):
        window = stream.iloc[end - patience + 1 : end + 1]
        answers = window["probe_answer"].astype(str).tolist()
        if any(answer == "" for answer in answers):
            continue
        if not all(as_bool(x) for x in window["is_certain"]):
            continue
        if not all(answer_equal(answers[0], answer) for answer in answers[1:]):
            continue
        row = stream.iloc[end]
        return {
            "probe_id": int(row["probe_id"]),
            "token_position": int(row["token_position"]),
            "stop_answer": answers[0],
        }
    return None


def load_streams(path: Path) -> dict[str, dict[int, pd.DataFrame]]:
    df = pd.read_csv(path, keep_default_na=False)
    missing = set(VARIANTS) - set(df["variant"].unique())
    if missing:
        raise ValueError(f"Missing variants: {sorted(missing)}")
    streams: dict[str, dict[int, pd.DataFrame]] = {}
    for variant in VARIANTS:
        streams[variant] = {
            int(pid): group.sort_values("probe_id").set_index("probe_id", drop=False)
            for pid, group in df[df["variant"] == variant].groupby("problem_id")
        }
    return streams


def load_trajectories(traj_dir: Path, problem_ids: set[int]) -> dict[int, dict]:
    trajectories = {}
    for pid in sorted(problem_ids):
        path = traj_dir / f"problem_{pid}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        trajectories[pid] = json.loads(path.read_text())
    return trajectories


def readout_at(
    streams: dict[str, dict[int, pd.DataFrame]],
    readout_variant: str,
    pid: int,
    probe_id: int,
) -> dict:
    row = streams[readout_variant][pid].loc[probe_id]
    if isinstance(row, pd.DataFrame):
        raise ValueError(f"Duplicate probe_id={probe_id} for problem={pid}")
    answer = str(row["probe_answer"])
    certain = as_bool(row["is_certain"])
    return {
        "answer": answer,
        "certain": certain,
        "committed": answer != "" and certain,
    }


def cell_metrics(
    timing_variant: str,
    readout_variant: str,
    problem_ids: set[int],
    stops: dict[str, dict[int, dict | None]],
    streams: dict[str, dict[int, pd.DataFrame]],
    trajectories: dict[int, dict],
) -> dict:
    rows = []
    for pid in sorted(problem_ids):
        stop = stops[timing_variant][pid]
        if stop is None:
            raise ValueError(f"Timing rule {timing_variant} did not stop on {pid}")
        readout = readout_at(streams, readout_variant, pid, stop["probe_id"])
        trajectory = trajectories[pid]
        rows.append(
            {
                "correct": correct(readout["answer"], trajectory["target"]),
                "continuation_match": answer_equal(
                    readout["answer"], trajectory["final_answer"]
                ),
                "committed": readout["committed"],
                "token_position": stop["token_position"],
            }
        )
    frame = pd.DataFrame(rows)
    committed = frame[frame["committed"]]
    return {
        "timing": STYLE[timing_variant],
        "readout": STYLE[readout_variant],
        "n": int(len(frame)),
        "accuracy": float(frame["correct"].mean()),
        "commit_rate": float(frame["committed"].mean()),
        "continuation_match": float(frame["continuation_match"].mean()),
        "conditional_accuracy": (
            float(committed["correct"].mean()) if len(committed) else None
        ),
        "conditional_continuation_match": (
            float(committed["continuation_match"].mean()) if len(committed) else None
        ),
        "mean_stop_tokens": float(frame["token_position"].mean()),
        "median_stop_tokens": float(frame["token_position"].median()),
    }


def factorial_summary(cells: dict[str, dict]) -> dict:
    ss = cells["simple_timing__simple_readout"]["accuracy"]
    sc = cells["simple_timing__certaindex_readout"]["accuracy"]
    cs = cells["certaindex_timing__simple_readout"]["accuracy"]
    cc = cells["certaindex_timing__certaindex_readout"]["accuracy"]
    readout_effect = ((sc - ss) + (cc - cs)) / 2
    timing_effect = ((cs - ss) + (cc - sc)) / 2
    denominator = abs(readout_effect) + abs(timing_effect)
    return {
        "readout_effect": readout_effect,
        "timing_effect": timing_effect,
        "interaction": (cc - cs) - (sc - ss),
        "timing_share_of_abs_main_effects": (
            abs(timing_effect) / denominator if denominator else None
        ),
    }


def make_cells(
    simple_ids: set[int],
    certaindex_ids: set[int],
    stops: dict[str, dict[int, dict | None]],
    streams: dict[str, dict[int, pd.DataFrame]],
    trajectories: dict[int, dict],
) -> dict[str, dict]:
    specifications = {
        "simple_timing__simple_readout": (
            "simple__10",
            "simple__10",
            simple_ids,
        ),
        "simple_timing__certaindex_readout": (
            "simple__10",
            "certaindex__10",
            simple_ids,
        ),
        "certaindex_timing__simple_readout": (
            "certaindex__10",
            "simple__10",
            certaindex_ids,
        ),
        "certaindex_timing__certaindex_readout": (
            "certaindex__10",
            "certaindex__10",
            certaindex_ids,
        ),
    }
    return {
        name: cell_metrics(timing, readout, pids, stops, streams, trajectories)
        for name, (timing, readout, pids) in specifications.items()
    }


def classify_simple_only(
    simple_only: set[int],
    stops: dict[str, dict[int, dict | None]],
    trajectories: dict[int, dict],
) -> pd.DataFrame:
    rows = []
    for pid in sorted(simple_only):
        stop = stops["simple__10"][pid]
        assert stop is not None
        trajectory = trajectories[pid]
        stop_correct = correct(stop["stop_answer"], trajectory["target"])
        final_correct = bool(trajectory["final_correct"])
        continuation_match = answer_equal(
            stop["stop_answer"], trajectory["final_answer"]
        )
        if continuation_match and stop_correct:
            category = "terminal_correct"
        elif continuation_match and not stop_correct:
            category = "terminal_wrong"
        elif not stop_correct and final_correct:
            category = "recovery"
        elif stop_correct and not final_correct:
            category = "overthinking"
        else:
            category = "changed_wrong_to_wrong"
        rows.append(
            {
                "problem_id": pid,
                "simple_stop_probe_id": stop["probe_id"],
                "simple_stop_tokens": stop["token_position"],
                "simple_stop_answer": stop["stop_answer"],
                "final_answer": trajectory["final_answer"],
                "target": trajectory["target"],
                "stop_correct": stop_correct,
                "final_correct": final_correct,
                "continuation_match": continuation_match,
                "category": category,
            }
        )
    return pd.DataFrame(rows)


def format_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def cell_table(cells: dict[str, dict]) -> list[str]:
    order = [
        "simple_timing__simple_readout",
        "simple_timing__certaindex_readout",
        "certaindex_timing__simple_readout",
        "certaindex_timing__certaindex_readout",
    ]
    lines = [
        "| Timing | Readout | N | Accuracy | Commit rate | Continuation match | Mean stop tokens |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for name in order:
        cell = cells[name]
        lines.append(
            f"| {cell['timing']} | {cell['readout']} | {cell['n']} | "
            f"{format_pct(cell['accuracy'])} | {format_pct(cell['commit_rate'])} | "
            f"{format_pct(cell['continuation_match'])} | "
            f"{cell['mean_stop_tokens']:.0f} |"
        )
    return lines


def write_report(path: Path, result: dict, simple_only: pd.DataFrame) -> None:
    headline = result["headline"]
    paired = result["common_trigger_paired"]
    overlap = result["trigger_overlap"]
    categories = Counter(simple_only["category"])
    n_simple_only = len(simple_only)
    changed = int((~simple_only["continuation_match"]).sum())
    stop_correct = int(simple_only["stop_correct"].sum())
    final_correct = int(simple_only["final_correct"].sum())

    lines = [
        "# Paired re-probe 2×2 follow-up",
        "",
        "This is an offline analysis of the paired `simple@10` and "
        "`certaindex@10` streams. No model calls were made.",
        "",
        "## Headline 2×2",
        "",
        *cell_table(headline["cells"]),
        "",
        f"- descriptive readout main effect: "
        f"**{headline['effects']['readout_effect'] * 100:+.2f} pp**",
        f"- descriptive timing main effect: "
        f"**{headline['effects']['timing_effect'] * 100:+.2f} pp**",
        f"- timing share of absolute main effects: "
        f"**{format_pct(headline['effects']['timing_share_of_abs_main_effects'])}**",
        "",
        "The headline timing rows have different problem sets (416 vs 311), so "
        "their contrast includes both later timing and trigger-set selection. "
        "It is not by itself a fully paired timing estimate.",
        "",
        "## Common-trigger paired sensitivity",
        "",
        f"Both timing rules trigger on **{overlap['both']}** problems. Restricting "
        "all four cells to those same problems gives:",
        "",
        *cell_table(paired["cells"]),
        "",
        f"- paired readout main effect: "
        f"**{paired['effects']['readout_effect'] * 100:+.2f} pp**",
        f"- paired timing main effect: "
        f"**{paired['effects']['timing_effect'] * 100:+.2f} pp**",
        f"- timing share of absolute paired main effects: "
        f"**{format_pct(paired['effects']['timing_share_of_abs_main_effects'])}**",
        "",
        "The paired result preserves the main qualitative conclusion: readout "
        "wording contributes little, while waiting for the certaindex timing "
        "point is associated with substantially higher correctness.",
        "",
        "## Trigger-set overlap",
        "",
        f"- simple triggers: **{overlap['simple']}**",
        f"- certaindex triggers: **{overlap['certaindex']}**",
        f"- both trigger: **{overlap['both']}**",
        f"- simple-only: **{overlap['simple_only']}**",
        f"- certaindex-only: **{overlap['certaindex_only']}**",
        f"- net trigger-count difference: **{overlap['net_difference']}**",
        "",
        "Therefore, the often quoted `416 - 311 = 105` is a net count "
        "difference, not the size of the simple-only set. The refusal analysis "
        f"contains **{n_simple_only}** problems.",
        "",
        "## Simple-only continuation analysis",
        "",
        f"- simple stop differs from the trajectory's final answer: "
        f"**{changed}/{n_simple_only} ({changed / n_simple_only:.1%})**",
        f"- simple stopped answer is reference-correct: "
        f"**{stop_correct}/{n_simple_only} ({stop_correct / n_simple_only:.1%})**",
        f"- full trajectory ends reference-correct: "
        f"**{final_correct}/{n_simple_only} ({final_correct / n_simple_only:.1%})**",
        "",
        "| Category | N | Share | Interpretation |",
        "|---|---:|---:|---|",
        f"| recovery | {categories['recovery']} | "
        f"{categories['recovery'] / n_simple_only:.1%} | refusal protects a wrong→correct recovery |",
        f"| overthinking | {categories['overthinking']} | "
        f"{categories['overthinking'] / n_simple_only:.1%} | refusal loses a correct early stop before correct→wrong |",
        f"| terminal_correct | {categories['terminal_correct']} | "
        f"{categories['terminal_correct'] / n_simple_only:.1%} | refusal delays an already correct terminal answer |",
        f"| terminal_wrong | {categories['terminal_wrong']} | "
        f"{categories['terminal_wrong'] / n_simple_only:.1%} | refusal delays but does not repair the wrong answer |",
        f"| changed_wrong_to_wrong | {categories['changed_wrong_to_wrong']} | "
        f"{categories['changed_wrong_to_wrong'] / n_simple_only:.1%} | answer changes, but both stop and final are wrong |",
        "",
        "Using final-answer mismatch as the operational definition, a majority "
        "of simple-only stops are non-terminal. But rejection is not uniformly "
        "beneficial: its direct accuracy benefit is the recovery group, while "
        "the overthinking group is harmed and the remaining groups only incur "
        "delay. This supports history/timing signals, but still requires the "
        "Pareto sweep to test whether a flat `min_tokens` floor reproduces the "
        "same gains more efficiently.",
        "",
        "Per-problem details are in `simple_only_cases.csv`; machine-readable "
        "summary statistics are in `analysis_2x2.json`.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paired-csv",
        type=Path,
        default=FC_DIR / "results/probe_paired_2x2/reprobe_paired.csv",
    )
    parser.add_argument(
        "--stage1-traj-dir",
        type=Path,
        default=FC_DIR / "results/stage1_logging/traj",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=FC_DIR / "results/probe_paired_2x2",
    )
    parser.add_argument("--patience", type=int, default=3)
    args = parser.parse_args()

    streams = load_streams(args.paired_csv)
    all_problem_ids = set(streams["simple__10"]) | set(streams["certaindex__10"])
    trajectories = load_trajectories(args.stage1_traj_dir, all_problem_ids)
    stops = {
        variant: {
            pid: find_first_stop(stream, args.patience)
            for pid, stream in streams[variant].items()
        }
        for variant in VARIANTS
    }

    simple_ids = {pid for pid, stop in stops["simple__10"].items() if stop}
    certaindex_ids = {
        pid for pid, stop in stops["certaindex__10"].items() if stop
    }
    common_ids = simple_ids & certaindex_ids
    simple_only_ids = simple_ids - certaindex_ids
    certaindex_only_ids = certaindex_ids - simple_ids

    headline_cells = make_cells(
        simple_ids, certaindex_ids, stops, streams, trajectories
    )
    paired_cells = make_cells(
        common_ids, common_ids, stops, streams, trajectories
    )
    simple_only = classify_simple_only(simple_only_ids, stops, trajectories)

    category_counts = {
        key: int(value) for key, value in Counter(simple_only["category"]).items()
    }
    result = {
        "patience": args.patience,
        "headline": {
            "cells": headline_cells,
            "effects": factorial_summary(headline_cells),
        },
        "common_trigger_paired": {
            "cells": paired_cells,
            "effects": factorial_summary(paired_cells),
        },
        "trigger_overlap": {
            "simple": len(simple_ids),
            "certaindex": len(certaindex_ids),
            "both": len(common_ids),
            "simple_only": len(simple_only_ids),
            "certaindex_only": len(certaindex_only_ids),
            "net_difference": len(simple_ids) - len(certaindex_ids),
        },
        "simple_only": {
            "n": len(simple_only),
            "continuation_mismatch": int(
                (~simple_only["continuation_match"]).sum()
            ),
            "stop_correct": int(simple_only["stop_correct"].sum()),
            "final_correct": int(simple_only["final_correct"].sum()),
            "category_counts": category_counts,
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    simple_only.to_csv(args.out_dir / "simple_only_cases.csv", index=False)
    (args.out_dir / "analysis_2x2.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    write_report(args.out_dir / "report.md", result, simple_only)

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
