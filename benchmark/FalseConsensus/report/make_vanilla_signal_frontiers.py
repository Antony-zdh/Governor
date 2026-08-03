#!/usr/bin/env python3
"""Vanilla single-signal early-exit frontiers (no Governor Pareto sweep).

Three deployable confidence signals, each swept over its own single natural
hyperparameter, plus a non-deployable oracle, plotted on the shared
accuracy-drop / token-saving plane over *all* Governor v2 development
trajectories (train + dev + test, seeds 42-47, both development models, 3,420
trajectories).

Data sources -- everything but DEER is read straight from committed, already
graded per-problem replay banks:

  * TJE        -- verbal confidence, top-1..top-6.  Committed replay rows:
                  ``tje_threshold_readout_bank_top1_6/aggregate/replay_rows.jsonl.gz``.
  * CertaIndex -- last-W simple@32 probe consensus with tau = 1 (window size
                  W = patience at interval 64).  Committed replay rows:
                  ``certaindex_effort_bank/aggregate/replay_rows.jsonl.gz``
                  (patience 2/3/5/8).
  * Oracle     -- first valid probe matching the reference, else full fallback.
                  Committed decision: ``simple32_oracle/per_problem.csv``,
                  re-anchored to the strict ``final_correct`` baseline.
  * DEER       -- trial-submit confidence, swept over tau.  Only its aggregate
                  frontier was committed, so its per-problem records are
                  re-derived here from the cap-30 confidence bank (fast: DEER
                  answers are numeric, so grading uses an exact/numeric path).

Token metric: all-generated tokens = main decode through the stop plus every
probe OUTPUT token; baseline = the full main decode.  Baseline correctness is
the strict ``final_correct`` for every series.

Five views, each its own figure: pooled / macro (mean over the three
benchmarks) / math500 / amc23 / aime24.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.related_work import common, model_map  # noqa: E402
from benchmark.FalseConsensus.report import (  # noqa: E402
    analyze_deer_confidence_frontier as deer_mod,
)

RELATED = REPO / "benchmark/FalseConsensus/results/related_work"
GOVERNOR = REPO / "benchmark/FalseConsensus/results/governor_v2"
FIGURES = REPO / "benchmark/FalseConsensus/report/figures/vanilla_signal"
RESULTS = RELATED / "vanilla_signal_frontiers"
TJE_ROWS = RELATED / "tje_threshold_readout_bank_top1_6/aggregate/replay_rows.jsonl.gz"
CERTAINDEX_ROWS = RELATED / "certaindex_effort_bank/aggregate/replay_rows.jsonl.gz"
ORACLE_CSV = GOVERNOR / "simple32_oracle/per_problem.csv"
DEER_BANK = RELATED / "deer_confidence_bank_cap30"
SCOPE_PREFIX = {"full": "development", "test": "confirmation"}

DEER_CAP = 30
DEER_THRESHOLDS = deer_mod.THRESHOLDS
BENCHMARKS = model_map.BENCHMARKS  # ("math500", "amc23", "aime24")
EXPECTED_TRAJECTORIES = 3420


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _record(
    benchmark: str,
    model_key: str,
    split: str,
    delivered_correct: bool,
    baseline_correct: bool,
    method_tokens: int,
    baseline_tokens: int,
) -> dict[str, Any]:
    return {
        "benchmark": benchmark,
        "model_key": model_key,
        "split": split,
        "dc": int(bool(delivered_correct)),
        "bc": int(bool(baseline_correct)),
        "mt": int(method_tokens),
        "bt": int(baseline_tokens),
    }


def _iter_jsonl_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


# --------------------------------------------------------------------------- #
# TJE + CertaIndex + oracle: committed, already-graded data
# --------------------------------------------------------------------------- #
def committed_line(
    path: Path, param_key: str
) -> tuple[dict[Any, list[dict[str, Any]]], int]:
    sweep: dict[Any, list[dict[str, Any]]] = {}
    total = 0
    for row in _iter_jsonl_gz(path):
        correct = row.get("correct")
        delivered = row["baseline_correct"] if correct is None else correct
        sweep.setdefault(row[param_key], []).append(
            _record(
                row["benchmark"],
                row["model_key"],
                row["split"],
                bool(delivered),
                bool(row["baseline_correct"]),
                int(row["all_generated_tokens"]),
                int(row["baseline_all_generated_tokens"]),
            )
        )
        total += 1
    return sweep, total


def final_correct_map() -> dict[tuple[str, str, int, int], int]:
    """Per-problem strict baseline, taken from the TJE bank (top-1 rows)."""
    table: dict[tuple[str, str, int, int], int] = {}
    for row in _iter_jsonl_gz(TJE_ROWS):
        if int(row["top_k"]) != 1:
            continue
        key = (
            str(row["model"]),
            str(row["benchmark"]),
            int(row["seed"]),
            int(row["problem_id"]),
        )
        table[key] = int(row["baseline_correct"])
    if len(table) != EXPECTED_TRAJECTORIES:
        raise ValueError(f"final_correct map: {len(table)}")
    return table


def oracle_records() -> list[dict[str, Any]]:
    baseline = final_correct_map()
    records: list[dict[str, Any]] = []
    reverse_model = {
        model_map.model_info(key)["model_id"]: key
        for key in ("deepseek", "qwen3")
    }
    with ORACLE_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (
                row["model"],
                row["benchmark"],
                int(row["seed"]),
                int(row["problem_id"]),
            )
            bc = baseline[key]
            found = bool(int(row["oracle_found_correct_probe"]))
            records.append(
                _record(
                    row["benchmark"],
                    reverse_model[row["model"]],
                    row["split"],
                    bool(1 if found else bc),
                    bool(bc),
                    int(row["oracle_tokens"]),
                    int(row["full_main_tokens"]),
                )
            )
    if len(records) != EXPECTED_TRAJECTORIES:
        raise ValueError(f"oracle rows: {len(records)}")
    return records


# --------------------------------------------------------------------------- #
# DEER: re-derive per-problem records from the committed confidence bank
# --------------------------------------------------------------------------- #
def _maybe_float(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError, AttributeError):
        return None


@lru_cache(maxsize=400_000)
def grade_equal(answer: str, target: str) -> bool:
    if not answer:
        return False
    if answer == target:
        return True
    a, b = _maybe_float(answer), _maybe_float(target)
    if a is not None and b is not None:
        return abs(a - b) <= 1e-9
    try:
        return bool(common.real_answers_equal(answer, target))
    except BaseException:
        return False


def _deer_worker(
    task: tuple[str, str, dict[tuple[str, str, int, int], str]],
) -> list[dict[str, Any]]:
    scope, archive_text, dev_splits = task
    archive = Path(archive_text)
    model_key, benchmark, seed_text = archive.parent.name.split("__")
    seed = int(seed_text.removeprefix("seed_"))
    slug = model_map.model_info(model_key)["slug"]
    traj_dir = (
        GOVERNOR
        / f"{SCOPE_PREFIX[scope]}__{slug}__{benchmark}__seed_{seed}"
        / "main/traj"
    )
    records: list[dict[str, Any]] = []
    for payload in _iter_jsonl_gz(archive):
        problem_id = int(payload["problem_id"])
        trajectory = json.loads(
            (traj_dir / f"problem_{problem_id}.json").read_text("utf-8")
        )
        target = _normalized(trajectory["target"])
        baseline_correct = bool(trajectory["final_correct"])
        baseline_tokens = int(payload["main_token_count_recorded"])
        split = (
            "test"
            if scope == "test"
            else dev_splits[
                (
                    str(payload["model"]),
                    str(payload["dataset"]),
                    int(payload["base_seed"]),
                    problem_id,
                )
            ]
        )
        steps = [
            (
                _normalized(t.get("trial_answer")),
                float(t["confidence"]),
                int(t.get("trial_out_tokens", 0)),
                int(t["token_position"]),
            )
            for t in sorted(
                payload["trials"], key=lambda r: int(r["candidate_id"])
            )[:DEER_CAP]
        ]
        for threshold in DEER_THRESHOLDS:
            probe_tokens = 0
            accepted = None
            for answer, confidence, out_tokens, position in steps:
                probe_tokens += out_tokens
                if answer and confidence > threshold:
                    accepted = (answer, position)
                    break
            if accepted is None:
                dc = baseline_correct
                tokens = baseline_tokens + probe_tokens
            else:
                dc = grade_equal(accepted[0], target)
                tokens = accepted[1] + probe_tokens
            records.append(
                {
                    "threshold": float(threshold),
                    **_record(
                        benchmark, model_key, split, dc,
                        baseline_correct, tokens, baseline_tokens,
                    ),
                }
            )
    return records


def deer_records() -> dict[float, list[dict[str, Any]]]:
    dev_splits = deer_mod.load_development_splits()
    tasks = [
        (scope, str(archive), dev_splits)
        for scope in ("full", "test")
        for archive in sorted((DEER_BANK / scope).glob("*/trials.jsonl.gz"))
    ]
    sweep: dict[float, list[dict[str, Any]]] = {
        float(t): [] for t in DEER_THRESHOLDS
    }
    total = 0
    with ProcessPoolExecutor(
        max_workers=8, mp_context=get_context("spawn")
    ) as executor:
        for future in as_completed(
            executor.submit(_deer_worker, task) for task in tasks
        ):
            for row in future.result():
                sweep[row["threshold"]].append(row)
                total += 1
    if total != EXPECTED_TRAJECTORIES * len(DEER_THRESHOLDS):
        raise ValueError(f"DEER record count: {total}")
    return sweep


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _pooled(records: list[dict[str, Any]]) -> dict[str, float] | None:
    if not records:
        return None
    n = len(records)
    bc = sum(r["bc"] for r in records)
    dc = sum(r["dc"] for r in records)
    bt = sum(r["bt"] for r in records)
    mt = sum(r["mt"] for r in records)
    return {
        "n": n,
        "accuracy_drop_pp": 100.0 * (bc - dc) / n,
        "token_saving_pct": 100.0 * (bt - mt) / bt if bt else 0.0,
        "baseline_accuracy_pct": 100.0 * bc / n,
        "accuracy_pct": 100.0 * dc / n,
    }


def aggregate(records: list[dict[str, Any]], view: str) -> dict[str, float] | None:
    if view == "pooled":
        return _pooled(records)
    if view in BENCHMARKS:
        return _pooled([r for r in records if r["benchmark"] == view])
    if view == "macro":
        cells = [
            _pooled([r for r in records if r["benchmark"] == b])
            for b in BENCHMARKS
        ]
        cells = [c for c in cells if c is not None]
        if not cells:
            return None
        keys = (
            "accuracy_drop_pp",
            "token_saving_pct",
            "baseline_accuracy_pct",
            "accuracy_pct",
        )
        out: dict[str, float] = {"n": sum(c["n"] for c in cells)}
        for key in keys:
            out[key] = sum(c[key] for c in cells) / len(cells)
        return out
    raise ValueError(f"unknown view: {view}")


def build_line(
    sweep: dict[Any, list[dict[str, Any]]], view: str
) -> list[dict[str, Any]]:
    points = []
    for param in sorted(sweep):
        summary = aggregate(sweep[param], view)
        if summary is not None:
            points.append({"param": param, **summary})
    return points


# --------------------------------------------------------------------------- #
# Plotting
# --------------------------------------------------------------------------- #
VIEW_TITLES = {
    "pooled": "Pooled (all trajectories)",
    "macro": "Macro (mean over the three benchmarks)",
    "math500": "MATH500",
    "amc23": "AMC23",
    "aime24": "AIME24",
}
METHOD_STYLE = {
    "DEER": ("#2563eb", "o", "DEER (trial-submit, sweep $\\tau$)"),
    "TJE": ("#ea580c", "*", "TJE (verbal confidence, top-1..6)"),
    "CertaIndex": ("#7c3aed", "s", "CertaIndex ($\\tau{=}1$, sweep window $W$)"),
}


def plot_view(axis, view, lines, oracle_point) -> None:
    for method in ("DEER", "TJE", "CertaIndex"):
        points = lines[method]
        color, marker, label = METHOD_STYLE[method]
        axis.plot(
            [p["accuracy_drop_pp"] for p in points],
            [p["token_saving_pct"] for p in points],
            color=color,
            marker=marker,
            markersize=6,
            linewidth=1.9,
            markeredgecolor="white",
            markeredgewidth=0.5,
            label=label,
            zorder=3,
        )
    if oracle_point is not None:
        axis.scatter(
            [oracle_point["accuracy_drop_pp"]],
            [oracle_point["token_saving_pct"]],
            marker="D",
            s=95,
            color="#0f766e",
            edgecolors="white",
            linewidths=0.8,
            zorder=5,
            label="Oracle (first correct probe)",
        )
    axis.axvline(0, color="#64748b", linewidth=0.9, alpha=0.7)
    axis.axhline(0, color="#64748b", linewidth=0.9, alpha=0.7)
    axis.grid(True, color="#cbd5e1", linewidth=0.6, alpha=0.5)
    axis.set_title(VIEW_TITLES[view])
    axis.set_xlabel("Accuracy drop vs full (pp) — lower is better")
    axis.set_ylabel("All-generated-token saving (%) — higher is better")
    axis.text(
        0.02, 0.98, "Preferred ↖", transform=axis.transAxes,
        ha="left", va="top", fontsize=8.5, color="#475569",
    )
    axis.legend(loc="lower right", fontsize=8)


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    print("TJE: committed replay rows ...", flush=True)
    tje, tje_total = committed_line(TJE_ROWS, "top_k")
    if tje_total != EXPECTED_TRAJECTORIES * 6:
        raise ValueError(f"TJE rows: {tje_total}")
    print("CertaIndex: committed effort replay rows (tau=1 window sweep) ...", flush=True)
    certaindex, ci_total = committed_line(CERTAINDEX_ROWS, "patience")
    if ci_total != EXPECTED_TRAJECTORIES * 4:
        raise ValueError(f"CertaIndex rows: {ci_total}")
    print("Oracle: committed decision ...", flush=True)
    oracle = oracle_records()
    print("DEER: re-derive per-problem records from confidence bank ...", flush=True)
    deer = deer_records()

    sweeps = {"DEER": deer, "TJE": tje, "CertaIndex": certaindex}
    views = ["pooled", "macro", *BENCHMARKS]

    csv_rows: list[dict[str, Any]] = []
    for view in views:
        for method, sweep in sweeps.items():
            for point in build_line(sweep, view):
                csv_rows.append({"view": view, "method": method, **point})
        ora = aggregate(oracle, view)
        if ora is not None:
            csv_rows.append({"view": view, "method": "Oracle", "param": "", **ora})
    with (RESULTS / "frontier_points.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "view", "method", "param", "n", "accuracy_drop_pp",
                "token_saving_pct", "baseline_accuracy_pct", "accuracy_pct",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    for view in views:
        lines = {m: build_line(s, view) for m, s in sweeps.items()}
        fig, axis = plt.subplots(figsize=(7.4, 5.6), constrained_layout=True)
        plot_view(axis, view, lines, aggregate(oracle, view))
        fig.suptitle("Vanilla early-exit signal frontiers", fontsize=13)
        for suffix in ("png", "pdf"):
            fig.savefig(FIGURES / f"vanilla_frontier_{view}.{suffix}", dpi=220)
        plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(19.5, 11.0), constrained_layout=True)
    flat = axes.flatten()
    for index, view in enumerate(views):
        lines = {m: build_line(s, view) for m, s in sweeps.items()}
        plot_view(flat[index], view, lines, aggregate(oracle, view))
    flat[-1].axis("off")
    fig.suptitle(
        "Vanilla early-exit signal frontiers over all Governor v2 "
        "trajectories (train + dev + test)",
        fontsize=16,
    )
    for suffix in ("png", "pdf"):
        fig.savefig(FIGURES / f"vanilla_frontier_overview.{suffix}", dpi=200)
    plt.close(fig)

    print(f"figures -> {FIGURES}")
    print(f"points  -> {RESULTS / 'frontier_points.csv'}")


if __name__ == "__main__":
    main()
