#!/usr/bin/env python3
"""Analyze and plot the threshold frontier of the DEER cap-30 bank.

Deployment replay:
  * probe at the first 30 whole-word Wait positions;
  * accept the first non-empty answer whose confidence is strictly above tau;
  * directly submit that answer (no formal readout);
  * if no answer is accepted, retain the frozen full answer;
  * charge every generated probe-output token observed through the decision.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
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

from benchmark.FalseConsensus.related_work import model_map  # noqa: E402
from benchmark.FalseConsensus.related_work.common import real_answers_equal  # noqa: E402


BANK = (
    REPO
    / "benchmark/FalseConsensus/results/related_work/"
    "deer_confidence_bank_cap30"
)
RESULTS = BANK / "aggregate"
FIGURES = REPO / "benchmark/FalseConsensus/report/figures"

THRESHOLDS = (
    0.50,
    0.60,
    0.70,
    0.80,
    0.85,
    0.90,
    0.925,
    0.95,
    0.96,
    0.97,
    0.975,
    0.98,
    0.985,
    0.99,
    0.9925,
    0.995,
    0.996,
    0.997,
    0.998,
    0.999,
    0.9995,
    0.9999,
    0.99995,
    0.99999,
    0.999995,
    0.999999,
    0.9999995,
    0.9999999,
    0.99999999,
    1.0,
)
TABLE_THRESHOLDS = (0.95, 0.99, 0.995, 0.999, 0.99999, 0.999999, 1.0)
PROBE_CAPS = (10, 20, 30)
SCOPE_PREFIX = {"full": "development", "test": "confirmation"}


def normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


@lru_cache(maxsize=100_000)
def correct(answer: str, target: str) -> bool:
    return bool(real_answers_equal(answer, target))


def iter_archive(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_development_splits() -> dict[tuple[str, str, int, int], str]:
    splits: dict[tuple[str, str, int, int], str] = {}
    replay_root = BANK.parent / "full" / "_replay"
    for directory in sorted(replay_root.glob("*__deer")):
        path = directory / "replay_rows.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = (
                str(row["model"]),
                str(row["dataset"]),
                int(row["base_seed"]),
                int(row["problem_id"]),
            )
            splits[key] = str(row["split"])
    if not splits:
        raise ValueError("no train/dev split assignments found")
    return splits


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    development_splits = load_development_splits()
    for scope in ("full", "test"):
        for archive in sorted((BANK / scope).glob("*/trials.jsonl.gz")):
            environment = archive.parent.name
            model_key, benchmark, seed_text = environment.split("__")
            seed = int(seed_text.removeprefix("seed_"))
            info = model_map.model_info(model_key)
            main = (
                REPO
                / "benchmark/FalseConsensus/results/governor_v2"
                / (
                    f"{SCOPE_PREFIX[scope]}__{info['slug']}__"
                    f"{benchmark}__seed_{seed}"
                )
                / "main/traj"
            )
            for payload in iter_archive(archive):
                problem_id = int(payload["problem_id"])
                identity = (
                    str(payload["model"]),
                    str(payload["dataset"]),
                    int(payload["base_seed"]),
                    problem_id,
                )
                split = (
                    development_splits[identity]
                    if scope == "full"
                    else "test"
                )
                trajectory = json.loads(
                    (main / f"problem_{problem_id}.json").read_text(
                        encoding="utf-8"
                    )
                )
                trials = sorted(
                    payload["trials"], key=lambda row: int(row["candidate_id"])
                )
                rows.append(
                    {
                        "scope": scope,
                        "split": split,
                        "environment": environment,
                        "model_key": model_key,
                        "benchmark": benchmark,
                        "seed": seed,
                        "problem_id": problem_id,
                        "target": normalized(trajectory["target"]),
                        "baseline_correct": bool(trajectory["final_correct"]),
                        "baseline_tokens": int(
                            payload["main_token_count_recorded"]
                        ),
                        "trials": trials,
                    }
                )
    if len(rows) != 3420:
        raise ValueError(f"expected 3420 trajectories, observed {len(rows)}")
    return rows


def replay(
    row: dict[str, Any], threshold: float, max_probes: int
) -> dict[str, Any]:
    probe_tokens = 0
    probes = 0
    accepted: dict[str, Any] | None = None
    for trial in row["trials"][:max_probes]:
        probes += 1
        probe_tokens += int(trial.get("trial_out_tokens", 0))
        answer = normalized(trial.get("trial_answer"))
        confidence = float(trial["confidence"])
        if answer and confidence > threshold:
            accepted = trial
            break

    if accepted is None:
        method_correct = row["baseline_correct"]
        method_tokens = row["baseline_tokens"] + probe_tokens
        stop_correct: bool | None = None
    else:
        answer = normalized(accepted["trial_answer"])
        method_correct = correct(answer, row["target"])
        method_tokens = int(accepted["token_position"]) + probe_tokens
        stop_correct = method_correct

    return {
        "method_correct": bool(method_correct),
        "method_tokens": int(method_tokens),
        "stopped": accepted is not None,
        "stop_correct": stop_correct,
        "probes": probes,
        "harm": bool(row["baseline_correct"] and not method_correct),
        "rescue": bool(not row["baseline_correct"] and method_correct),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, float | int]:
    n = len(records)
    stopped = [record for record in records if record["stopped"]]
    baseline_correct = sum(record["baseline_correct"] for record in records)
    method_correct = sum(record["method_correct"] for record in records)
    baseline_tokens = sum(record["baseline_tokens"] for record in records)
    method_tokens = sum(record["method_tokens"] for record in records)
    harms = sum(record["harm"] for record in records)
    rescues = sum(record["rescue"] for record in records)
    stop_correct = sum(bool(record["stop_correct"]) for record in stopped)
    return {
        "n": n,
        "baseline_accuracy_pct": 100.0 * baseline_correct / n,
        "accuracy_pct": 100.0 * method_correct / n,
        "accuracy_drop_pp": 100.0 * (baseline_correct - method_correct) / n,
        "token_saving_pct": 100.0 * (baseline_tokens - method_tokens)
        / baseline_tokens,
        "stop_rate_pct": 100.0 * len(stopped) / n,
        "early_stop_accuracy_pct": (
            100.0 * stop_correct / len(stopped) if stopped else math.nan
        ),
        "false_stop_ratio_pct": (
            100.0 * (len(stopped) - stop_correct) / len(stopped)
            if stopped
            else math.nan
        ),
        "avg_probes": sum(record["probes"] for record in records) / n,
        "harm_count": harms,
        "rescue_count": rescues,
        "harm_rescue_ratio": harms / rescues if rescues else math.inf,
    }


def analyze(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for max_probes in PROBE_CAPS:
        for threshold in THRESHOLDS:
            evaluated: list[dict[str, Any]] = []
            for row in rows:
                evaluated.append(
                    {**row, **replay(row, threshold, max_probes)}
                )

            for scope in ("full", "test", "all", "train", "dev"):
                if scope == "all":
                    selected = evaluated
                elif scope in {"train", "dev"}:
                    selected = [
                        row for row in evaluated if row["split"] == scope
                    ]
                else:
                    selected = [
                        row for row in evaluated if row["scope"] == scope
                    ]
                pooled = summarize(selected)
                output.append(
                    {
                        "scope": scope,
                        "aggregation": "pooled",
                        "max_probes": max_probes,
                        "threshold": threshold,
                        **pooled,
                    }
                )

                environment_metrics = [
                    summarize(
                        [
                            row
                            for row in selected
                            if row["environment"] == environment
                        ]
                    )
                    for environment in sorted(
                        {row["environment"] for row in selected}
                    )
                ]
                macro_keys = (
                    "baseline_accuracy_pct",
                    "accuracy_pct",
                    "accuracy_drop_pp",
                    "token_saving_pct",
                    "stop_rate_pct",
                    "early_stop_accuracy_pct",
                    "false_stop_ratio_pct",
                    "avg_probes",
                )
                output.append(
                    {
                        "scope": scope,
                        "aggregation": "environment_macro",
                        "max_probes": max_probes,
                        "threshold": threshold,
                        "n": len(selected),
                        **{
                            key: sum(
                                float(metric[key])
                                for metric in environment_metrics
                            )
                            / len(environment_metrics)
                            for key in macro_keys
                        },
                        "harm_count": sum(
                            int(metric["harm_count"])
                            for metric in environment_metrics
                        ),
                        "rescue_count": sum(
                            int(metric["rescue_count"])
                            for metric in environment_metrics
                        ),
                        "harm_rescue_ratio": (
                        sum(
                            int(metric["harm_count"])
                            for metric in environment_metrics
                        )
                        / sum(
                            int(metric["rescue_count"])
                            for metric in environment_metrics
                        )
                        if sum(
                            int(metric["rescue_count"])
                            for metric in environment_metrics
                        )
                        else math.inf
                        ),
                    }
                )

                model_benchmark_metrics = [
                    summarize(
                        [
                            row
                            for row in selected
                            if (
                                row["model_key"],
                                row["benchmark"],
                            )
                            == model_benchmark
                        ]
                    )
                    for model_benchmark in sorted(
                        {
                            (row["model_key"], row["benchmark"])
                            for row in selected
                        }
                    )
                ]
                output.append(
                    {
                        "scope": scope,
                        "aggregation": "model_benchmark_macro",
                        "max_probes": max_probes,
                        "threshold": threshold,
                        "n": len(selected),
                        **{
                            key: sum(
                                float(metric[key])
                                for metric in model_benchmark_metrics
                            )
                            / len(model_benchmark_metrics)
                            for key in macro_keys
                        },
                        "harm_count": sum(
                            int(metric["harm_count"])
                            for metric in model_benchmark_metrics
                        ),
                        "rescue_count": sum(
                            int(metric["rescue_count"])
                            for metric in model_benchmark_metrics
                        ),
                        "harm_rescue_ratio": (
                            sum(
                                int(metric["harm_count"])
                                for metric in model_benchmark_metrics
                            )
                            / sum(
                                int(metric["rescue_count"])
                                for metric in model_benchmark_metrics
                            )
                            if sum(
                                int(metric["rescue_count"])
                                for metric in model_benchmark_metrics
                            )
                            else math.inf
                        ),
                    }
                )
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_related_anchors(scope: str) -> dict[str, dict[str, float]]:
    source = (
        REPO
        / "benchmark/FalseConsensus/results/related_work"
        / (
            "aggregate/train_dev_diagnostic.csv"
            if scope == "full"
            else "test_aggregate/dev_pooled.csv"
        )
    )
    with source.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    output: dict[str, dict[str, float]] = {}
    for method in ("deer_frozen", "tje_frozen"):
        selected = [row for row in rows if row["method"] == method]
        n = sum(int(row["n"]) for row in selected)
        correct = sum(int(row["n"]) * float(row["accuracy"]) for row in selected)
        baseline_correct = sum(
            int(row["n"]) * float(row["baseline_accuracy"]) for row in selected
        )
        used_tokens = sum(
            int(row["n"]) * float(row["avg_all_generated_tokens"])
            for row in selected
        )
        baseline_tokens = sum(
            int(row["n"]) * float(row["avg_baseline_all_generated_tokens"])
            for row in selected
        )
        output[method] = {
            "accuracy_drop_pp": 100.0 * (baseline_correct - correct) / n,
            "token_saving_pct": 100.0 * (baseline_tokens - used_tokens)
            / baseline_tokens,
        }
    return output


def selected_rows(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in metrics
        if row["aggregation"] == "pooled"
        and int(row["max_probes"]) == 30
        and row["scope"] in {"full", "test"}
        and any(
            math.isclose(float(row["threshold"]), threshold)
            for threshold in TABLE_THRESHOLDS
        )
    ]


def matched_faithful_rows(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for scope in ("full", "test"):
        anchor = load_related_anchors(scope)["deer_frozen"]
        for max_probes in PROBE_CAPS:
            candidates = [
                row
                for row in metrics
                if row["scope"] == scope
                and row["aggregation"] == "pooled"
                and int(row["max_probes"]) == max_probes
            ]
            nearest = min(
                candidates,
                key=lambda row: (
                    abs(
                        float(row["accuracy_drop_pp"])
                        - anchor["accuracy_drop_pp"]
                    ),
                    -float(row["token_saving_pct"]),
                ),
            )
            output.append(
                {
                    "scope": scope,
                    "max_probes": max_probes,
                    "threshold": nearest["threshold"],
                    "direct_accuracy_drop_pp": nearest["accuracy_drop_pp"],
                    "direct_token_saving_pct": nearest["token_saving_pct"],
                    "direct_stop_rate_pct": nearest["stop_rate_pct"],
                    "faithful_deer_accuracy_drop_pp": anchor[
                        "accuracy_drop_pp"
                    ],
                    "faithful_deer_token_saving_pct": anchor[
                        "token_saving_pct"
                    ],
                }
            )
    return output


def threshold_label(threshold: float) -> str:
    if 0.9999 <= threshold < 1.0:
        return f"{threshold:.8f}".rstrip("0")
    return f"{threshold:g}"


def make_frontier(metrics: list[dict[str, Any]]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.2), constrained_layout=True)
    for axis, scope, title in zip(
        axes,
        ("full", "test"),
        ("Train + dev (seeds 42–44)", "Test (seeds 45–47)"),
    ):
        cap_styles = {
            10: ("#2563eb", "o"),
            20: ("#d97706", "s"),
            30: ("#0f766e", "o"),
        }
        for max_probes in PROBE_CAPS:
            points = [
                row
                for row in metrics
                if row["scope"] == scope
                and row["aggregation"] == "pooled"
                and int(row["max_probes"]) == max_probes
            ]
            points.sort(key=lambda row: float(row["threshold"]))
            color, marker = cap_styles[max_probes]
            axis.plot(
                [float(row["accuracy_drop_pp"]) for row in points],
                [float(row["token_saving_pct"]) for row in points],
                marker=marker,
                color=color,
                linewidth=1.8,
                markersize=3.5,
                label=f"Direct submit, cap {max_probes}",
            )
            if max_probes == 30:
                for row in points:
                    threshold = float(row["threshold"])
                    if threshold in TABLE_THRESHOLDS:
                        axis.annotate(
                            threshold_label(threshold),
                            (
                                float(row["accuracy_drop_pp"]),
                                float(row["token_saving_pct"]),
                            ),
                            xytext=(5, 5),
                            textcoords="offset points",
                            fontsize=8,
                        )
        anchors = load_related_anchors(scope)
        for method, marker, color, label in (
            ("deer_frozen", "D", "#7c3aed", "Faithful DEER + readout"),
            ("tje_frozen", "*", "#ea580c", "Faithful TJE"),
        ):
            anchor = anchors[method]
            axis.scatter(
                [anchor["accuracy_drop_pp"]],
                [anchor["token_saving_pct"]],
                marker=marker,
                s=95,
                color=color,
                edgecolors="white",
                linewidths=0.7,
                zorder=5,
                label=label,
            )
            axis.annotate(
                label,
                (anchor["accuracy_drop_pp"], anchor["token_saving_pct"]),
                xytext=(7, 8 if method == "deer_frozen" else -14),
                textcoords="offset points",
                fontsize=8,
            )
        axis.axvline(0, color="#64748b", linewidth=1)
        axis.axhline(0, color="#64748b", linewidth=1)
        axis.set_title(title)
        axis.set_xlabel("Accuracy drop vs full (pp) — lower is better")
        axis.set_ylabel("All-generated-token saving (%) — higher is better")
        axis.text(
            0.02,
            0.98,
            "Preferred: upper-left",
            transform=axis.transAxes,
            va="top",
            fontsize=9,
            color="#475569",
        )
        axis.legend(loc="lower right", fontsize=8)
    fig.suptitle(
        "DEER direct-submit threshold frontiers from the cap-30 bank",
        fontsize=15,
    )
    for suffix in ("png", "pdf"):
        fig.savefig(
            FIGURES / f"deer_confidence_frontier_cap30.{suffix}",
            dpi=220,
            bbox_inches="tight",
        )
    plt.close(fig)


def cap_hit_curves(rows: list[dict[str, Any]], threshold: float = 0.995) -> None:
    curves: dict[str, list[float]] = {}
    for scope in ("full", "test", "all"):
        selected = rows if scope == "all" else [r for r in rows if r["scope"] == scope]
        values = []
        for cap in range(1, 31):
            hits = 0
            for row in selected:
                if any(
                    normalized(trial.get("trial_answer"))
                    and float(trial["confidence"]) > threshold
                    for trial in row["trials"][:cap]
                ):
                    hits += 1
            values.append(100.0 * hits / len(selected))
        curves[scope] = values

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axis = plt.subplots(figsize=(8.2, 5.0), constrained_layout=True)
    styles = {
        "full": ("#2563eb", "Train + dev"),
        "test": ("#dc2626", "Test"),
        "all": ("#0f766e", "All"),
    }
    caps = list(range(1, 31))
    for scope in ("full", "test", "all"):
        color, label = styles[scope]
        axis.plot(caps, curves[scope], color=color, linewidth=2, label=label)
        for cap in (10, 20, 30):
            axis.scatter(
                [cap],
                [curves[scope][cap - 1]],
                color=color,
                s=24,
                zorder=3,
            )
    axis.set_xlabel("Maximum Wait probes per trajectory")
    axis.set_ylabel("Valid confidence > 0.995 hit rate (%)")
    axis.set_title("Marginal coverage from extending DEER probing to 30 Waits")
    axis.legend(loc="lower right")
    for suffix in ("png", "pdf"):
        fig.savefig(
            FIGURES / f"deer_confidence_cap_saturation.{suffix}",
            dpi=220,
            bbox_inches="tight",
        )
    plt.close(fig)


def write_report(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# DEER cap-30 direct-submit frontier",
        "",
        "The replay accepts the first non-empty DEER answer with confidence "
        "strictly above the threshold, directly submits it without a formal "
        "readout, and otherwise retains the frozen full answer. Token saving "
        "charges all generated probe-output tokens through the decision.",
        "",
        "| Scope | Threshold | Accuracy | Drop | Token saving | Stop rate | "
        "Stopped accuracy | False-stop | Avg probes | Harm / rescue |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in selected_rows(rows):
        ratio = float(row["harm_rescue_ratio"])
        ratio_text = "∞" if math.isinf(ratio) else f"{ratio:.2f}"
        lines.append(
            f"| {row['scope']} | {float(row['threshold']):.6f} | "
            f"{float(row['accuracy_pct']):.2f}% | "
            f"{float(row['accuracy_drop_pp']):+.2f} pp | "
            f"{float(row['token_saving_pct']):.2f}% | "
            f"{float(row['stop_rate_pct']):.2f}% | "
            f"{float(row['early_stop_accuracy_pct']):.2f}% | "
            f"{float(row['false_stop_ratio_pct']):.2f}% | "
            f"{float(row['avg_probes']):.2f} | "
            f"{int(row['harm_count'])}/{int(row['rescue_count'])} "
            f"({ratio_text}) |"
        )
    lines.extend(
        [
            "",
            "## Faithful related-work anchors",
            "",
            "| Scope | Method | Accuracy drop | Token saving |",
            "|---|---|---:|---:|",
        ]
    )
    for scope in ("full", "test"):
        for method, values in load_related_anchors(scope).items():
            lines.append(
                f"| {scope} | {method} | "
                f"{values['accuracy_drop_pp']:+.2f} pp | "
                f"{values['token_saving_pct']:.2f}% |"
            )
    lines.extend(
        [
            "",
            "## Same-threshold comparison (tau=0.95, cap=10)",
            "",
            "At the same threshold and cap, direct submit omits the readout and "
            "therefore saves more tokens. With the project robust mathematical "
            "equivalence grader, it also has a smaller measured accuracy drop "
            "than the faithful readout variant.",
            "",
            "| Scope | Variant | Accuracy drop | Token saving |",
            "|---|---|---:|---:|",
        ]
    )
    for scope in ("full", "test"):
        direct = next(
            row
            for row in rows
            if row["scope"] == scope
            and row["aggregation"] == "pooled"
            and int(row["max_probes"]) == 10
            and math.isclose(float(row["threshold"]), 0.95)
        )
        faithful = load_related_anchors(scope)["deer_frozen"]
        lines.extend(
            [
                f"| {scope} | Direct submit | "
                f"{float(direct['accuracy_drop_pp']):+.2f} pp | "
                f"{float(direct['token_saving_pct']):.2f}% |",
                f"| {scope} | Faithful DEER + readout | "
                f"{faithful['accuracy_drop_pp']:+.2f} pp | "
                f"{faithful['token_saving_pct']:.2f}% |",
            ]
        )
    lines.extend(
        [
            "",
            "## Direct submit at approximately matched faithful-DEER accuracy",
            "",
            "| Scope | Cap | Threshold | Direct drop | Direct saving | "
            "Faithful DEER drop | Faithful DEER saving |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in matched_faithful_rows(rows):
        lines.append(
            f"| {row['scope']} | {row['max_probes']} | "
            f"{threshold_label(float(row['threshold']))} | "
            f"{float(row['direct_accuracy_drop_pp']):+.2f} pp | "
            f"{float(row['direct_token_saving_pct']):.2f}% | "
            f"{float(row['faithful_deer_accuracy_drop_pp']):+.2f} pp | "
            f"{float(row['faithful_deer_token_saving_pct']):.2f}% |"
        )
    (RESULTS / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    metrics = analyze(rows)
    write_csv(RESULTS / "frontier.csv", metrics)
    write_csv(RESULTS / "selected_thresholds.csv", selected_rows(metrics))
    write_csv(
        RESULTS / "matched_faithful_accuracy.csv",
        matched_faithful_rows(metrics),
    )
    make_frontier(metrics)
    cap_hit_curves(rows)
    write_report(metrics)
    print(f"trajectories={len(rows)}")
    print(f"frontier_rows={len(metrics)}")
    print(f"output={RESULTS}")


if __name__ == "__main__":
    main()
