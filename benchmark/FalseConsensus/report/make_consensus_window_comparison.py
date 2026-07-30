#!/usr/bin/env python3
"""Compare strict-consensus window trajectories with DEER and TJE.

The script replays strict unanimous stopping for windows 2..30 over the same
2,736 development trajectories used by the related-work replay bank.  It
reports both problem-pooled and equal-environment-macro views.  Token saving
counts generated output tokens only: main output through stop plus every
consumed probe completion.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.governor_v2 import (  # noqa: E402
    analyze_multivariate_a1_a3 as consensus,
)
from benchmark.FalseConsensus.related_work.analyze_false_stops import (  # noqa: E402
    analyze as analyze_related,
)
from benchmark.FalseConsensus.related_work.analyze_false_stops import (  # noqa: E402
    load_replay_rows,
)


WINDOWS = tuple(range(2, 31))
RESULTS_ROOT = REPO / "benchmark/FalseConsensus/results/governor_v2"
REPLAY_ROOT = REPO / "benchmark/FalseConsensus/results/related_work/full/_replay"
OUTPUT_DIR = HERE / "figures"

SAVING_COLOR = "#287A63"
ACCURACY_COLOR = "#C66A21"
CONSENSUS_COLOR = "#565A61"
DEER_COLOR = "#2866B1"
TJE_COLOR = "#8A4FA3"


def collect() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    consensus.WINDOWS = WINDOWS
    trajectories, _ = consensus.load_bank(
        RESULTS_ROOT,
        environment_glob="development__*",
        expected_environments=18,
    )
    strict_records = consensus.strict_stop_records(trajectories)
    _, strict_summaries = consensus.aggregate_strict(strict_records)

    trajectory_rows: list[dict[str, Any]] = []
    for summary in strict_summaries:
        trajectory_rows.append(
            {
                "window": int(summary["window"]),
                "pooled_token_saving": float(
                    summary["pooled_net_output_saving"]
                ),
                "pooled_stop_accuracy": 1.0
                - float(summary["pooled_false_stop_rate_given_stop"]),
                "pooled_stop_coverage": float(summary["pooled_coverage"]),
                "pooled_overall_accuracy": float(
                    summary["pooled_delivered_accuracy"]
                ),
                "macro_token_saving": float(
                    summary["macro_net_output_saving"]
                ),
                "macro_stop_accuracy": 1.0
                - float(summary["macro_false_stop_rate_given_stop"]),
                "macro_stop_coverage": float(summary["macro_coverage"]),
                "macro_overall_accuracy": float(
                    summary["macro_delivered_accuracy"]
                ),
                "harm": int(summary["recovery_killed"]),
                "rescue": int(summary["overthinking_avoided"]),
            }
        )

    related = analyze_related(load_replay_rows(REPLAY_ROOT))
    baselines: dict[str, dict[str, Any]] = {}
    for method, label in (("deer_frozen", "DEER"), ("tje_frozen", "TJE")):
        payload = related["methods"][method]
        pooled = payload["pooled"]
        macro = payload["environment_macro"]
        baselines[label] = {
            "pooled_token_saving": float(
                pooled["all_generated_token_saving"]
            ),
            "pooled_stop_accuracy": 1.0
            - float(pooled["false_stop_rate_given_stop"]),
            "pooled_stop_coverage": float(pooled["stop_rate"]),
            "pooled_overall_accuracy": float(pooled["accuracy"]),
            "macro_token_saving": float(
                macro["all_generated_token_saving"]
            ),
            "macro_stop_accuracy": 1.0
            - float(macro["false_stop_rate_given_stop"]),
            "macro_stop_coverage": float(macro["stop_rate"]),
            "macro_overall_accuracy": float(macro["accuracy"]),
            "harm": int(pooled["harm"]),
            "rescue": int(pooled["rescue"]),
        }
    return trajectory_rows, baselines


def write_csv(
    trajectory: Sequence[Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
) -> None:
    rows: list[dict[str, Any]] = [
        {"method": "strict_consensus", **dict(row)} for row in trajectory
    ]
    for method, row in baselines.items():
        rows.append({"method": method, "window": "", **dict(row)})
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    path = OUTPUT_DIR / "consensus_window_vs_related_work.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def marginal_efficiency_rows(
    trajectory: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Finite-difference estimates of -d(saving)/d(stop accuracy).

    ``raw`` is the adjacent transition from w-1 to w. ``local`` spans two
    windows on either side of w, which suppresses single-window grading noise.
    Undefined values mean accuracy did not increase over that transition.
    """

    rows: list[dict[str, Any]] = []
    for view in ("pooled", "macro"):
        for left, right in zip(trajectory, trajectory[1:]):
            saving_lost = 100.0 * (
                float(left[f"{view}_token_saving"])
                - float(right[f"{view}_token_saving"])
            )
            accuracy_gained = 100.0 * (
                float(right[f"{view}_stop_accuracy"])
                - float(left[f"{view}_stop_accuracy"])
            )
            rows.append(
                {
                    "view": view,
                    "estimate": "adjacent",
                    "window": int(right["window"]),
                    "window_from": int(left["window"]),
                    "window_to": int(right["window"]),
                    "saving_lost_pp": saving_lost,
                    "stop_accuracy_gained_pp": accuracy_gained,
                    "saving_cost_per_accuracy_pp": (
                        saving_lost / accuracy_gained
                        if accuracy_gained > 0
                        else None
                    ),
                }
            )
        for index in range(2, len(trajectory) - 2):
            left = trajectory[index - 2]
            center = trajectory[index]
            right = trajectory[index + 2]
            saving_lost = 100.0 * (
                float(left[f"{view}_token_saving"])
                - float(right[f"{view}_token_saving"])
            )
            accuracy_gained = 100.0 * (
                float(right[f"{view}_stop_accuracy"])
                - float(left[f"{view}_stop_accuracy"])
            )
            rows.append(
                {
                    "view": view,
                    "estimate": "local_w_minus_2_to_w_plus_2",
                    "window": int(center["window"]),
                    "window_from": int(left["window"]),
                    "window_to": int(right["window"]),
                    "saving_lost_pp": saving_lost,
                    "stop_accuracy_gained_pp": accuracy_gained,
                    "saving_cost_per_accuracy_pp": (
                        saving_lost / accuracy_gained
                        if accuracy_gained > 0
                        else None
                    ),
                }
            )
    return rows


def write_marginal_efficiency(
    trajectory: Sequence[Mapping[str, Any]],
) -> None:
    rows = marginal_efficiency_rows(trajectory)
    csv_path = OUTPUT_DIR / "consensus_window_marginal_efficiency.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    fig, axes = plt.subplots(1, 2, figsize=(11.7, 4.4), sharey=True)
    view_style = {
        "pooled": ("Pooled", DEER_COLOR),
        "macro": ("Environment macro", TJE_COLOR),
    }
    for axis, view in zip(axes, ("pooled", "macro")):
        title, color = view_style[view]
        adjacent = [
            row
            for row in rows
            if row["view"] == view and row["estimate"] == "adjacent"
        ]
        local = [
            row
            for row in rows
            if row["view"] == view
            and row["estimate"] == "local_w_minus_2_to_w_plus_2"
            and row["saving_cost_per_accuracy_pp"] is not None
        ]
        valid_adjacent = [
            row
            for row in adjacent
            if row["saving_cost_per_accuracy_pp"] is not None
            and math.isfinite(float(row["saving_cost_per_accuracy_pp"]))
        ]
        invalid_adjacent = [
            row for row in adjacent if row["saving_cost_per_accuracy_pp"] is None
        ]
        axis.scatter(
            [row["window"] for row in valid_adjacent],
            [row["saving_cost_per_accuracy_pp"] for row in valid_adjacent],
            color="#8C9199",
            alpha=0.55,
            s=24,
            label="Adjacent Δ",
            zorder=2,
        )
        axis.plot(
            [row["window"] for row in local],
            [row["saving_cost_per_accuracy_pp"] for row in local],
            color=color,
            marker="o",
            markersize=4.2,
            linewidth=2.2,
            label="Local trend (w±2)",
            zorder=3,
        )
        if invalid_adjacent:
            axis.scatter(
                [row["window"] for row in invalid_adjacent],
                [38.0] * len(invalid_adjacent),
                marker="x",
                color="#B23A3A",
                s=38,
                linewidth=1.5,
                label="No accuracy gain",
                zorder=4,
            )
        axis.axvspan(16.5, 30.5, color="#B23A3A", alpha=0.045, linewidth=0)
        axis.text(
            23.5,
            31.5,
            "diminishing / noisy gains",
            ha="center",
            va="center",
            fontsize=8.5,
            color="#6A6E75",
        )
        axis.set_title(title)
        axis.set_xlabel("Window size w (transition ends at w)")
        axis.set_xlim(2.4, 30.6)
        axis.set_xticks(range(4, 31, 4))
        axis.set_yscale("log")
        axis.set_ylim(0.45, 45.0)
        axis.set_yticks([0.5, 1, 2, 5, 10, 20, 40])
        axis.set_yticklabels(["0.5", "1", "2", "5", "10", "20", "40"])
        axis.grid(which="both", color="#C8CBD0", alpha=0.42, linewidth=0.7)
        axis.legend(frameon=False, loc="upper left")
    axes[0].set_ylabel(
        "Token-saving loss per +1 pp stop-accuracy gain\n"
        r"$-\Delta S / \Delta A$ (lower is better)"
    )
    fig.suptitle(
        "Marginal cost of increasing strict-consensus persistence",
        fontsize=13.0,
        fontweight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Raw adjacent differences are shown in gray; the colored trend spans "
        "w−2 to w+2 to reduce single-window noise.",
        ha="center",
        fontsize=8.7,
        color="#55585D",
    )
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.18, top=0.85, wspace=0.12)
    stem = OUTPUT_DIR / "consensus_window_marginal_efficiency"
    fig.savefig(stem.with_suffix(".png"), dpi=240, bbox_inches="tight")
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_view(
    trajectory: Sequence[Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
    *,
    view: str,
    title: str,
) -> None:
    windows = np.asarray([int(row["window"]) for row in trajectory])
    saving = 100 * np.asarray(
        [float(row[f"{view}_token_saving"]) for row in trajectory]
    )
    stop_accuracy = 100 * np.asarray(
        [float(row[f"{view}_stop_accuracy"]) for row in trajectory]
    )

    fig = plt.figure(figsize=(12.4, 4.65))
    grid = fig.add_gridspec(1, 2, width_ratios=(2.15, 1.0), wspace=0.46)
    ax_saving = fig.add_subplot(grid[0, 0])
    ax_accuracy = ax_saving.twinx()
    ax_tradeoff = fig.add_subplot(grid[0, 1])

    saving_line = ax_saving.plot(
        windows,
        saving,
        color=SAVING_COLOR,
        marker="o",
        markersize=4.2,
        linewidth=2.2,
        label="Consensus token saving",
    )[0]
    accuracy_line = ax_accuracy.plot(
        windows,
        stop_accuracy,
        color=ACCURACY_COLOR,
        marker="s",
        markersize=4.0,
        linewidth=2.2,
        label="Consensus stop accuracy",
    )[0]
    ax_saving.set_xlim(float(windows.min()) - 0.4, float(windows.max()) + 0.4)
    x_ticks = list(range(int(windows.min()), int(windows.max()) + 1, 2))
    if int(windows.max()) not in x_ticks:
        x_ticks.append(int(windows.max()))
    ax_saving.set_xticks(x_ticks)
    ax_saving.set_xlabel("Strict unanimous window size")
    ax_saving.set_ylabel("Generated-output token saving (%)", color=SAVING_COLOR)
    ax_accuracy.set_ylabel("Accuracy among actual stops (%)", color=ACCURACY_COLOR)
    ax_saving.tick_params(axis="y", colors=SAVING_COLOR)
    ax_accuracy.tick_params(axis="y", colors=ACCURACY_COLOR)
    ax_saving.grid(axis="both", color="#C8CBD0", alpha=0.42, linewidth=0.7)
    ax_saving.spines["left"].set_color(SAVING_COLOR)
    ax_accuracy.spines["right"].set_color(ACCURACY_COLOR)
    ax_saving.legend(
        [saving_line, accuracy_line],
        [saving_line.get_label(), accuracy_line.get_label()],
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=2,
        frameon=False,
        borderaxespad=0.0,
    )

    ax_tradeoff.plot(
        saving,
        stop_accuracy,
        color=CONSENSUS_COLOR,
        linewidth=1.7,
        alpha=0.8,
        zorder=1,
    )
    ax_tradeoff.scatter(
        saving,
        stop_accuracy,
        c=windows,
        cmap="viridis",
        s=29,
        edgecolor="white",
        linewidth=0.55,
        zorder=2,
    )
    label_windows = (
        {2, 4, 6, 8, 12, 30}
        if view == "macro"
        else {2, 4, 6, 8, 10, 12, 16, 30}
    )
    for window, x, y in zip(windows, saving, stop_accuracy):
        if window in label_windows:
            offset = (4, 3)
            if view == "macro" and window == 30:
                offset = (-6, 8)
            ax_tradeoff.annotate(
                f"w={window}",
                (x, y),
                xytext=offset,
                textcoords="offset points",
                fontsize=7.5,
                color=CONSENSUS_COLOR,
            )

    for method, marker, color in (
        ("DEER", "*", DEER_COLOR),
        ("TJE", "D", TJE_COLOR),
    ):
        row = baselines[method]
        x = 100 * float(row[f"{view}_token_saving"])
        y = 100 * float(row[f"{view}_stop_accuracy"])
        ax_tradeoff.scatter(
            [x],
            [y],
            marker=marker,
            s=135 if method == "DEER" else 64,
            color=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=4,
            label=method,
        )
        ax_tradeoff.annotate(
            method,
            (x, y),
            xytext=(8, 12) if view == "macro" and method == "TJE" else (6, 4),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold",
            color=color,
        )
    ax_tradeoff.set_xlabel("Generated-output token saving (%)")
    ax_tradeoff.set_title("Accuracy–saving operating points")
    ax_tradeoff.grid(color="#C8CBD0", alpha=0.42, linewidth=0.7)
    x_values = [
        *saving,
        *[
            100 * float(row[f"{view}_token_saving"])
            for row in baselines.values()
        ],
    ]
    y_values = [
        *stop_accuracy,
        *[
            100 * float(row[f"{view}_stop_accuracy"])
            for row in baselines.values()
        ],
    ]
    ax_tradeoff.set_xlim(min(x_values) - 4.0, max(x_values) + 7.0)
    ax_tradeoff.set_ylim(min(y_values) - 3.0, max(y_values) + 3.0)

    fig.suptitle(title, fontsize=12.5, fontweight="bold", y=0.97)
    fig.subplots_adjust(left=0.07, right=0.96, bottom=0.18, top=0.86)
    fig.text(
        0.5,
        0.035,
        "Token saving includes main output through stop and consumed probe outputs; "
        "prompt/prefill cost is excluded.",
        ha="center",
        fontsize=8.7,
        color="#55585D",
    )
    stem = OUTPUT_DIR / f"consensus_window_vs_related_work_{view}"
    fig.savefig(stem.with_suffix(".png"), dpi=240, bbox_inches="tight")
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trajectory, baselines = collect()
    write_csv(trajectory, baselines)
    write_marginal_efficiency(trajectory)
    plot_view(
        trajectory,
        baselines,
        view="pooled",
        title="Pooled comparison (2,736 trajectories)",
    )
    plot_view(
        trajectory,
        baselines,
        view="macro",
        title="Environment-macro comparison (18 environments)",
    )
    print(f"Wrote comparison figures and CSV to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
