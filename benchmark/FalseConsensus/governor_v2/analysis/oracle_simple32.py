#!/usr/bin/env python3
"""Non-deployable upper bound from the frozen interval-64 simple@32 probe bank.

For every seen-model trajectory, the oracle submits the first valid probe answer
that matches the reference answer.  If no such probe exists it falls back to the
observed full trajectory.  The analysis is diagnostic only: reference labels are
used to choose the stopping point and the result must never enter rule selection.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RESULTS = REPO / "benchmark/FalseConsensus/results/governor_v2"
SPLITS = REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
OUT = RESULTS / "simple32_oracle"
FIGURE = REPO / "benchmark/FalseConsensus/report/figures/simple32_oracle_upper_bound"
SEEN_MODELS = {
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "Qwen/Qwen3-8B",
}
BENCHMARKS = {"math500", "amc23", "aime24"}
EXPECTED_ENVS = 36
EXPECTED_TRAJECTORIES = 3420

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmark/TokenDeprivation"))
from benchmark.FalseConsensus.governor_v2.replay_rules import (  # noqa: E402
    answers_equal,
    load_split_map,
    valid_answer,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def discover_environments() -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for env in sorted(RESULTS.iterdir()):
        if not env.is_dir() or not env.name.startswith(("development__", "confirmation__")):
            continue
        manifest_path = env / "main/run_manifest.json"
        probe_manifest_path = env / "dense_simple32/probe_manifest.json"
        if not manifest_path.exists() or not probe_manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        settings = manifest["run_settings"]
        model, benchmark, seed = (
            str(settings["model"]),
            str(settings["dataset"]),
            int(settings["base_seed"]),
        )
        if model not in SEEN_MODELS or benchmark not in BENCHMARKS or seed not in range(42, 48):
            continue
        phase = str(settings["phase"])
        if (seed <= 44 and phase != "development") or (seed >= 45 and phase != "confirmation"):
            raise AssertionError(f"phase/seed mismatch in {env}")
        probe_manifest = json.loads(probe_manifest_path.read_text(encoding="utf-8"))
        probe_settings = probe_manifest["probe_settings"]
        required = {
            "probe_style": "simple",
            "probe_tokens": 32,
            "dense_interval": 64,
            "start_token": 64,
        }
        for key, expected in required.items():
            if probe_settings.get(key) != expected:
                raise AssertionError(f"{env}: {key}={probe_settings.get(key)!r}, expected {expected!r}")
        found.append((env, settings))
    if len(found) != EXPECTED_ENVS:
        raise AssertionError(f"expected {EXPECTED_ENVS} seen-model environments, found {len(found)}")
    return found


def build_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    split_map = load_split_map(SPLITS)
    rows: list[dict[str, Any]] = []
    input_files: list[dict[str, Any]] = [{"path": str(SPLITS.relative_to(REPO)), "sha256": sha256(SPLITS)}]
    for env, settings in discover_environments():
        model = str(settings["model"])
        benchmark = str(settings["dataset"])
        seed = int(settings["base_seed"])
        traj_paths = sorted((env / "main/traj").glob("problem_*.json"))
        probe_paths = sorted((env / "dense_simple32/probes").glob("problem_*.json"))
        probe_by_id = {int(path.stem.split("_")[-1]): path for path in probe_paths}
        if len(traj_paths) != len(probe_paths):
            raise AssertionError(f"trajectory/probe count mismatch: {env}")
        for traj_path in traj_paths:
            trajectory = json.loads(traj_path.read_text(encoding="utf-8"))
            problem_id = int(trajectory["problem_id"])
            probe_path = probe_by_id.get(problem_id)
            if probe_path is None:
                raise AssertionError(f"missing dense probe file for {env.name}/problem_{problem_id}")
            payload = json.loads(probe_path.read_text(encoding="utf-8"))
            probes = sorted(payload["probes"], key=lambda item: int(item["token_position"]))
            if any(int(right["token_position"]) - int(left["token_position"]) != 64
                   for left, right in zip(probes, probes[1:])):
                raise AssertionError(f"non-dense schedule in {probe_path}")
            target = trajectory["target"]
            cumulative_probe_tokens = 0
            chosen: dict[str, Any] | None = None
            for probe in probes:
                cumulative_probe_tokens += int(probe.get("probe_out_tokens", 0))
                answer = str(probe.get("probe_answer", ""))
                if valid_answer(answer, benchmark, "schema") and answers_equal(answer, target):
                    chosen = probe
                    break
            full_main_tokens = int(trajectory["tokens_used"])
            all_probe_tokens = sum(int(probe.get("probe_out_tokens", 0)) for probe in probes)
            finished = bool(trajectory.get("finished_naturally", False))
            observed_final_correct = bool(answers_equal(trajectory.get("final_answer", ""), target))
            strict_full_correct = bool(finished and observed_final_correct)
            if chosen is not None:
                oracle_tokens = int(chosen["token_position"]) + cumulative_probe_tokens
                oracle_correct = True
                oracle_observed_correct = True
                stop_position: int | str = int(chosen["token_position"])
                stop_probe_id: int | str = int(chosen["probe_id"])
                used_fallback = False
            else:
                oracle_tokens = full_main_tokens + all_probe_tokens
                oracle_correct = strict_full_correct
                oracle_observed_correct = observed_final_correct
                stop_position = ""
                stop_probe_id = ""
                used_fallback = True
            rows.append(
                {
                    "model": model,
                    "benchmark": benchmark,
                    "seed": seed,
                    "split": split_map[(benchmark, problem_id)],
                    "problem_id": problem_id,
                    "environment": env.name,
                    "full_main_tokens": full_main_tokens,
                    "all_probe_out_tokens": all_probe_tokens,
                    "full_finished_naturally": int(finished),
                    "full_correct_strict": int(strict_full_correct),
                    "full_correct_observed": int(observed_final_correct),
                    "oracle_found_correct_probe": int(chosen is not None),
                    "oracle_stop_probe_id": stop_probe_id,
                    "oracle_stop_token": stop_position,
                    "oracle_tokens": oracle_tokens,
                    "oracle_correct_strict": int(oracle_correct),
                    "oracle_correct_observed": int(oracle_observed_correct),
                    "oracle_used_fallback": int(used_fallback),
                    "oracle_token_saving_pct": 100.0 * (full_main_tokens - oracle_tokens) / full_main_tokens,
                }
            )
            input_files.extend(
                [
                    {"path": str(traj_path.relative_to(REPO)), "sha256": sha256(traj_path)},
                    {"path": str(probe_path.relative_to(REPO)), "sha256": sha256(probe_path)},
                ]
            )
    if len(rows) != EXPECTED_TRAJECTORIES:
        raise AssertionError(f"expected {EXPECTED_TRAJECTORIES} trajectories, found {len(rows)}")
    return rows, input_files


def aggregate(rows: Sequence[Mapping[str, Any]], group_fields: Sequence[str], scope: str) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)
    output: list[dict[str, Any]] = []
    for key, group in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0])):
        full_tokens = sum(int(row["full_main_tokens"]) for row in group)
        oracle_tokens = sum(int(row["oracle_tokens"]) for row in group)
        record: dict[str, Any] = {"scope": scope}
        record.update(dict(zip(group_fields, key)))
        stop_tokens = sorted(
            int(row["oracle_stop_token"])
            for row in group
            if int(row["oracle_found_correct_probe"])
        )

        def percentile(fraction: float) -> float | str:
            if not stop_tokens:
                return ""
            position = fraction * (len(stop_tokens) - 1)
            lower, upper = int(position), min(int(position) + 1, len(stop_tokens) - 1)
            weight = position - lower
            return stop_tokens[lower] * (1.0 - weight) + stop_tokens[upper] * weight

        record.update(
            {
                "n": len(group),
                "full_accuracy_strict_pct": 100.0 * statistics.mean(int(row["full_correct_strict"]) for row in group),
                "oracle_accuracy_strict_pct": 100.0 * statistics.mean(int(row["oracle_correct_strict"]) for row in group),
                "full_accuracy_observed_pct": 100.0 * statistics.mean(int(row["full_correct_observed"]) for row in group),
                "oracle_accuracy_observed_pct": 100.0 * statistics.mean(int(row["oracle_correct_observed"]) for row in group),
                "correct_probe_coverage_pct": 100.0 * statistics.mean(int(row["oracle_found_correct_probe"]) for row in group),
                "fallback_rate_pct": 100.0 * statistics.mean(int(row["oracle_used_fallback"]) for row in group),
                "first_correct_token_mean": statistics.mean(stop_tokens) if stop_tokens else "",
                "first_correct_token_p25": percentile(0.25),
                "first_correct_token_median": percentile(0.50),
                "first_correct_token_p75": percentile(0.75),
                "token_saving_micro_pct": 100.0 * (full_tokens - oracle_tokens) / full_tokens,
                "token_saving_macro_pct": statistics.mean(float(row["oracle_token_saving_pct"]) for row in group),
                "full_main_tokens": full_tokens,
                "oracle_tokens": oracle_tokens,
            }
        )
        output.append(record)
    return output


def environment_macro(
    environment_rows: Sequence[Mapping[str, Any]], group_fields: Sequence[str], scope: str
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in environment_rows:
        groups[tuple(row[field] for field in group_fields)].append(row)
    output: list[dict[str, Any]] = []
    metric_fields = (
        "full_accuracy_strict_pct", "oracle_accuracy_strict_pct",
        "full_accuracy_observed_pct", "oracle_accuracy_observed_pct",
        "correct_probe_coverage_pct", "fallback_rate_pct",
        "token_saving_micro_pct", "token_saving_macro_pct",
    )
    for key, group in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0])):
        record: dict[str, Any] = {"scope": scope, "environment_count": len(group)}
        record.update(dict(zip(group_fields, key)))
        for field in metric_fields:
            record[field] = statistics.mean(float(row[field]) for row in group)
        output.append(record)
    return output


def make_figure(summary: Sequence[Mapping[str, Any]]) -> None:
    split_rows = [row for row in summary if row["scope"] == "split_pooled"]
    order = {"train": 0, "dev": 1, "test": 2}
    split_rows.sort(key=lambda row: order[str(row["split"])])
    labels = [str(row["split"]).title() for row in split_rows]
    full_acc = [float(row["full_accuracy_strict_pct"]) for row in split_rows]
    oracle_acc = [float(row["oracle_accuracy_strict_pct"]) for row in split_rows]
    saving = [float(row["token_saving_micro_pct"]) for row in split_rows]
    x = list(range(len(labels)))
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.0))
    width = 0.34
    axes[0].bar([value - width / 2 for value in x], full_acc, width, label="Observed full")
    axes[0].bar([value + width / 2 for value in x], oracle_acc, width, label="Oracle")
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Strict accuracy (%)")
    axes[0].set_title("Accuracy upper bound")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(x, saving, width=0.55, color="#6f4cc3")
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("All-generated-token saving (%)")
    axes[1].set_title("Earliest-correct-probe saving")
    axes[1].grid(axis="y", alpha=0.25)
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Non-deployable simple@32 oracle (interval 64)")
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE.with_suffix(".png"), dpi=220, bbox_inches="tight")
    fig.savefig(FIGURE.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    rows, inputs = build_rows()
    environment = aggregate(rows, ["model", "benchmark", "seed", "split"], "environment")
    summary: list[dict[str, Any]] = []
    summary.extend(aggregate(rows, [], "pooled"))
    summary.extend(aggregate(rows, ["split"], "split_pooled"))
    summary.extend(aggregate(rows, ["model"], "model_pooled"))
    summary.extend(aggregate(rows, ["benchmark"], "benchmark_pooled"))
    summary.extend(aggregate(rows, ["seed"], "seed_pooled"))
    macro_summary: list[dict[str, Any]] = []
    macro_summary.extend(environment_macro(environment, [], "environment_macro"))
    macro_summary.extend(environment_macro(environment, ["split"], "split_environment_macro"))
    write_csv(OUT / "per_problem.csv", rows)
    write_csv(OUT / "per_environment.csv", environment)
    write_csv(OUT / "summary.csv", summary)
    write_csv(OUT / "macro_summary.csv", macro_summary)
    make_figure(summary)
    pooled = next(row for row in summary if row["scope"] == "pooled")
    report = f"""# simple@32 oracle upper bound

This is a **non-deployable diagnostic**, not a Governor rule. It uses the reference
label to submit the first valid, correct interval-64 simple@32 probe; if none exists,
it falls back to the observed full trajectory. Probe output tokens are charged, while
probe prompt/prefill tokens are excluded consistently with the paper's generated-token metric.

| Scope | Trajectories | Full strict acc. | Oracle strict acc. | Correct-probe coverage | Fallback | First-correct token P25 / median / P75 | Token saving (micro) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pooled | {int(pooled['n']):,} | {float(pooled['full_accuracy_strict_pct']):.2f}% | {float(pooled['oracle_accuracy_strict_pct']):.2f}% | {float(pooled['correct_probe_coverage_pct']):.2f}% | {float(pooled['fallback_rate_pct']):.2f}% | {float(pooled['first_correct_token_p25']):.0f} / {float(pooled['first_correct_token_median']):.0f} / {float(pooled['first_correct_token_p75']):.0f} | {float(pooled['token_saving_micro_pct']):.2f}% |

Strict full accuracy requires natural completion and a correct final answer. The
parallel observed-answer columns retain capped-but-correct answers as a sensitivity
check. All inputs are frozen seen-model trajectories (two models, three benchmarks,
seeds 42--47, Train/Dev/Test); no unseen-model result is required.
"""
    atomic_text(OUT / "report.md", report)
    atomic_text(OUT / "input_files.json", json.dumps(inputs, indent=2) + "\n")
    manifest = {
        "schema_version": "simple32-oracle-cpu-1",
        "non_deployable_oracle": True,
        "uses_reference_labels_for_stopping": True,
        "test_data_used_for_diagnostic_only": True,
        "test_data_used_for_rule_selection": False,
        "probe_style": "simple",
        "probe_tokens": 32,
        "interval": 64,
        "validity_mode": "schema",
        "cost_metric": "main decode tokens plus probe output tokens through stopping/fallback",
        "expected_environments": EXPECTED_ENVS,
        "environment_count": len(discover_environments()),
        "trajectory_count": len(rows),
        "input_file_count": len(inputs),
        "input_digest": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
        "outputs": ["per_problem.csv", "per_environment.csv", "summary.csv", "macro_summary.csv", "input_files.json", "report.md"],
    }
    atomic_text(OUT / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "pooled": pooled}, indent=2))


if __name__ == "__main__":
    main()
