#!/usr/bin/env python3
"""Plot the corrected Llama-8B scale sweep in the earlier train/dev style.

Each point macro-averages three benchmark cells after pooling the three seeds
within each benchmark. Train filtering retains rules within two percentage
points of the best saving envelope at the same or lower accuracy drop. The dev
frontier is then computed only over rules retained without looking at dev.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SWEEP = (
    REPO_ROOT
    / "benchmark/FalseConsensus/governor_v2/generated/"
    "sweep_scale_llama.jsonl.gz"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "benchmark/FalseConsensus/report/figures"
NEAR_PARETO_SAVING_SLACK_PCT = 2.0
HIGHLIGHT_RULE = "entropy_budget_fraction__1499bbc05821"


@dataclass(frozen=True)
class Point:
    rule_id: str
    split: str
    accuracy_drop_pp: float
    token_saving_pct: float


def load_points(sweep: Path) -> dict[str, dict[str, Point]]:
    # (rule, split, benchmark) ->
    # [n, correct, baseline_correct, total_decode_tokens, baseline_tokens]
    cells: dict[tuple[str, str, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0, 0.0]
    )
    opener = gzip.open if sweep.suffix == ".gz" else open
    with opener(sweep, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            split = str(row["split"])
            if split not in {"train", "dev"}:
                continue
            n = float(row["n"])
            cell = cells[
                (str(row["rule_id"]), split, str(row["benchmark"]))
            ]
            cell[0] += n
            cell[1] += n * float(row["accuracy"])
            cell[2] += n * float(row["baseline_accuracy"])
            cell[3] += n * float(row["avg_total_decode_tokens"])
            cell[4] += n * float(row["avg_baseline_decode_tokens"])

    by_rule_split: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (rule_id, split, _benchmark), cell in cells.items():
        n, correct, baseline_correct, used_tokens, baseline_tokens = cell
        if n <= 0 or baseline_tokens <= 0:
            raise ValueError(f"invalid cell for {rule_id}/{split}")
        by_rule_split[(rule_id, split)].append(
            (
                100.0 * (baseline_correct - correct) / n,
                100.0 * (baseline_tokens - used_tokens) / baseline_tokens,
            )
        )

    points: dict[str, dict[str, Point]] = {"train": {}, "dev": {}}
    for (rule_id, split), values in by_rule_split.items():
        if len(values) != 3:
            raise ValueError(
                f"expected three benchmark cells for {rule_id}/{split}, "
                f"observed {len(values)}"
            )
        points[split][rule_id] = Point(
            rule_id=rule_id,
            split=split,
            accuracy_drop_pp=sum(value[0] for value in values) / len(values),
            token_saving_pct=sum(value[1] for value in values) / len(values),
        )
    if set(points["train"]) != set(points["dev"]):
        raise ValueError("train/dev rule coverage mismatch")
    if len(points["train"]) != 17712:
        raise ValueError(
            f"expected 17,712 candidate rules, got {len(points['train'])}"
        )
    return points


def pareto_representatives(points: Iterable[Point]) -> list[Point]:
    coordinate_representatives: dict[tuple[float, float], Point] = {}
    for point in points:
        coordinate = (
            round(point.accuracy_drop_pp, 12),
            round(point.token_saving_pct, 12),
        )
        current = coordinate_representatives.get(coordinate)
        if current is None or point.rule_id < current.rule_id:
            coordinate_representatives[coordinate] = point
    ordered = sorted(
        coordinate_representatives.values(),
        key=lambda point: (
            point.accuracy_drop_pp,
            -point.token_saving_pct,
            point.rule_id,
        ),
    )
    frontier = []
    best_saving = float("-inf")
    for point in ordered:
        if point.token_saving_pct > best_saving + 1e-12:
            frontier.append(point)
            best_saving = point.token_saving_pct
    return frontier


def near_pareto_ids(
    points: Iterable[Point], *, saving_slack_pct: float
) -> set[str]:
    by_drop: dict[float, list[Point]] = defaultdict(list)
    for point in points:
        by_drop[round(point.accuracy_drop_pp, 12)].append(point)
    retained = set()
    best_saving = float("-inf")
    for drop in sorted(by_drop):
        group = by_drop[drop]
        best_saving = max(
            best_saving,
            max(point.token_saving_pct for point in group),
        )
        for point in group:
            if best_saving - point.token_saving_pct <= saving_slack_pct + 1e-12:
                retained.add(point.rule_id)
    return retained


def plot_panel(
    axis,
    *,
    split: str,
    points: dict[str, Point],
    retained_ids: set[str],
    frontier: list[Point],
) -> None:
    filtered = [
        point for rule_id, point in points.items() if rule_id not in retained_ids
    ]
    retained = [
        point for rule_id, point in points.items() if rule_id in retained_ids
    ]
    axis.scatter(
        [point.accuracy_drop_pp for point in filtered],
        [point.token_saving_pct for point in filtered],
        s=7,
        alpha=0.10,
        color="#94a3b8",
        linewidths=0,
        rasterized=True,
        label=f"Outside train buffer ({len(filtered):,})",
    )
    axis.scatter(
        [point.accuracy_drop_pp for point in retained],
        [point.token_saving_pct for point in retained],
        s=21,
        alpha=0.72,
        color="#2563eb",
        edgecolors="white",
        linewidths=0.25,
        zorder=3,
        label=f"Train-retained ({len(retained):,})",
    )
    ordered_frontier = sorted(frontier, key=lambda point: point.accuracy_drop_pp)
    axis.step(
        [point.accuracy_drop_pp for point in ordered_frontier],
        [point.token_saving_pct for point in ordered_frontier],
        where="post",
        color="#dc2626",
        linewidth=2.0,
        zorder=4,
        label=(
            "Train Pareto boundary"
            if split == "train"
            else "Dev boundary after train filter"
        ),
    )
    highlight = points.get(HIGHLIGHT_RULE)
    if highlight is not None:
        axis.scatter(
            [highlight.accuracy_drop_pp],
            [highlight.token_saving_pct],
            s=115,
            marker="D",
            color="#f59e0b",
            edgecolors="white",
            linewidths=0.8,
            zorder=6,
            label="Best Llama token-efficient rule",
        )
        axis.annotate(
            (
                f"Token-efficient\n"
                f"({highlight.accuracy_drop_pp:.1f}, "
                f"{highlight.token_saving_pct:.1f})"
            ),
            (highlight.accuracy_drop_pp, highlight.token_saving_pct),
            xytext=(8, 7),
            textcoords="offset points",
            fontsize=8.5,
            fontweight="medium",
        )
    axis.axvline(0, color="#64748b", linewidth=0.8, alpha=0.55)
    axis.axhline(0, color="#64748b", linewidth=0.8, alpha=0.55)
    axis.grid(True, color="#cbd5e1", linewidth=0.6, alpha=0.45)
    axis.set_xlabel("Accuracy drop vs Full (pp) — lower is better")
    axis.set_title(
        (
            "Train: near-Pareto filtering"
            if split == "train"
            else "Dev: transfer of train-retained rules"
        ),
        loc="left",
        fontsize=12.5,
        fontweight="medium",
    )
    axis.text(
        0.015,
        0.985,
        "Preferred direction ↖",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color="#475569",
    )
    axis.legend(loc="lower right", framealpha=0.95, fontsize=7.8)


def write_points(
    output: Path,
    train: dict[str, Point],
    dev: dict[str, Point],
    retained_ids: set[str],
    train_frontier: list[Point],
    dev_frontier: list[Point],
) -> None:
    train_frontier_ids = {point.rule_id for point in train_frontier}
    dev_frontier_ids = {point.rule_id for point in dev_frontier}
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rule_id",
                "train_accuracy_drop_pp",
                "train_token_saving_pct",
                "train_retained",
                "train_frontier",
                "dev_accuracy_drop_pp",
                "dev_token_saving_pct",
                "dev_frontier_after_train_filter",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for rule_id in sorted(train):
            writer.writerow(
                {
                    "rule_id": rule_id,
                    "train_accuracy_drop_pp": f"{train[rule_id].accuracy_drop_pp:.8f}",
                    "train_token_saving_pct": f"{train[rule_id].token_saving_pct:.8f}",
                    "train_retained": str(rule_id in retained_ids).lower(),
                    "train_frontier": str(
                        rule_id in train_frontier_ids
                    ).lower(),
                    "dev_accuracy_drop_pp": f"{dev[rule_id].accuracy_drop_pp:.8f}",
                    "dev_token_saving_pct": f"{dev[rule_id].token_saving_pct:.8f}",
                    "dev_frontier_after_train_filter": str(
                        rule_id in dev_frontier_ids
                    ).lower(),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", type=Path, default=DEFAULT_SWEEP)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    points = load_points(args.sweep)
    train_frontier = pareto_representatives(points["train"].values())
    retained_ids = near_pareto_ids(
        points["train"].values(),
        saving_slack_pct=NEAR_PARETO_SAVING_SLACK_PCT,
    )
    dev_frontier = pareto_representatives(
        points["dev"][rule_id] for rule_id in retained_ids
    )

    all_values = list(points["train"].values()) + list(points["dev"].values())
    x_min = min(-2.5, min(point.accuracy_drop_pp for point in all_values) - 2)
    x_max = max(point.accuracy_drop_pp for point in all_values) + 3
    y_min = min(-12.0, min(point.token_saving_pct for point in all_values) - 3)
    y_max = min(100.0, max(point.token_saving_pct for point in all_values) + 4)

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(13.2, 5.7),
        sharex=True,
        sharey=True,
    )
    plot_panel(
        axes[0],
        split="train",
        points=points["train"],
        retained_ids=retained_ids,
        frontier=train_frontier,
    )
    plot_panel(
        axes[1],
        split="dev",
        points=points["dev"],
        retained_ids=retained_ids,
        frontier=dev_frontier,
    )
    axes[0].set_ylabel(
        "Total-decode-token saving (%) — higher is better"
    )
    for axis in axes:
        axis.set_xlim(x_min, x_max)
        axis.set_ylim(y_min, y_max)
    fig.suptitle(
        "Llama-8B Governor candidate rules: train filtering and dev transfer",
        x=0.055,
        ha="left",
        fontsize=14,
        fontweight="medium",
    )
    fig.text(
        0.055,
        0.015,
        (
            "Macro over MATH500, AMC23, and AIME24 after pooling seeds; "
            "train saving-envelope slack = 2 pp."
        ),
        fontsize=8.5,
        color="#475569",
    )
    fig.tight_layout(rect=(0, 0.045, 1, 0.95))

    stem = args.output_dir / "scale_llama_train_dev_pareto"
    fig.savefig(stem.with_suffix(".png"), dpi=240, bbox_inches="tight")
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    write_points(
        stem.with_name(f"{stem.name}_points.csv"),
        points["train"],
        points["dev"],
        retained_ids,
        train_frontier,
        dev_frontier,
    )
    print(
        json.dumps(
            {
                "candidate_rules": len(points["train"]),
                "train_strict_frontier": len(train_frontier),
                "train_retained": len(retained_ids),
                "train_filtered": len(points["train"]) - len(retained_ids),
                "dev_frontier_after_train_filter": len(dev_frontier),
                "highlight_rule": HIGHLIGHT_RULE,
                "highlight_train": points["train"][HIGHLIGHT_RULE].__dict__,
                "highlight_dev": points["dev"][HIGHLIGHT_RULE].__dict__,
                "output_stem": str(stem),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
