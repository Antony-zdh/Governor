#!/usr/bin/env python3
"""Generate the train/validation sweep figure used by the roadmap report."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


FC_DIR = Path(__file__).resolve().parents[1]
RESULT_DIR = FC_DIR / "results/stage10_rule_sweep"
OUT = Path(__file__).resolve().parent / "figures/f6_train_validation_sweep.png"
FUNNEL_DIR = FC_DIR / "results/stage10_rule_funnel_v2"
FUNNEL_OUT = Path(__file__).resolve().parent / "figures/f7_funnel_qwen_tradeoff.png"


def make_train_validation() -> None:
    train = pd.read_csv(RESULT_DIR / "sweep_train.csv")
    validation = pd.read_csv(RESULT_DIR / "sweep_validation.csv")
    selected = json.loads((RESULT_DIR / "selected_configs.json").read_text())

    vanilla = {
        "train": {"accuracy": 0.8233333333333334, "tokens": 2231.2266666666665},
        "validation": {
            "accuracy": 0.801980198019802,
            "tokens": 2425.930693069307,
        },
    }
    colors = {
        "conservative": "#2f855a",
        "balanced": "#805ad5",
        "aggressive": "#c53030",
    }

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True, sharey=True)
    for ax, (name, frame) in zip(
        axes, [("train", train), ("validation", validation)]
    ):
        ax.scatter(
            frame["avg_total_generated_tokens"],
            frame["overall_accuracy"],
            s=11,
            alpha=0.32,
            color="#2b6cb0",
            label="all candidates",
        )
        ax.scatter(
            [vanilla[name]["tokens"]],
            [vanilla[name]["accuracy"]],
            marker="*",
            s=150,
            color="#dd6b20",
            label="vanilla",
            zorder=5,
        )
        for point, config in selected.items():
            config_id = config["config_id"]
            row = frame.loc[frame["config_id"] == config_id].iloc[0]
            ax.scatter(
                [row["avg_total_generated_tokens"]],
                [row["overall_accuracy"]],
                s=75,
                color=colors[point],
                label=point,
                zorder=6,
            )
        ax.set_title(name.capitalize())
        ax.set_xlabel("Average total generated tokens")
        ax.grid(alpha=0.22)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Accuracy")
    handles, labels = axes[1].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    axes[1].legend(
        by_label.values(), by_label.keys(), frameon=False, fontsize=8
    )
    fig.suptitle("Rule sweep: train and validation", fontsize=15)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(OUT)


def make_funnel_tradeoff() -> None:
    round1 = pd.read_csv(FUNNEL_DIR / "round1_train_candidates.csv")
    round2 = pd.read_csv(FUNNEL_DIR / "round2_validation_candidates.csv")
    finalists = pd.read_csv(FUNNEL_DIR / "round3_finalists.csv")
    qwen = pd.read_csv(FUNNEL_DIR / "round4_qwen_simple32_results.csv")
    baselines = pd.read_csv(FUNNEL_DIR / "qwen_simple32_baselines.csv")

    stages = [
        ("Train", round1),
        ("Validation", round2),
        ("Validation-2", finalists),
    ]
    bands = ["conservative", "balanced", "exploratory"]
    colors = {
        "conservative": "#2f855a",
        "balanced": "#805ad5",
        "exploratory": "#c53030",
    }

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    x = range(len(stages))
    bottom = [0] * len(stages)
    for band in bands:
        values = [
            int(frame["risk_band"].eq(band).sum()) for _, frame in stages
        ]
        axes[0].bar(
            x,
            values,
            bottom=bottom,
            color=colors[band],
            label=band,
            alpha=0.88,
        )
        bottom = [a + b for a, b in zip(bottom, values)]
    axes[0].set_xticks(list(x), [name for name, _ in stages])
    axes[0].set_ylabel("Candidates carried forward")
    axes[0].set_title("Expanded candidate funnel")
    axes[0].spines[["top", "right"]].set_visible(False)
    axes[0].grid(axis="y", alpha=0.2)
    axes[0].legend(frameon=False, fontsize=8)

    vanilla = baselines.loc[
        baselines["operating_point"] == "vanilla"
    ].iloc[0]
    vanilla_tokens = float(vanilla["avg_total_generated_tokens"])
    qwen = qwen.copy()
    qwen["saving"] = (
        1 - qwen["avg_total_generated_tokens"] / vanilla_tokens
    )
    scatter = axes[1].scatter(
        qwen["saving"] * 100,
        qwen["false_stop_rate"] * 100,
        c=qwen["drop_qwen"] * 100,
        cmap="RdYlGn_r",
        vmin=0,
        vmax=max(8.0, float(qwen["drop_qwen"].max() * 100)),
        s=42,
        alpha=0.78,
        edgecolors="white",
        linewidths=0.5,
    )
    recommended_id = (
        "hist_w5_mv5_s1.0_level768-2048_swany_span0_"
        "cert1_validschema"
    )
    recommended = qwen.loc[qwen["config_id"] == recommended_id].iloc[0]
    axes[1].scatter(
        [recommended["saving"] * 100],
        [recommended["false_stop_rate"] * 100],
        marker="*",
        s=220,
        color="#1a202c",
        label="recommended p5 level rule",
        zorder=5,
    )
    old = baselines.loc[
        baselines["operating_point"] == "stage7_conservative_v0"
    ].iloc[0]
    old_saving = 1 - float(old["avg_total_generated_tokens"]) / vanilla_tokens
    axes[1].scatter(
        [old_saving * 100],
        [float(old["false_stop_rate"]) * 100],
        marker="D",
        s=70,
        color="#3182ce",
        label="Stage-7 Conservative v0",
        zorder=5,
    )
    axes[1].set_xlabel("Qwen total-token saving (%)")
    axes[1].set_ylabel("Qwen false-stop rate (%)")
    axes[1].set_title("Matched Qwen@32: saving vs false-stop")
    axes[1].spines[["top", "right"]].set_visible(False)
    axes[1].grid(alpha=0.2)
    axes[1].legend(frameon=False, fontsize=8)
    colorbar = fig.colorbar(scatter, ax=axes[1], pad=0.02)
    colorbar.set_label("Accuracy drop (pp)")

    fig.tight_layout()
    FUNNEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FUNNEL_OUT, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(FUNNEL_OUT)


def main() -> None:
    make_train_validation()
    make_funnel_tradeoff()


if __name__ == "__main__":
    main()
