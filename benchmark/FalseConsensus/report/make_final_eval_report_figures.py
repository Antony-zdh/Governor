#!/usr/bin/env python3
"""Create figures for the three-seed DeepSeek final-evaluation report."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "benchmark/FalseConsensus/results/final_eval"
FIGURES = Path(__file__).resolve().parent / "figures"


def load_aggregate() -> dict[str, dict[str, str]]:
    path = RESULTS / "aggregate/model_seed_aggregate.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["method"]: row for row in csv.DictReader(handle)}


def make_pareto(rows: dict[str, dict[str, str]]) -> None:
    fig, ax = plt.subplots(figsize=(8.3, 4.7))
    ax.axhspan(-1.0, 1.0, color="#DCEAF7", alpha=0.7, label="accuracy gate: +/-1 pp")
    ax.axhline(0, color="#334155", linewidth=0.9)
    ax.axvline(0, color="#334155", linewidth=0.9)

    fixed = [
        ("fixed_budget_512", "B512"),
        ("fixed_budget_1024", "B1024"),
        ("fixed_budget_1536", "B1536"),
        ("fixed_budget_2048", "B2048"),
        ("fixed_budget_3072", "B3072"),
    ]
    fx = [100 * float(rows[key]["total_token_saving_mean"]) for key, _ in fixed]
    fy = [100 * float(rows[key]["accuracy_diff_vs_full_mean"]) for key, _ in fixed]
    ax.plot(fx, fy, color="#94A3B8", linewidth=1.2, zorder=2)
    ax.scatter(fx, fy, color="#64748B", marker="s", s=42, zorder=3)
    fixed_offsets = {
        "B512": (5, 4),
        "B1024": (5, 4),
        "B1536": (5, 4),
        "B2048": (5, 4),
        "B3072": (55, 25),
    }
    for x, y, (_, label) in zip(fx, fy, fixed):
        ax.annotate(
            label,
            (x, y),
            xytext=fixed_offsets[label],
            textcoords="offset points",
            fontsize=8,
            arrowprops=(
                {"arrowstyle": "-", "color": "#64748B", "linewidth": 0.7}
                if label == "B3072"
                else None
            ),
        )

    points = [
        ("full_generation", "Full", "#111827", "o"),
        ("conservative", "Conservative", "#C2410C", "o"),
        ("balanced_math", "Balanced-MATH", "#047857", "o"),
        ("dynasor_stop_logic_on_simple32", "Dynasor", "#7C3AED", "^"),
        ("naive_agreement", "Naive agreement", "#BE123C", "^"),
    ]
    offsets = {
        "Full": (-72, -38),
        "Conservative": (-12, 27),
        "Balanced-MATH": (30, -27),
        "Dynasor": (6, 6),
        "Naive agreement": (6, 6),
    }
    for key, label, color, marker in points:
        x = 100 * float(rows[key]["total_token_saving_mean"])
        y = 100 * float(rows[key]["accuracy_diff_vs_full_mean"])
        ax.scatter([x], [y], color=color, marker=marker, s=65, zorder=4)
        ax.annotate(
            label,
            (x, y),
            xytext=offsets[label],
            textcoords="offset points",
            fontsize=8.5,
            color=color,
            fontweight="semibold",
            arrowprops=(
                {"arrowstyle": "-", "color": color, "linewidth": 0.7}
                if label in {"Full", "Conservative", "Balanced-MATH"}
                else None
            ),
        )

    ax.set_xlim(-8, 82)
    ax.set_ylim(-43.5, 3.5)
    ax.set_xlabel("Total generated-token saving vs. Full (%)")
    ax.set_ylabel("Accuracy difference vs. Full (percentage points)")
    ax.set_title("Three-seed accuracy-compute trade-off")
    ax.grid(True, color="#E2E8F0", linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "f8_final_eval_pareto.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def load_factorial() -> dict[str, dict[str, tuple[float, float]]]:
    collected: dict[str, dict[str, list[float]]] = {}
    for seed in (43, 44, 45):
        path = (
            RESULTS
            / f"deepseek7b_math500/seed_{seed}/final_eval/"
            "factorial_component_mean_effects.csv"
        )
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                component = row["component"]
                for column in (
                    "accuracy_on_minus_off",
                    "mean_total_generated_tokens_on_minus_off",
                ):
                    collected.setdefault(component, {}).setdefault(column, []).append(
                        float(row[column])
                    )

    result: dict[str, dict[str, tuple[float, float]]] = {}
    for component, columns in collected.items():
        result[component] = {}
        for column, values in columns.items():
            result[component][column] = (float(np.mean(values)), float(np.std(values, ddof=1)))
    return result


def make_factorial(effects: dict[str, dict[str, tuple[float, float]]]) -> None:
    components = ["schema", "maturity", "certainty", "persistence"]
    labels = ["Schema", "Maturity", "Certainty", "Persistence"]
    colors = ["#0891B2", "#2563EB", "#7C3AED", "#C2410C"]
    y = np.arange(len(components))

    acc_mean = [
        100 * effects[c]["accuracy_on_minus_off"][0] for c in components
    ]
    acc_sd = [100 * effects[c]["accuracy_on_minus_off"][1] for c in components]
    tok_mean = [
        effects[c]["mean_total_generated_tokens_on_minus_off"][0] for c in components
    ]
    tok_sd = [
        effects[c]["mean_total_generated_tokens_on_minus_off"][1] for c in components
    ]

    fig, axes = plt.subplots(1, 2, figsize=(8.3, 4.4), sharey=True)
    axes[0].barh(y, acc_mean, xerr=acc_sd, color=colors, alpha=0.9, capsize=3)
    axes[1].barh(y, tok_mean, xerr=tok_sd, color=colors, alpha=0.9, capsize=3)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Accuracy effect: on - off (pp)")
    axes[1].set_xlabel("Generated-token effect: on - off")
    axes[0].set_title("Safety benefit")
    axes[1].set_title("Compute cost")
    for axis in axes:
        axis.axvline(0, color="#334155", linewidth=0.8)
        axis.grid(True, axis="x", color="#E2E8F0", linewidth=0.7)
        axis.spines[["top", "right"]].set_visible(False)
    for i, value in enumerate(acc_mean):
        axes[0].text(value + 0.15, i, f"{value:.2f}", va="center", fontsize=8)
    for i, value in enumerate(tok_mean):
        axes[1].text(value + 12, i, f"{value:.0f}", va="center", fontsize=8)
    fig.suptitle("Mean marginal component effects across three seeds", y=1.01)
    fig.tight_layout()
    fig.savefig(FIGURES / "f9_final_eval_factorial.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    aggregate = load_aggregate()
    make_pareto(aggregate)
    make_factorial(load_factorial())


if __name__ == "__main__":
    main()
