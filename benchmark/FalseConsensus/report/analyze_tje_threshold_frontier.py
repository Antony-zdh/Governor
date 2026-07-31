#!/usr/bin/env python3
"""CPU replay and plots for the TJE top-1..top-6 threshold bank."""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.related_work import (  # noqa: E402
    common,
    metrics,
    model_map,
    tje,
)
from benchmark.FalseConsensus.related_work.tje_threshold_readout_bank import (  # noqa: E402
    TOP_K_THRESHOLDS,
)


BANK = (
    REPO
    / "benchmark/FalseConsensus/results/related_work/"
    "tje_threshold_readout_bank_top1_6"
)
AGGREGATE = BANK / "aggregate"
FIGURES = REPO / "benchmark/FalseConsensus/report/figures"
SPLIT_MANIFEST = (
    REPO
    / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
)
SCOPE_PREFIX = {"full": "development", "test": "confirmation"}


@lru_cache(maxsize=100_000)
def answers_equal(answer: str, target: str) -> bool:
    return bool(common.real_answers_equal(answer, target))


def iter_archive(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main_run(
    scope: str, model_key: str, benchmark: str, seed: int
) -> Path:
    info = model_map.model_info(model_key)
    return (
        REPO
        / "benchmark/FalseConsensus/results/governor_v2"
        / (
            f"{SCOPE_PREFIX[scope]}__{info['slug']}__"
            f"{benchmark}__seed_{seed}"
        )
        / "main"
    )


def threshold_replay(
    payload: dict[str, Any],
    trajectory: dict[str, Any],
    *,
    top_k: int,
    split: str,
) -> dict[str, Any]:
    decision = payload["top_k_decisions"][str(top_k)]
    stop_id = decision.get("stop_trigger_id")
    triggers: list[dict[str, Any]] = []
    for source in payload["confidence_triggers"]:
        trigger_id = int(source["trigger_id"])
        if stop_id is not None and trigger_id > int(stop_id):
            break
        row = dict(source)
        row["meets_threshold"] = (
            stop_id is not None and trigger_id == int(stop_id)
        )
        triggers.append(row)
    readout = None
    if stop_id is not None:
        matches = [
            row
            for row in payload["readouts"]
            if int(row["at_trigger_id"]) == int(stop_id)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected one readout for stop trigger {stop_id}, "
                f"observed {len(matches)}"
            )
        readout = matches[0]
    replayed = tje.replay(
        trajectory,
        triggers,
        threshold_label=TOP_K_THRESHOLDS[top_k],
        readout=readout,
        answers_equal_target_fn=answers_equal,
        split=split,
        include_think_close=True,
    )
    row = metrics.per_problem_metric(replayed)
    row.update(
        {
            "policy": f"top_{top_k}",
            "top_k": top_k,
            "threshold_label": TOP_K_THRESHOLDS[top_k],
        }
    )
    return row


def load_rows() -> list[dict[str, Any]]:
    split_map = common.load_split_map(SPLIT_MANIFEST)
    rows: list[dict[str, Any]] = []
    observed_problems = 0
    for scope in ("full", "test"):
        for archive in sorted((BANK / scope).glob("*/readouts.jsonl.gz")):
            model_key, benchmark, seed_text = archive.parent.name.split("__")
            seed = int(seed_text.removeprefix("seed_"))
            trajectories = main_run(
                scope, model_key, benchmark, seed
            ) / "traj"
            for payload in iter_archive(archive):
                problem_id = int(payload["problem_id"])
                trajectory = common.load_trajectory(
                    trajectories / f"problem_{problem_id}.json"
                )
                split = (
                    split_map[(benchmark, problem_id)]
                    if scope == "full"
                    else "test"
                )
                observed_problems += 1
                for top_k in range(1, 7):
                    row = threshold_replay(
                        payload,
                        trajectory,
                        top_k=top_k,
                        split=split,
                    )
                    row.update(
                        {
                            "scope": scope,
                            "model_key": model_key,
                            "benchmark": benchmark,
                            "seed": seed,
                        }
                    )
                    rows.append(row)
    if observed_problems != 3420:
        raise ValueError(
            f"expected 3420 trajectories, observed {observed_problems}"
        )
    if len(rows) != 3420 * 6:
        raise ValueError(f"wrong policy-row count: {len(rows)}")
    return rows


def write_problem_rows(rows: list[dict[str, Any]]) -> None:
    path = AGGREGATE / "replay_rows.jsonl.gz"
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, mtime=0
        ) as out:
            for row in rows:
                out.write(
                    (json.dumps(row, sort_keys=True) + "\n").encode(
                        "utf-8"
                    )
                )


def summarize_groups(
    rows: list[dict[str, Any]], keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    output: list[dict[str, Any]] = []
    for identity, members in sorted(groups.items()):
        summary = metrics.aggregate(members)
        output.append(
            {
                **dict(zip(keys, identity)),
                "threshold_label": members[0]["threshold_label"],
                **summary,
            }
        )
    return output


def macro_frontier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for split in ("train", "dev", "test"):
        for top_k in range(1, 7):
            selected = [
                row
                for row in rows
                if row["split"] == split and row["top_k"] == top_k
            ]
            pooled = metrics.aggregate(selected)
            output.append(
                {
                    "scope": split,
                    "aggregation": "pooled",
                    "top_k": top_k,
                    "threshold_label": TOP_K_THRESHOLDS[top_k],
                    "n": pooled["n"],
                    "accuracy": pooled["accuracy"],
                    "baseline_accuracy": pooled["baseline_accuracy"],
                    "accuracy_drop_pp": -pooled["accuracy_diff_pp"],
                    "token_saving_pct": 100.0
                    * pooled["all_generated_token_saving_fraction"],
                    "stop_rate": pooled["stop_rate"],
                    "avg_all_generated_tokens": pooled[
                        "avg_all_generated_tokens"
                    ],
                    "avg_baseline_all_generated_tokens": pooled[
                        "avg_baseline_all_generated_tokens"
                    ],
                }
            )
            cells = []
            for model_key in ("deepseek", "qwen3"):
                for benchmark in model_map.BENCHMARKS:
                    cell_rows = [
                        row
                        for row in selected
                        if row["model_key"] == model_key
                        and row["benchmark"] == benchmark
                    ]
                    cell = metrics.aggregate(cell_rows)
                    cells.append(
                        (
                            -cell["accuracy_diff_pp"],
                            100.0
                            * cell[
                                "all_generated_token_saving_fraction"
                            ],
                        )
                    )
            output.append(
                {
                    "scope": split,
                    "aggregation": "model_benchmark_macro",
                    "top_k": top_k,
                    "threshold_label": TOP_K_THRESHOLDS[top_k],
                    "n": len(selected),
                    "accuracy": pooled["accuracy"],
                    "baseline_accuracy": pooled["baseline_accuracy"],
                    "accuracy_drop_pp": sum(cell[0] for cell in cells)
                    / len(cells),
                    "token_saving_pct": sum(cell[1] for cell in cells)
                    / len(cells),
                    "stop_rate": pooled["stop_rate"],
                    "avg_all_generated_tokens": pooled[
                        "avg_all_generated_tokens"
                    ],
                    "avg_baseline_all_generated_tokens": pooled[
                        "avg_baseline_all_generated_tokens"
                    ],
                }
            )
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_frontier(frontier: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.5))
    for axis, split in zip(axes, ("train", "dev")):
        points = [
            row
            for row in frontier
            if row["scope"] == split
            and row["aggregation"] == "model_benchmark_macro"
        ]
        points.sort(key=lambda row: int(row["top_k"]))
        axis.plot(
            [float(row["accuracy_drop_pp"]) for row in points],
            [float(row["token_saving_pct"]) for row in points],
            color="#ea580c",
            linewidth=2.4,
            marker="*",
            markersize=11,
            markeredgecolor="white",
            markeredgewidth=0.7,
        )
        # Show every operating point, while labeling only the transition,
        # the next threshold, and the endpoint.  Top-2 through top-6 cluster
        # tightly, so labeling each one obscures the curve.
        label_offsets = {1: (6, 6), 2: (5, -17), 6: (-12, 10)}
        for row in points:
            top_k = int(row["top_k"])
            if top_k not in label_offsets:
                continue
            axis.annotate(
                f"top-{top_k}",
                (
                    float(row["accuracy_drop_pp"]),
                    float(row["token_saving_pct"]),
                ),
                xytext=label_offsets[top_k],
                textcoords="offset points",
                fontsize=8.5,
            )
        axis.axvline(0, color="#64748b", linewidth=0.8, alpha=0.55)
        axis.axhline(0, color="#64748b", linewidth=0.8, alpha=0.55)
        axis.grid(True, color="#cbd5e1", linewidth=0.6, alpha=0.5)
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
        axis.set_title(split.title())
        axis.set_xlabel("Accuracy drop vs Full (pp) — lower is better")
        axis.set_ylabel(
            "All-generated-token saving (%) — higher is better"
        )
    fig.suptitle(
        "Think Just Enough: self-assessed confidence threshold frontier",
        fontsize=15,
        fontweight="medium",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        FIGURES / "tje_threshold_frontier_train_dev.png",
        dpi=240,
        bbox_inches="tight",
    )
    fig.savefig(
        FIGURES / "tje_threshold_frontier_train_dev.pdf",
        bbox_inches="tight",
    )
    plt.close(fig)


def main() -> None:
    AGGREGATE.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    write_problem_rows(rows)
    environment = summarize_groups(
        rows,
        (
            "scope",
            "split",
            "model_key",
            "benchmark",
            "seed",
            "top_k",
        ),
    )
    frontier = macro_frontier(rows)
    write_csv(AGGREGATE / "environment_split.csv", environment)
    write_csv(AGGREGATE / "frontier.csv", frontier)
    plot_frontier(frontier)
    print(json.dumps(frontier, indent=2))


if __name__ == "__main__":
    main()
