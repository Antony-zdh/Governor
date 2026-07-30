#!/usr/bin/env python3
"""Generate compact, audit-oriented figures for FINDING_EXPERIMENT_MAP.md.

The values below are copied from fixed text/JSON artifacts cited in the
appendix. This script intentionally does not read held-out per-problem data.
"""

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUT = Path(__file__).resolve().parent / "figures" / "finding_map_appendix"
OUT.mkdir(parents=True, exist_ok=True)
REPO = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads(
    (
        REPO
        / "benchmark"
        / "FalseConsensus"
        / "results"
        / "appendix_evidence_upgrade"
        / "summary.json"
    ).read_text()
)

COLORS = {
    "blue": "#2878B5",
    "orange": "#F28E2B",
    "green": "#2A9D8F",
    "red": "#D9534F",
    "purple": "#7E57C2",
    "gray": "#6B7280",
}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight")
    plt.close(fig)


def sweep_distribution() -> None:
    labels = ["min", "p1", "p5", "p25", "median"]
    dev = [1.852, 3.370, 4.259, 10.722, 20.074]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(7.7, 3.5))
    ax.plot(
        x, dev, marker="o", linewidth=2.2, color=COLORS["blue"],
        label="Development selection (train+dev, 36 cells/rule)"
    )
    ax.axhline(1.5, color=COLORS["red"], linestyle="--", linewidth=1.4,
               label="conservative per-model gate (1.5 pp)")
    for xi, value in zip(x, dev):
        ax.annotate(f"{value:.2f}", (xi, value), xytext=(0, 7),
                    textcoords="offset points", ha="center")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Worst-case per-model accuracy drop (pp)")
    ax.set_title("Development worst-case per-model drop over 17,712 rules")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, loc="upper left")
    save(fig, "a5_sweep_drop_distribution.png")


def direction_ratio() -> None:
    named_labels = ["Naive", "Conservative", "Balanced-\ngeneral", "Balanced-\nmath"]
    named_values = [35.17, 14.59, 15.00, 18.31]
    local_labels = ["w=3", "w=5", "w=8"]
    local_values = [33.44, 29.15, 19.70]
    strict_values = [33.44, 17.38, 9.43]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.55), sharey=True)
    x = np.arange(len(named_labels))
    bars = axes[0].bar(
        x, named_values,
        color=[COLORS["red"], COLORS["green"], COLORS["purple"], COLORS["blue"]],
        width=0.66,
    )
    axes[0].bar_label(bars, fmt="%.2f", padding=3)
    axes[0].set_xticks(x, named_labels)
    axes[0].set_title("Named Governor rules")

    x2 = np.arange(len(local_labels))
    width = 0.34
    bars_local = axes[1].bar(
        x2 - width / 2, local_values, width,
        color=COLORS["orange"], label="First local consensus\n(share >= 0.8)",
    )
    bars_strict = axes[1].bar(
        x2 + width / 2, strict_values, width,
        color=COLORS["gray"], label="First strict unanimous\nwindow",
    )
    axes[1].bar_label(bars_local, fmt="%.2f", padding=2, fontsize=8)
    axes[1].bar_label(bars_strict, fmt="%.2f", padding=2, fontsize=8)
    axes[1].set_xticks(x2, local_labels)
    axes[1].set_title("Consensus diagnostics")
    axes[1].legend(frameon=False, fontsize=8)

    for ax in axes:
        ax.axhline(1.0, color="#111827", linestyle="--", linewidth=1)
        ax.grid(axis="y", alpha=0.25)
        ax.set_ylim(0, 40)
    axes[0].set_ylabel("Harm count / rescue count")
    save(fig, "a7_direction_ratio.png")


def confirmation_summary() -> None:
    points_path = (
        REPO / "benchmark" / "FalseConsensus" / "results"
        / "appendix_evidence_upgrade" / "a8_strategy_points.csv"
    )
    with points_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9), sharex=True, sharey=True)
    panels = [
        (
            axes[0],
            "dev_worst_model_drop_pp",
            "dev_q20_total_token_saving",
            "dev_frontier",
            "Dev (same 2 models)",
            COLORS["blue"],
        ),
        (
            axes[1],
            "test_worst_model_drop_pp",
            "test_q20_total_token_saving",
            "test_frontier",
            "Held-out Test (same 2 models)",
            COLORS["orange"],
        ),
    ]
    for ax, x_key, y_key, frontier_key, title, color in panels:
        x = np.array([float(row[x_key]) for row in rows])
        y = 100 * np.array([float(row[y_key]) for row in rows])
        ax.scatter(x, y, s=5, alpha=0.12, color=color, linewidths=0)
        frontier = sorted(
            (
                (float(row[x_key]), 100 * float(row[y_key]))
                for row in rows
                if row[frontier_key].lower() == "true"
            ),
            key=lambda item: item[0],
        )
        ax.plot(
            [point[0] for point in frontier],
            [point[1] for point in frontier],
            color="#111827",
            linewidth=1.8,
            marker="o",
            markersize=2.8,
            label=f"Pareto frontier (n={len(frontier)})",
        )
        ax.axvline(1.5, color=COLORS["red"], linestyle="--", linewidth=1)
        ax.axhline(0, color=COLORS["gray"], linestyle=":", linewidth=1)
        ax.set_title(title)
        ax.set_xlabel("Worst per-model accuracy drop (pp; lower is better)")
        ax.grid(alpha=0.18)
        ax.legend(frameon=False, fontsize=8, loc="lower right")
    axes[0].set_ylabel("20th-percentile total-token saving (%)")
    axes[0].text(
        0.03, 0.04, "17,712 rules",
        transform=axes[0].transAxes, fontsize=9, color="#374151"
    )
    axes[1].text(
        0.03, 0.04, "r(drop Dev, Test) = 0.962",
        transform=axes[1].transAxes, fontsize=9, color="#374151"
    )
    save(fig, "a8_confirmation_gate.png")


def boundary_components() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.45))

    # Frozen, paired fast-path-only replay on Train and Dev.
    fast = EVIDENCE["fast_path_split_rows"]
    order = [("train", "Qwen3-8B"), ("train", "DeepSeek-7B"),
             ("dev", "Qwen3-8B"), ("dev", "DeepSeek-7B")]
    by_key = {(row["split"], row["model"]): row for row in fast}
    models = ["Train\nQwen", "Train\nDS", "Dev\nQwen", "Dev\nDS"]
    acc_delta = [by_key[key]["accuracy_delta_pp"] for key in order]
    saving_delta = [by_key[key]["token_saving_delta_pp"] for key in order]
    x = np.arange(len(models))
    width = 0.35
    bars1 = axes[0].bar(
        x - width / 2, acc_delta, width, label="Δ accuracy (pp)",
        color=COLORS["blue"]
    )
    bars2 = axes[0].bar(
        x + width / 2, saving_delta, width, label="Δ saving (pp)",
        color=COLORS["green"]
    )
    axes[0].axhline(0, color="#111827", linewidth=0.8)
    axes[0].bar_label(bars1, fmt="%+.2f", padding=2, fontsize=9)
    axes[0].bar_label(bars2, fmt="%+.2f", padding=2, fontsize=9)
    axes[0].set_xticks(x, models)
    axes[0].set_title("Fast-path-only vs frozen DEER")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_ylim(-1.0, 3.8)
    axes[0].grid(axis="y", alpha=0.22)

    # Online three-seed environment-macro.
    labels = ["Inspired", "Online DEER"]
    dacc = [-0.75, -2.71]
    saving = [34.2, 22.1]
    x2 = np.arange(len(labels))
    ax_left = axes[1]
    ax_right = ax_left.twinx()
    bars3 = ax_left.bar(
        x2 - width / 2, dacc, width, color=COLORS["orange"],
        label="Δ accuracy vs Full (pp)"
    )
    bars4 = ax_right.bar(
        x2 + width / 2, saving, width, color=COLORS["purple"],
        label="Fair saving (%)"
    )
    ax_left.axhline(0, color="#111827", linewidth=0.8)
    ax_left.bar_label(bars3, fmt="%+.2f", padding=2, fontsize=9)
    ax_right.bar_label(bars4, fmt="%.1f", padding=2, fontsize=9)
    ax_left.set_xticks(x2, labels)
    ax_left.set_ylabel("Δ accuracy (pp)")
    ax_right.set_ylabel("Fair saving (%)")
    ax_left.set_ylim(-4.0, 1.2)
    ax_right.set_ylim(0, 42)
    ax_left.set_title("Online Dev, 3-seed environment-macro")
    ax_left.grid(axis="y", alpha=0.22)
    handles = [bars3, bars4]
    ax_left.legend(handles, [h.get_label() for h in handles],
                   frameon=False, fontsize=8, loc="upper center")

    save(fig, "a11_a12_boundary_components.png")


def related_work_matched() -> None:
    dev_macro_path = (
        REPO / "benchmark" / "FalseConsensus" / "results"
        / "related_work" / "aggregate" / "dev_macro.csv"
    )
    with dev_macro_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    method_names = {
        "certaindex_mid_frozen": "CertaIndex",
        "deer_frozen": "DEER",
        "tje_frozen": "TJE",
    }
    points = []
    for row in rows:
        if row["method"] not in method_names:
            continue
        points.append(
            {
                "model": "Qwen" if row["model"] == "Qwen/Qwen3-8B" else "DeepSeek",
                "method": method_names[row["method"]],
                "drop": -float(row["accuracy_diff_pp"]),
                "saving": 100 * float(row["all_generated_token_saving_fraction"]),
                "kind": "Related work",
            }
        )
    for row in EVIDENCE["related_work"]["matched_governor_macro"]:
        points.append(
            {
                "model": "Qwen" if row["model"] == "Qwen3-8B" else "DeepSeek",
                "method": row["method"].replace("Governor ", "Gov. "),
                "drop": -float(row["accuracy_diff_pp"]),
                "saving": 100 * float(row["all_generated_saving_fraction"]),
                "kind": "Governor named rule",
            }
        )

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8), sharex=True, sharey=True)
    palette = {
        "CertaIndex": COLORS["red"],
        "DEER": COLORS["green"],
        "TJE": COLORS["purple"],
        "Gov. balanced-task-aware": COLORS["orange"],
        "Gov. conservative": COLORS["blue"],
        "Gov. naive": COLORS["gray"],
    }
    markers = {"Related work": "o", "Governor named rule": "s"}
    for ax, model in zip(axes, ("Qwen", "DeepSeek")):
        for point in [item for item in points if item["model"] == model]:
            ax.scatter(
                point["drop"], point["saving"], s=58,
                color=palette[point["method"]], marker=markers[point["kind"]],
                edgecolor="white", linewidth=0.7, zorder=3
            )
            ax.annotate(
                point["method"], (point["drop"], point["saving"]),
                xytext=(4, 4), textcoords="offset points", fontsize=7.5
            )
        ax.set_title(f"{model} Dev macro")
        ax.set_xlabel("Accuracy drop vs Full (pp; lower is better)")
        ax.grid(alpha=0.22)
    axes[0].set_ylabel("All-generated token saving (%)")
    axes[0].set_xlim(-2, 76)
    axes[0].set_ylim(-5, 96)
    save(fig, "a10_matched_methods.png")


if __name__ == "__main__":
    sweep_distribution()
    direction_ratio()
    confirmation_summary()
    related_work_matched()
    boundary_components()
