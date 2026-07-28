#!/usr/bin/env python3
"""Plot Governor candidate rules against related-work operating points.

The comparison uses the same macro convention as the related-work report:

1. pool the three seeds within each model x benchmark cell;
2. compute accuracy drop and all-generated-token saving per cell;
3. macro-average the six model x benchmark cells.

Train filtering uses a near-Pareto buffer instead of retaining only the strict
frontier.  For each accuracy-drop budget, a rule is retained when its token
saving is within two percentage points of the best train saving available at
the same or a lower accuracy drop.  The dev frontier is then computed only
among these train-retained rules.
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
GOVERNOR_DIR = REPO_ROOT / "benchmark/FalseConsensus/governor_v2"
SWEEP_DIR = GOVERNOR_DIR / "generated"
RELATED_WORK_CSV = (
    REPO_ROOT
    / "benchmark/FalseConsensus/results/related_work/aggregate/environment_split.csv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "benchmark/FalseConsensus/report/figures"
NEAR_PARETO_SAVING_SLACK_PCT = 2.0

METHOD_LABELS = {
    "certaindex_mid_frozen": "CertaIndex",
    "deer_frozen": "DEER",
    "tje_frozen": "TJE",
}
METHOD_MARKERS = {
    "CertaIndex": "s",
    "DEER": "D",
    "TJE": "*",
}
METHOD_COLORS = {
    "CertaIndex": "#7c3aed",
    "DEER": "#059669",
    "TJE": "#ea580c",
}


@dataclass(frozen=True)
class Point:
    rule_id: str
    split: str
    accuracy_drop_pp: float
    token_saving_pct: float


def _macro_points_from_sweep() -> dict[str, dict[str, Point]]:
    # (rule, split, model, benchmark) ->
    # [n, correct, baseline_correct, used_tokens, baseline_tokens]
    cells: dict[tuple[str, str, str, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0, 0.0]
    )
    for shard in sorted(SWEEP_DIR.glob("sweep_*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                split = str(row["split"])
                if split not in {"train", "dev"}:
                    continue
                n = float(row["n"])
                cell = cells[
                    (
                        str(row["rule_id"]),
                        split,
                        str(row["model"]),
                        str(row["benchmark"]),
                    )
                ]
                cell[0] += n
                cell[1] += n * float(row["accuracy"])
                cell[2] += n * float(row["baseline_accuracy"])
                cell[3] += n * float(row["avg_total_decode_tokens"])
                cell[4] += n * float(row["avg_baseline_decode_tokens"])

    by_rule_split: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (rule_id, split, _model, _benchmark), cell in cells.items():
        n, correct, baseline_correct, used_tokens, baseline_tokens = cell
        if n <= 0 or baseline_tokens <= 0:
            raise ValueError(f"invalid pooled cell for {rule_id}/{split}")
        drop = 100.0 * (baseline_correct - correct) / n
        saving = 100.0 * (baseline_tokens - used_tokens) / baseline_tokens
        by_rule_split[(rule_id, split)].append((drop, saving))

    points: dict[str, dict[str, Point]] = {"train": {}, "dev": {}}
    for (rule_id, split), values in by_rule_split.items():
        if len(values) != 6:
            raise ValueError(
                f"expected six model x benchmark cells for {rule_id}/{split}, "
                f"got {len(values)}"
            )
        points[split][rule_id] = Point(
            rule_id=rule_id,
            split=split,
            accuracy_drop_pp=sum(value[0] for value in values) / len(values),
            token_saving_pct=sum(value[1] for value in values) / len(values),
        )
    if set(points["train"]) != set(points["dev"]):
        raise ValueError("train and dev candidate rule sets differ")
    return points


def _related_work_points() -> dict[str, dict[str, Point]]:
    rows = list(csv.DictReader(RELATED_WORK_CSV.open(encoding="utf-8")))
    cells: dict[tuple[str, str, str, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0, 0.0]
    )
    for row in rows:
        method = str(row["method"])
        if method not in METHOD_LABELS:
            continue
        n = float(row["n"])
        cell = cells[
            (
                method,
                str(row["split"]),
                str(row["model"]),
                str(row["dataset"]),
            )
        ]
        cell[0] += n
        cell[1] += n * float(row["accuracy"])
        cell[2] += n * float(row["baseline_accuracy"])
        cell[3] += n * float(row["avg_all_generated_tokens"])
        cell[4] += n * float(row["avg_baseline_all_generated_tokens"])

    by_method_split: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (method, split, _model, _benchmark), cell in cells.items():
        n, correct, baseline_correct, used_tokens, baseline_tokens = cell
        by_method_split[(method, split)].append(
            (
                100.0 * (baseline_correct - correct) / n,
                100.0 * (baseline_tokens - used_tokens) / baseline_tokens,
            )
        )

    points: dict[str, dict[str, Point]] = {"train": {}, "dev": {}}
    for (method, split), values in by_method_split.items():
        if len(values) != 6:
            raise ValueError(
                f"expected six related-work cells for {method}/{split}, "
                f"got {len(values)}"
            )
        label = METHOD_LABELS[method]
        points[split][label] = Point(
            rule_id=label,
            split=split,
            accuracy_drop_pp=sum(value[0] for value in values) / len(values),
            token_saving_pct=sum(value[1] for value in values) / len(values),
        )
    return points


def _pareto_representatives(points: Iterable[Point]) -> list[Point]:
    """Return one lexical representative per strict 2D Pareto coordinate."""
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
    frontier: list[Point] = []
    best_saving = float("-inf")
    for point in ordered:
        if point.token_saving_pct > best_saving + 1e-12:
            frontier.append(point)
            best_saving = point.token_saving_pct
    return frontier


def _near_pareto_ids(
    points: Iterable[Point],
    *,
    saving_slack_pct: float,
) -> set[str]:
    """Keep rules close to the train saving envelope at their drop budget."""
    by_drop: dict[float, list[Point]] = defaultdict(list)
    for point in points:
        by_drop[round(point.accuracy_drop_pp, 12)].append(point)

    retained: set[str] = set()
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


def _plot_split(
    *,
    split: str,
    all_points: dict[str, Point],
    train_retained_ids: set[str],
    frontier: list[Point],
    baselines: dict[str, Point],
    output_dir: Path,
) -> None:
    filtered = [
        point for rule_id, point in all_points.items() if rule_id not in train_retained_ids
    ]
    retained = [
        point for rule_id, point in all_points.items() if rule_id in train_retained_ids
    ]

    fig, axis = plt.subplots(figsize=(10.6, 7.2))
    axis.scatter(
        [point.accuracy_drop_pp for point in filtered],
        [point.token_saving_pct for point in filtered],
        s=8,
        alpha=0.12,
        color="#94a3b8",
        linewidths=0,
        rasterized=True,
        label=f"Outside train near-Pareto buffer ({len(filtered):,})",
    )
    axis.scatter(
        [point.accuracy_drop_pp for point in retained],
        [point.token_saving_pct for point in retained],
        s=24,
        alpha=0.75,
        color="#2563eb",
        edgecolors="white",
        linewidths=0.25,
        zorder=3,
        label=f"Train-retained near-Pareto ({len(retained):,})",
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
            "Train Governor Pareto boundary"
            if split == "train"
            else "Dev Pareto boundary after train filter"
        ),
    )

    for label, point in baselines.items():
        axis.scatter(
            [point.accuracy_drop_pp],
            [point.token_saving_pct],
            s=130 if label != "TJE" else 180,
            marker=METHOD_MARKERS[label],
            color=METHOD_COLORS[label],
            edgecolors="white",
            linewidths=0.8,
            zorder=6,
            label=label,
        )
        axis.annotate(
            f"{label}\n({point.accuracy_drop_pp:.1f}, {point.token_saving_pct:.1f})",
            (point.accuracy_drop_pp, point.token_saving_pct),
            xytext=(7, 7),
            textcoords="offset points",
            fontsize=9,
            fontweight="medium",
        )

    axis.axvline(0, color="#64748b", linewidth=0.8, alpha=0.55)
    axis.axhline(0, color="#64748b", linewidth=0.8, alpha=0.55)
    axis.grid(True, color="#cbd5e1", linewidth=0.6, alpha=0.45)
    axis.set_xlim(-3, 83)
    axis.set_ylim(-13, 100)
    axis.set_xlabel("Accuracy drop vs Full (pp) — lower is better")
    axis.set_ylabel("All-generated-token saving (%) — higher is better")
    axis.set_title(
        (
            "Train: Governor near-Pareto filtering and related-work anchors"
            if split == "train"
            else "Dev: train-retained near-Pareto candidates and related-work anchors"
        ),
        loc="left",
        fontsize=14,
        fontweight="medium",
    )
    axis.text(
        0.01,
        0.99,
        "Preferred direction ↖",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        color="#475569",
    )
    axis.legend(
        loc="lower right",
        frameon=True,
        framealpha=0.95,
        fontsize=8.5,
        ncols=2,
    )
    fig.tight_layout()
    stem = f"governor_related_work_pareto_{split}"
    fig.savefig(output_dir / f"{stem}.png", dpi=240, bbox_inches="tight")
    fig.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def _write_frontier_csv(
    output: Path,
    train_points: dict[str, Point],
    dev_points: dict[str, Point],
    train_retained_ids: set[str],
    train_frontier: list[Point],
    dev_frontier: list[Point],
) -> None:
    strict_train_ids = {point.rule_id for point in train_frontier}
    dev_ids = {point.rule_id for point in dev_frontier}
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rule_id",
                "train_accuracy_drop_pp",
                "train_token_saving_pct",
                "train_retained",
                "strict_train_frontier",
                "dev_accuracy_drop_pp",
                "dev_token_saving_pct",
                "dev_frontier_after_train_filter",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for rule_id in sorted(train_retained_ids):
            train = train_points[rule_id]
            dev = dev_points[rule_id]
            writer.writerow(
                {
                    "rule_id": rule_id,
                    "train_accuracy_drop_pp": f"{train.accuracy_drop_pp:.8f}",
                    "train_token_saving_pct": f"{train.token_saving_pct:.8f}",
                    "train_retained": "true",
                    "strict_train_frontier": str(
                        rule_id in strict_train_ids
                    ).lower(),
                    "dev_accuracy_drop_pp": f"{dev.accuracy_drop_pp:.8f}",
                    "dev_token_saving_pct": f"{dev.token_saving_pct:.8f}",
                    "dev_frontier_after_train_filter": str(
                        rule_id in dev_ids
                    ).lower(),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    governor = _macro_points_from_sweep()
    baselines = _related_work_points()
    train_frontier = _pareto_representatives(governor["train"].values())
    train_retained_ids = _near_pareto_ids(
        governor["train"].values(),
        saving_slack_pct=NEAR_PARETO_SAVING_SLACK_PCT,
    )
    dev_frontier = _pareto_representatives(
        governor["dev"][rule_id] for rule_id in train_retained_ids
    )

    _plot_split(
        split="train",
        all_points=governor["train"],
        train_retained_ids=train_retained_ids,
        frontier=train_frontier,
        baselines=baselines["train"],
        output_dir=args.output_dir,
    )
    _plot_split(
        split="dev",
        all_points=governor["dev"],
        train_retained_ids=train_retained_ids,
        frontier=dev_frontier,
        baselines=baselines["dev"],
        output_dir=args.output_dir,
    )
    _write_frontier_csv(
        args.output_dir / "governor_related_work_pareto_frontiers.csv",
        governor["train"],
        governor["dev"],
        train_retained_ids,
        train_frontier,
        dev_frontier,
    )
    print(
        json.dumps(
            {
                "candidate_rules": len(governor["train"]),
                "train_strict_frontier": len(train_frontier),
                "near_pareto_saving_slack_pct": NEAR_PARETO_SAVING_SLACK_PCT,
                "train_retained": len(train_retained_ids),
                "train_filtered": len(governor["train"]) - len(train_retained_ids),
                "dev_frontier_after_train_filter": len(dev_frontier),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
