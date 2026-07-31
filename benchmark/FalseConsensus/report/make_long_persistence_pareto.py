#!/usr/bin/env python3
"""Plot the post-hoc long-persistence expansion against the frozen sweep.

The figures use the same macro convention and related-work anchors as
``make_governor_related_work_pareto.py``.  They keep the preregistered and
post-hoc rule sets visually distinct and show both a full view and a zoom of
the low-drop decision region.
"""

from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[3]
GOVERNOR = REPO_ROOT / "benchmark/FalseConsensus/governor_v2"
ORIGINAL_SWEEPS = [
    GOVERNOR / f"generated/sweep_{index}.jsonl.gz" for index in range(8)
]
LONG_DIR = GOVERNOR / "generated/long_persistence_sensitivity"
LONG_SWEEPS = [LONG_DIR / f"sweep_{index}.jsonl.gz" for index in range(8)]
LONG_RULES = LONG_DIR / "candidate_rules_incremental.jsonl"
LONG_SUMMARY = (
    GOVERNOR / "analysis/long_persistence_sensitivity/summary.json"
)
RELATED_WORK_CSV = (
    REPO_ROOT
    / "benchmark/FalseConsensus/results/related_work/aggregate/environment_split.csv"
)
DEER_DYNAMIC_CSV = (
    REPO_ROOT
    / "benchmark/FalseConsensus/results/related_work/"
    "deer_confidence_bank_cap30/aggregate/frontier.csv"
)
TJE_DYNAMIC_CSV = (
    REPO_ROOT
    / "benchmark/FalseConsensus/results/related_work/"
    "tje_threshold_readout_bank_top1_6/aggregate/frontier.csv"
)
CERTAINDEX_DYNAMIC_CSV = (
    REPO_ROOT
    / "benchmark/FalseConsensus/results/related_work/"
    "certaindex_effort_bank/aggregate/frontier.csv"
)
ORACLE_ENV_CSV = (
    REPO_ROOT
    / "benchmark/FalseConsensus/results/governor_v2/simple32_oracle/per_environment.csv"
)
OUTPUT_DIR = REPO_ROOT / "benchmark/FalseConsensus/report/figures"

METHOD_LABELS = {
    "certaindex_mid_frozen": "CertaIndex",
    "deer_frozen": "Faithful DEER",
    "tje_frozen": "TJE",
}
METHOD_MARKERS = {
    "CertaIndex": "s",
    "Faithful DEER": "D",
    "TJE": "*",
}
METHOD_COLORS = {
    "CertaIndex": "#7c3aed",
    "Faithful DEER": "#059669",
    "TJE": "#ea580c",
}

COLOR_ORIGINAL = "#94a3b8"
COLOR_LONG = "#0d9488"
COLOR_ORIGINAL_FRONTIER = "#dc2626"
COLOR_EXPANDED_FRONTIER = "#1d4ed8"
COLOR_REPRESENTATIVE = "#f59e0b"
COLOR_DEER_DYNAMIC = "#047857"
COLOR_TJE_DYNAMIC = "#ea580c"
COLOR_CERTAINDEX_DYNAMIC = "#7c3aed"
COLOR_ORACLE = "#111827"


@dataclass(frozen=True)
class Point:
    rule_id: str
    split: str
    accuracy_drop_pp: float
    token_saving_pct: float


@dataclass(frozen=True)
class DEERPoint:
    split: str
    max_probes: int
    threshold: float
    accuracy_drop_pp: float
    token_saving_pct: float


@dataclass(frozen=True)
class TJEPoint:
    split: str
    top_k: int
    threshold_label: str
    accuracy_drop_pp: float
    token_saving_pct: float


@dataclass(frozen=True)
class CertaIndexPoint:
    split: str
    effort: str
    patience: int
    accuracy_drop_pp: float
    token_saving_pct: float


def load_rows(path: Path) -> Iterable[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def macro_points(paths: Sequence[Path]) -> dict[str, dict[str, Point]]:
    cells: dict[tuple[str, str, str, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0, 0.0]
    )
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        for row in load_rows(path):
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

    grouped: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (rule_id, split, _model, _benchmark), values in cells.items():
        n, correct, baseline_correct, used_tokens, baseline_tokens = values
        if n <= 0 or baseline_tokens <= 0:
            raise ValueError(f"invalid macro cell: {rule_id}/{split}")
        grouped[(rule_id, split)].append(
            (
                100.0 * (baseline_correct - correct) / n,
                100.0 * (baseline_tokens - used_tokens) / baseline_tokens,
            )
        )

    points: dict[str, dict[str, Point]] = {"train": {}, "dev": {}}
    for (rule_id, split), values in grouped.items():
        if len(values) != 6:
            raise ValueError(
                f"expected six model x benchmark cells for {rule_id}/{split}, "
                f"got {len(values)}"
            )
        points[split][rule_id] = Point(
            rule_id=rule_id,
            split=split,
            accuracy_drop_pp=sum(value[0] for value in values) / 6,
            token_saving_pct=sum(value[1] for value in values) / 6,
        )
    if set(points["train"]) != set(points["dev"]):
        raise ValueError("train/dev rule sets differ")
    return points


def related_work_points() -> dict[str, dict[str, Point]]:
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

    grouped: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (method, split, _model, _benchmark), values in cells.items():
        n, correct, baseline_correct, used_tokens, baseline_tokens = values
        grouped[(method, split)].append(
            (
                100.0 * (baseline_correct - correct) / n,
                100.0 * (baseline_tokens - used_tokens) / baseline_tokens,
            )
        )

    points: dict[str, dict[str, Point]] = {"train": {}, "dev": {}}
    for (method, split), values in grouped.items():
        if len(values) != 6:
            raise ValueError(
                f"expected six cells for {method}/{split}, got {len(values)}"
            )
        label = METHOD_LABELS[method]
        points[split][label] = Point(
            rule_id=label,
            split=split,
            accuracy_drop_pp=sum(value[0] for value in values) / 6,
            token_saving_pct=sum(value[1] for value in values) / 6,
        )
    return points


def oracle_points() -> dict[str, Point]:
    """Load the label-using, non-deployable simple@32 upper bound."""
    rows = list(csv.DictReader(ORACLE_ENV_CSV.open(encoding="utf-8")))
    output: dict[str, Point] = {}
    for split in ("train", "dev"):
        selected = [row for row in rows if row["split"] == split]
        if len(selected) != 18:
            raise ValueError(f"expected 18 oracle environments for {split}, got {len(selected)}")
        output[split] = Point(
            rule_id="Non-deployable oracle",
            split=split,
            accuracy_drop_pp=sum(
                float(row["full_accuracy_strict_pct"])
                - float(row["oracle_accuracy_strict_pct"])
                for row in selected
            )
            / len(selected),
            token_saving_pct=sum(float(row["token_saving_micro_pct"]) for row in selected)
            / len(selected),
        )
    return output


def deer_dynamic_frontiers() -> dict[str, list[DEERPoint]]:
    if not DEER_DYNAMIC_CSV.exists():
        raise FileNotFoundError(DEER_DYNAMIC_CSV)
    rows = list(csv.DictReader(DEER_DYNAMIC_CSV.open(encoding="utf-8")))
    output: dict[str, list[DEERPoint]] = {}
    for split in ("train", "dev"):
        candidates = [
            DEERPoint(
                split=split,
                max_probes=int(row["max_probes"]),
                threshold=float(row["threshold"]),
                accuracy_drop_pp=float(row["accuracy_drop_pp"]),
                token_saving_pct=float(row["token_saving_pct"]),
            )
            for row in rows
            if row["scope"] == split
            and row["aggregation"] == "model_benchmark_macro"
        ]
        if len(candidates) != 90:
            raise ValueError(
                f"expected 90 DEER sweep points for {split}, "
                f"got {len(candidates)}"
            )
        coordinate_representatives: dict[tuple[float, float], DEERPoint] = {}
        for point in candidates:
            coordinate = (
                round(point.accuracy_drop_pp, 12),
                round(point.token_saving_pct, 12),
            )
            current = coordinate_representatives.get(coordinate)
            if current is None or (
                point.max_probes,
                point.threshold,
            ) < (
                current.max_probes,
                current.threshold,
            ):
                coordinate_representatives[coordinate] = point
        ordered = sorted(
            coordinate_representatives.values(),
            key=lambda point: (
                point.accuracy_drop_pp,
                -point.token_saving_pct,
                point.max_probes,
                point.threshold,
            ),
        )
        frontier: list[DEERPoint] = []
        best_saving = float("-inf")
        for point in ordered:
            if point.token_saving_pct > best_saving + 1e-12:
                frontier.append(point)
                best_saving = point.token_saving_pct
        output[split] = frontier
    return output


def tje_dynamic_frontiers() -> dict[str, list[TJEPoint]]:
    if not TJE_DYNAMIC_CSV.exists():
        raise FileNotFoundError(TJE_DYNAMIC_CSV)
    rows = list(csv.DictReader(TJE_DYNAMIC_CSV.open(encoding="utf-8")))
    output: dict[str, list[TJEPoint]] = {}
    for split in ("train", "dev"):
        points = [
            TJEPoint(
                split=split,
                top_k=int(row["top_k"]),
                threshold_label=str(row["threshold_label"]),
                accuracy_drop_pp=float(row["accuracy_drop_pp"]),
                token_saving_pct=float(row["token_saving_pct"]),
            )
            for row in rows
            if row["scope"] == split
            and row["aggregation"] == "model_benchmark_macro"
        ]
        if len(points) != 6:
            raise ValueError(
                f"expected six TJE threshold points for {split}, "
                f"got {len(points)}"
            )
        output[split] = sorted(points, key=lambda point: point.top_k)
    return output


def certaindex_dynamic_frontiers() -> dict[str, list[CertaIndexPoint]]:
    if not CERTAINDEX_DYNAMIC_CSV.exists():
        raise FileNotFoundError(CERTAINDEX_DYNAMIC_CSV)
    rows = list(csv.DictReader(CERTAINDEX_DYNAMIC_CSV.open(encoding="utf-8")))
    effort_order = {"mild": 0, "low": 1, "mid": 2, "high": 3}
    output: dict[str, list[CertaIndexPoint]] = {}
    for split in ("train", "dev"):
        points = [
            CertaIndexPoint(
                split=split,
                effort=str(row["effort"]),
                patience=int(row["patience"]),
                accuracy_drop_pp=float(row["accuracy_drop_pp"]),
                token_saving_pct=float(row["token_saving_pct"]),
            )
            for row in rows
            if row["scope"] == split
            and row["aggregation"] == "model_benchmark_macro"
        ]
        if len(points) != 4:
            raise ValueError(
                f"expected four CertaIndex effort points for {split}, "
                f"got {len(points)}"
            )
        output[split] = sorted(
            points, key=lambda point: effort_order[point.effort]
        )
    return output


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
    frontier: list[Point] = []
    best_saving = float("-inf")
    for point in ordered:
        if point.token_saving_pct > best_saving + 1e-12:
            frontier.append(point)
            best_saving = point.token_saving_pct
    return frontier


def window_by_rule() -> dict[str, int]:
    return {
        str(row["rule_id"]): int(
            row["persistence"]["minimum_consistent_accepts"]
        )
        for row in load_rows(LONG_RULES)
    }


def representative_ids() -> dict[int, str]:
    summary = json.loads(LONG_SUMMARY.read_text(encoding="utf-8"))
    return {
        int(row["window"]): str(row["minimum_drop_point"]["rule_id"])
        for row in summary["windows"]
    }


def plot_points(
    axis,
    *,
    original: Mapping[str, Point],
    long: Mapping[str, Point],
    original_frontier: Sequence[Point],
    expanded_frontier: Sequence[Point],
    new_frontier_ids: set[str],
    representatives: Mapping[int, Point],
    baselines: Mapping[str, Point],
    deer_frontier: Sequence[DEERPoint],
    tje_frontier: Sequence[TJEPoint],
    certaindex_frontier: Sequence[CertaIndexPoint],
    oracle: Point,
    zoom: bool,
) -> None:
    axis.scatter(
        [point.accuracy_drop_pp for point in original.values()],
        [point.token_saving_pct for point in original.values()],
        s=8 if not zoom else 12,
        alpha=0.10,
        color=COLOR_ORIGINAL,
        linewidths=0,
        rasterized=True,
        label=f"Preregistered candidates ({len(original):,})",
    )
    axis.scatter(
        [point.accuracy_drop_pp for point in long.values()],
        [point.token_saving_pct for point in long.values()],
        s=9 if not zoom else 14,
        alpha=0.12,
        color=COLOR_LONG,
        linewidths=0,
        rasterized=True,
        label=f"Added long-window candidates ({len(long):,})",
    )

    ordered_original = sorted(
        original_frontier, key=lambda point: point.accuracy_drop_pp
    )
    axis.step(
        [point.accuracy_drop_pp for point in ordered_original],
        [point.token_saving_pct for point in ordered_original],
        where="post",
        color=COLOR_ORIGINAL_FRONTIER,
        linestyle="--",
        linewidth=1.7,
        zorder=4,
        label="Original Pareto boundary",
    )
    ordered_expanded = sorted(
        expanded_frontier, key=lambda point: point.accuracy_drop_pp
    )
    axis.step(
        [point.accuracy_drop_pp for point in ordered_expanded],
        [point.token_saving_pct for point in ordered_expanded],
        where="post",
        color=COLOR_EXPANDED_FRONTIER,
        linewidth=2.2,
        zorder=5,
        label="Expanded Pareto boundary",
    )

    frontier_points = [
        long[rule_id] for rule_id in sorted(new_frontier_ids)
    ]
    axis.scatter(
        [point.accuracy_drop_pp for point in frontier_points],
        [point.token_saving_pct for point in frontier_points],
        s=38 if not zoom else 52,
        marker="o",
        color=COLOR_LONG,
        edgecolors="white",
        linewidths=0.7,
        zorder=6,
        label=f"Long-window frontier entrants ({len(frontier_points)})",
    )

    ordered_deer = sorted(
        deer_frontier, key=lambda point: point.accuracy_drop_pp
    )
    axis.plot(
        [point.accuracy_drop_pp for point in ordered_deer],
        [point.token_saving_pct for point in ordered_deer],
        color=COLOR_DEER_DYNAMIC,
        linewidth=2.4,
        marker="^",
        markersize=4.5,
        markeredgecolor="white",
        markeredgewidth=0.45,
        zorder=7,
        label=(
            "DEER direct-submit frontier "
            f"({len(ordered_deer)} operating points)"
        ),
    )

    axis.plot(
        [point.accuracy_drop_pp for point in tje_frontier],
        [point.token_saving_pct for point in tje_frontier],
        color=COLOR_TJE_DYNAMIC,
        linewidth=2.4,
        marker="*",
        markersize=8,
        markeredgecolor="white",
        markeredgewidth=0.45,
        zorder=8,
        label="TJE confidence frontier (top-1…top-6)",
    )
    if zoom:
        for point in tje_frontier:
            axis.annotate(
                f"T{point.top_k}",
                (point.accuracy_drop_pp, point.token_saving_pct),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7.5,
                color="#9a3412",
                zorder=9,
            )

    axis.plot(
        [point.accuracy_drop_pp for point in certaindex_frontier],
        [point.token_saving_pct for point in certaindex_frontier],
        color=COLOR_CERTAINDEX_DYNAMIC,
        linewidth=2.4,
        marker="s",
        markersize=5.5,
        markeredgecolor="white",
        markeredgewidth=0.45,
        zorder=8,
        label="CertaIndex effort frontier (mild…high)",
    )
    if not zoom:
        for point in certaindex_frontier:
            offset_y = {
                "mild": 4,
                "low": -15,
                "mid": -13,
                "high": -13,
            }[point.effort]
            axis.annotate(
                f"CI-{point.effort}",
                (point.accuracy_drop_pp, point.token_saving_pct),
                xytext=(4, offset_y),
                textcoords="offset points",
                fontsize=7.5,
                color="#5b21b6",
                zorder=9,
            )

    axis.scatter(
        [oracle.accuracy_drop_pp],
        [oracle.token_saving_pct],
        s=190,
        marker="*",
        color=COLOR_ORACLE,
        edgecolors="white",
        linewidths=0.9,
        zorder=11,
        label="Oracle upper bound (uses labels)",
    )
    axis.annotate(
        f"Oracle\n({oracle.accuracy_drop_pp:.1f}, {oracle.token_saving_pct:.1f})",
        (oracle.accuracy_drop_pp, oracle.token_saving_pct),
        xytext=(7, 5),
        textcoords="offset points",
        fontsize=8.5,
        fontweight="medium",
        color=COLOR_ORACLE,
        zorder=12,
    )

    for window, point in representatives.items():
        axis.scatter(
            [point.accuracy_drop_pp],
            [point.token_saving_pct],
            s=70 if not zoom else 88,
            marker="P",
            color=COLOR_REPRESENTATIVE,
            edgecolors="white",
            linewidths=0.8,
            zorder=7,
            label="Per-window safest point" if window == 10 else None,
        )
        if zoom:
            label_positions = {
                "train": {
                    10: (0.15, 14.4),
                    12: (0.75, 18.2),
                    16: (-2.35, 12.5),
                    20: (-1.15, 7.8),
                    25: (-2.35, 4.2),
                    30: (-1.25, -1.8),
                },
                "dev": {
                    10: (4.75, 16.6),
                    12: (4.75, 12.4),
                    16: (2.45, 10.4),
                    20: (1.05, 6.5),
                    25: (2.25, 3.2),
                    30: (1.20, -1.4),
                },
            }
            axis.annotate(
                f"w={window}",
                (point.accuracy_drop_pp, point.token_saving_pct),
                xytext=label_positions[point.split][window],
                textcoords="data",
                fontsize=8.5,
                fontweight="medium",
                color="#92400e",
                arrowprops={
                    "arrowstyle": "-",
                    "color": "#b45309",
                    "linewidth": 0.65,
                    "shrinkA": 2,
                    "shrinkB": 3,
                },
                bbox={
                    "boxstyle": "round,pad=0.15",
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.82,
                },
                zorder=8,
            )

    for label, point in baselines.items():
        if label in {"TJE", "CertaIndex"}:
            # These faithful points are on their corresponding dynamic curves.
            continue
        if zoom and not (
            -2.5 <= point.accuracy_drop_pp <= 13
            and -8 <= point.token_saving_pct <= 42
        ):
            continue
        axis.scatter(
            [point.accuracy_drop_pp],
            [point.token_saving_pct],
            s=120 if label != "TJE" else 165,
            marker=METHOD_MARKERS[label],
            color=METHOD_COLORS[label],
            edgecolors="white",
            linewidths=0.8,
            zorder=9,
            label=label if not zoom else None,
        )
        offset = {
            "CertaIndex": (7, 7),
            "Faithful DEER": (7, -18 if zoom else 7),
            "TJE": (7, 7),
        }[label]
        axis.annotate(
            f"{label}\n({point.accuracy_drop_pp:.1f}, "
            f"{point.token_saving_pct:.1f})",
            (point.accuracy_drop_pp, point.token_saving_pct),
            xytext=offset,
            textcoords="offset points",
            fontsize=8.5,
            fontweight="medium",
            zorder=10,
        )

    axis.axvline(0, color="#64748b", linewidth=0.8, alpha=0.55)
    axis.axhline(0, color="#64748b", linewidth=0.8, alpha=0.55)
    axis.grid(True, color="#cbd5e1", linewidth=0.6, alpha=0.45)
    if zoom:
        axis.set_xlim(-10.5, 13)
        axis.set_ylim(-8, 62)
        axis.set_title("Low-drop region", fontsize=11, fontweight="medium")
    else:
        axis.set_xlim(-3, 83)
        axis.set_ylim(-13, 100)
        axis.set_title("Full operating range", fontsize=11, fontweight="medium")
    axis.text(
        0.02,
        0.98,
        "Preferred direction ↖",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color="#475569",
    )
    axis.set_xlabel("Accuracy drop vs Full (pp) — lower is better")
    axis.set_ylabel("All-generated-token saving (%) — higher is better")


def write_representatives(
    path: Path,
    *,
    representative_rule_ids: Mapping[int, str],
    train: Mapping[str, Point],
    dev: Mapping[str, Point],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "window",
                "rule_id",
                "train_accuracy_drop_pp",
                "train_token_saving_pct",
                "dev_accuracy_drop_pp",
                "dev_token_saving_pct",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for window, rule_id in sorted(representative_rule_ids.items()):
            writer.writerow(
                {
                    "window": window,
                    "rule_id": rule_id,
                    "train_accuracy_drop_pp": train[
                        rule_id
                    ].accuracy_drop_pp,
                    "train_token_saving_pct": train[
                        rule_id
                    ].token_saving_pct,
                    "dev_accuracy_drop_pp": dev[rule_id].accuracy_drop_pp,
                    "dev_token_saving_pct": dev[rule_id].token_saving_pct,
                }
            )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    original = macro_points(ORIGINAL_SWEEPS)
    long = macro_points(LONG_SWEEPS)
    baselines = related_work_points()
    deer_frontiers = deer_dynamic_frontiers()
    tje_frontiers = tje_dynamic_frontiers()
    certaindex_frontiers = certaindex_dynamic_frontiers()
    oracles = oracle_points()
    windows = window_by_rule()
    rep_ids = representative_ids()
    manifest: dict[str, dict] = {}

    for split in ("train", "dev"):
        combined = {**original[split], **long[split]}
        original_frontier = pareto_representatives(
            original[split].values()
        )
        expanded_frontier = pareto_representatives(combined.values())
        new_frontier_ids = {
            point.rule_id
            for point in expanded_frontier
            if point.rule_id in long[split]
        }
        representatives = {
            window: long[split][rule_id]
            for window, rule_id in rep_ids.items()
        }

        fig, axes = plt.subplots(
            1,
            2,
            figsize=(15.8, 7.1),
            gridspec_kw={"width_ratios": [1.42, 1.0]},
        )
        for axis, zoom in zip(axes, (False, True)):
            plot_points(
                axis,
                original=original[split],
                long=long[split],
                original_frontier=original_frontier,
                expanded_frontier=expanded_frontier,
                new_frontier_ids=new_frontier_ids,
                representatives=representatives,
                baselines=baselines[split],
                deer_frontier=deer_frontiers[split],
                tje_frontier=tje_frontiers[split],
                certaindex_frontier=certaindex_frontiers[split],
                oracle=oracles[split],
                zoom=zoom,
            )
        axes[1].set_ylabel("")
        title_split = "Train" if split == "train" else "Dev"
        fig.suptitle(
            f"{title_split}: consensus and related-work frontiers "
            "(post-hoc sensitivity)",
            x=0.055,
            ha="left",
            fontsize=16,
            fontweight="medium",
        )
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.01),
            ncols=5,
            frameon=True,
            framealpha=0.96,
            fontsize=8.5,
        )
        fig.tight_layout(rect=(0, 0.10, 1, 0.96))
        stem = f"governor_long_persistence_pareto_{split}"
        fig.savefig(
            OUTPUT_DIR / f"{stem}.png",
            dpi=240,
            bbox_inches="tight",
        )
        fig.savefig(OUTPUT_DIR / f"{stem}.pdf", bbox_inches="tight")
        plt.close(fig)

        manifest[split] = {
            "original_candidates": len(original[split]),
            "long_window_candidates": len(long[split]),
            "original_macro_frontier": len(original_frontier),
            "expanded_macro_frontier": len(expanded_frontier),
            "long_window_macro_frontier_entrants": len(new_frontier_ids),
            "deer_direct_submit_frontier_points": len(
                deer_frontiers[split]
            ),
            "tje_confidence_frontier_points": len(
                tje_frontiers[split]
            ),
            "certaindex_effort_frontier_points": len(
                certaindex_frontiers[split]
            ),
            "oracle_non_deployable": {
                "accuracy_drop_pp": oracles[split].accuracy_drop_pp,
                "token_saving_pct": oracles[split].token_saving_pct,
                "uses_reference_labels": True,
            },
            "long_window_frontier_windows": dict(
                sorted(Counter(windows[rule_id] for rule_id in new_frontier_ids).items())
            )
            if new_frontier_ids
            else {},
        }

    write_representatives(
        OUTPUT_DIR / "governor_long_persistence_representatives.csv",
        representative_rule_ids=rep_ids,
        train=long["train"],
        dev=long["dev"],
    )
    (OUTPUT_DIR / "governor_long_persistence_pareto_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
