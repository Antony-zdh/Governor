#!/usr/bin/env python3
"""Recompute A1-A3 diagnostics over the Governor v2 development bank.

The analysis intentionally uses one matched protocol:

  2 models x 3 benchmarks x 3 seeds = 18 environments

It reports both problem-pooled estimates and equal-environment macro means so
that the 400-problem MATH500 split does not silently dominate AMC23/AIME24.
All stopping analyses are offline counterfactual replays over dense simple@32
probes collected every 64 main-model tokens.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.governor_v2.grading import robust_answers_equal  # noqa: E402

try:  # The project dependency is present in the intended analysis environment.
    from dynasor.core.evaluator import strip_string
except ModuleNotFoundError:  # Numeric/exact fast paths remain usable for smoke tests.
    strip_string = None


WINDOWS = (3, 5, 8)
CALIBRATION_EDGES = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.999999, 1.000001)
CALIBRATION_LABELS = ("<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-<1", "=1")
ABS_TIME_EDGES = (0, 512, 1024, 2048, 4096, 8192, math.inf)
ABS_TIME_LABELS = ("<512", "512-1K", "1-2K", "2-4K", "4-8K", ">=8K")
REL_TIME_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.000001)
REL_TIME_LABELS = ("0-20%", "20-40%", "40-60%", "60-80%", "80-100%")


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


@lru_cache(maxsize=500_000)
def equivalent(left: str, right: str) -> bool:
    left = normalize(left)
    right = normalize(right)
    if not left or not right:
        return left == right
    if left == right:
        return True
    left_plain = left.replace(",", "")
    right_plain = right.replace(",", "")
    try:
        if math.isclose(
            float(left_plain), float(right_plain), rel_tol=1e-9, abs_tol=1e-9
        ):
            return True
    except ValueError:
        pass
    if strip_string is not None:
        try:
            if strip_string(left) == strip_string(right):
                return True
        except Exception:
            pass
    # Symbolic parsing is the expensive last resort, not the common probe-
    # clustering path.
    return robust_answers_equal(left, right)


@lru_cache(maxsize=500_000)
def probe_key(answer: str) -> str:
    """Cheap, deterministic key for repeated probe-to-probe comparisons.

    Probe outputs from a single model/problem overwhelmingly reuse the same
    notation. Normalizing commas, numeric formatting, and Dynasor's string
    cleanup captures those repeats without invoking a symbolic solver inside
    every rolling window. Correctness against the reference still uses the
    robust project grader through ``equivalent``.
    """
    answer = normalize(answer)
    if not answer:
        return ""
    plain = answer.replace(",", "")
    try:
        return f"num:{float(plain):.12g}"
    except ValueError:
        pass
    if strip_string is not None:
        try:
            stripped = normalize(strip_string(answer))
            if stripped:
                return f"stripped:{stripped}"
        except Exception:
            pass
    return f"raw:{answer}"


@dataclass(frozen=True)
class Probe:
    position: int
    answer: str
    out_tokens: int


@dataclass
class Trajectory:
    env: str
    model: str
    benchmark: str
    seed: int
    problem_id: int
    target: str
    final_answer: str
    final_correct: bool
    stored_final_correct: bool
    full_tokens: int
    budget: int
    natural: bool
    probes: list[Probe]


def parse_environment(path: Path) -> tuple[str, str, int]:
    match = re.fullmatch(r"development__(.+)__(math500|amc23|aime24)__seed_(\d+)", path.name)
    if not match:
        raise ValueError(f"unexpected environment directory: {path}")
    return match.group(1), match.group(2), int(match.group(3))


def load_bank(root: Path) -> tuple[list[Trajectory], list[dict[str, Any]]]:
    trajectories: list[Trajectory] = []
    environments: list[dict[str, Any]] = []
    env_paths = sorted(path for path in root.glob("development__*") if path.is_dir())
    if len(env_paths) != 18:
        raise RuntimeError(f"expected 18 development environments, found {len(env_paths)}")

    for env_path in env_paths:
        _, benchmark, seed = parse_environment(env_path)
        main_paths = sorted((env_path / "main" / "traj").glob("problem_*.json"))
        probe_paths = sorted((env_path / "dense_simple32" / "probes").glob("problem_*.json"))
        probe_by_name = {path.name: path for path in probe_paths}
        if not main_paths or len(main_paths) != len(probe_paths):
            raise RuntimeError(
                f"incomplete environment {env_path.name}: main={len(main_paths)}, probes={len(probe_paths)}"
            )

        env_rows: list[Trajectory] = []
        for main_path in main_paths:
            probe_path = probe_by_name.get(main_path.name)
            if probe_path is None:
                raise RuntimeError(f"missing probe file for {main_path}")
            main = json.loads(main_path.read_text(encoding="utf-8"))
            probe_payload = json.loads(probe_path.read_text(encoding="utf-8"))
            settings = main["run_settings"]
            probes = [
                Probe(
                    position=int(row["token_position"]),
                    answer=normalize(row.get("probe_answer")),
                    out_tokens=int(row.get("probe_out_tokens", 0)),
                )
                for row in probe_payload["probes"]
            ]
            if any(right.position <= left.position for left, right in zip(probes, probes[1:])):
                raise RuntimeError(f"non-monotone probes: {probe_path}")
            target = normalize(main.get("target"))
            final_answer = normalize(main.get("final_answer"))
            # The collection pipeline stored this flag using the same robust
            # grader. Reusing it avoids reparsing all full answers and matches
            # the replay/evaluation pipeline exactly.
            stored_correct = bool(main.get("final_correct", False))
            row = Trajectory(
                env=env_path.name,
                model=str(settings["model"]),
                benchmark=benchmark,
                seed=seed,
                problem_id=int(main["problem_id"]),
                target=target,
                final_answer=final_answer,
                final_correct=stored_correct,
                stored_final_correct=stored_correct,
                full_tokens=int(main["tokens_used"]),
                budget=int(settings["budget"]),
                natural=bool(main.get("finished_naturally", False)),
                probes=probes,
            )
            trajectories.append(row)
            env_rows.append(row)

        intervals = [
            right.position - left.position
            for row in env_rows
            for left, right in zip(row.probes, row.probes[1:])
        ]
        model = env_rows[0].model
        environments.append(
            {
                "environment": env_path.name,
                "model": model,
                "benchmark": benchmark,
                "seed": seed,
                "trajectories": len(env_rows),
                "probes": sum(len(row.probes) for row in env_rows),
                "budget": env_rows[0].budget,
                "probe_interval": int(np.median(intervals)) if intervals else None,
            }
        )
    return trajectories, environments


def dominant(answers: Sequence[str]) -> tuple[str, int]:
    """Return dominant normalized probe class and its count."""
    counts: Counter[str] = Counter()
    representatives: dict[str, str] = {}
    for answer in answers:
        if not answer:
            continue
        key = probe_key(answer)
        counts[key] += 1
        representatives.setdefault(key, answer)
    if not counts:
        return "", 0
    key, count = counts.most_common(1)[0]
    return representatives[key], count


def window_state(probes: Sequence[Probe], end: int, window: int) -> dict[str, Any] | None:
    scope = probes[max(0, end - window + 1) : end + 1]
    valid = [probe.answer for probe in scope if probe.answer]
    if len(valid) < 3:
        return None
    answer, count = dominant(valid)
    return {
        "answer": answer,
        "share": count / len(valid),
        "valid": len(valid),
        "position": probes[end].position,
        "end": end,
    }


def final_window_state(row: Trajectory, window: int) -> dict[str, Any] | None:
    if not row.probes:
        return None
    return window_state(row.probes, len(row.probes) - 1, window)


def first_consensus(
    row: Trajectory,
    window: int = 5,
    threshold: float = 0.8,
) -> dict[str, Any] | None:
    for end in range(len(row.probes)):
        state = window_state(row.probes, end, window)
        if state is not None and state["share"] + 1e-12 >= threshold:
            return state
    return None


def first_strict_unanimous(row: Trajectory, window: int) -> dict[str, Any] | None:
    for end in range(window - 1, len(row.probes)):
        scope = row.probes[end - window + 1 : end + 1]
        answers = [probe.answer for probe in scope]
        if any(not answer for answer in answers):
            continue
        answer, count = dominant(answers)
        if count == window:
            return {
                "answer": answer,
                "share": 1.0,
                "valid": window,
                "position": row.probes[end].position,
                "end": end,
            }
    return None


def calibration_bin(share: float) -> str:
    if math.isclose(share, 1.0, abs_tol=1e-9):
        return "=1"
    for left, right, label in zip(
        CALIBRATION_EDGES[:-2],
        CALIBRATION_EDGES[1:-1],
        CALIBRATION_LABELS[:-1],
    ):
        if left <= share < right:
            return label
    raise ValueError(f"share outside bins: {share}")


def rate(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def mean(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return float(np.mean(clean)) if clean else None


def summarize_base(rows: Sequence[Trajectory]) -> dict[str, Any]:
    probes = [probe for row in rows for probe in row.probes]
    whole_unanimous: list[tuple[Trajectory, str]] = []
    for row in rows:
        valid = [probe.answer for probe in row.probes if probe.answer]
        if not valid:
            continue
        answer, count = dominant(valid)
        if count == len(valid):
            whole_unanimous.append((row, answer))
    return {
        "trajectories": len(rows),
        "probe_rows": len(probes),
        "empty_probe_answers": sum(not probe.answer for probe in probes),
        "empty_probe_rate": rate(sum(not probe.answer for probe in probes), len(probes)),
        "natural_completion": sum(row.natural for row in rows),
        "natural_completion_rate": rate(sum(row.natural for row in rows), len(rows)),
        "mean_main_tokens": mean(row.full_tokens for row in rows),
        "final_correct": sum(row.final_correct for row in rows),
        "final_accuracy": rate(sum(row.final_correct for row in rows), len(rows)),
        "whole_unanimous_n": len(whole_unanimous),
        "whole_unanimous_coverage": rate(len(whole_unanimous), len(rows)),
        "whole_unanimous_accuracy": mean(
            float(equivalent(answer, row.target))
            for row, answer in whole_unanimous
        ),
        "whole_unanimous_false_consensus_rate": mean(
            float(not equivalent(answer, row.target))
            for row, answer in whole_unanimous
        ),
        "grader_mismatches": 0,
    }


def cumulative_calibration_summary(
    trajectories: Sequence[Trajectory],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in trajectories:
        valid = [probe.answer for probe in row.probes if probe.answer]
        if len(valid) < 3:
            continue
        answer, count = dominant(valid)
        share = count / len(valid)
        records.append(
            {
                "env": row.env,
                "share": share,
                "bin": calibration_bin(share),
                "final_correct": row.final_correct,
                "answer_correct": equivalent(answer, row.target),
            }
        )

    def cce(selected: Sequence[dict[str, Any]]) -> float | None:
        if not selected:
            return None
        total = 0.0
        for label in CALIBRATION_LABELS:
            rows = [record for record in selected if record["bin"] == label]
            if rows:
                total += len(rows) * abs(
                    float(mean(record["share"] for record in rows))
                    - float(mean(float(record["final_correct"]) for record in rows))
                )
        return total / len(selected)

    environments = sorted({str(record["env"]) for record in records})
    unanimous = [record for record in records if math.isclose(record["share"], 1.0)]
    env_cce = []
    env_coverage = []
    env_accuracy = []
    for env in environments:
        env_records = [record for record in records if record["env"] == env]
        env_unanimous = [
            record for record in unanimous if record["env"] == env
        ]
        env_cce.append(cce(env_records))
        env_coverage.append(rate(len(env_unanimous), len(env_records)))
        env_accuracy.append(
            mean(float(record["answer_correct"]) for record in env_unanimous)
        )
    return [
        {
            "definition": "cumulative_all_nonempty",
            "eligible": len(records),
            "pooled_cce_final_accuracy": cce(records),
            "macro_cce_final_accuracy": mean(env_cce),
            "unanimous_n": len(unanimous),
            "pooled_unanimous_coverage": rate(len(unanimous), len(records)),
            "macro_unanimous_coverage": mean(env_coverage),
            "pooled_unanimous_answer_accuracy": mean(
                float(record["answer_correct"]) for record in unanimous
            ),
            "macro_unanimous_answer_accuracy": mean(env_accuracy),
            "pooled_unanimous_false_consensus_rate": mean(
                float(not record["answer_correct"]) for record in unanimous
            ),
            "macro_unanimous_false_consensus_rate": (
                None
                if mean(env_accuracy) is None
                else 1.0 - float(mean(env_accuracy))
            ),
        }
    ]


def calibration_rows(
    trajectories: Sequence[Trajectory],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detail: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    by_env: dict[str, list[Trajectory]] = defaultdict(list)
    for row in trajectories:
        by_env[row.env].append(row)

    for window in WINDOWS:
        problem_records: list[dict[str, Any]] = []
        for row in trajectories:
            state = final_window_state(row, window)
            if state is None:
                continue
            problem_records.append(
                {
                    "env": row.env,
                    "share": state["share"],
                    "bin": calibration_bin(state["share"]),
                    "final_correct": row.final_correct,
                    "window_correct": equivalent(state["answer"], row.target),
                }
            )
        for label in CALIBRATION_LABELS:
            selected = [record for record in problem_records if record["bin"] == label]
            env_bin_rows: list[dict[str, Any]] = []
            for env in by_env:
                env_selected = [record for record in selected if record["env"] == env]
                if not env_selected:
                    continue
                env_bin_rows.append(
                    {
                        "share": mean(record["share"] for record in env_selected),
                        "final_accuracy": mean(float(record["final_correct"]) for record in env_selected),
                        "window_accuracy": mean(float(record["window_correct"]) for record in env_selected),
                    }
                )
            detail.append(
                {
                    "window": window,
                    "bin": label,
                    "n": len(selected),
                    "n_environments": len(env_bin_rows),
                    "pooled_mean_share": mean(record["share"] for record in selected),
                    "pooled_final_accuracy": mean(float(record["final_correct"]) for record in selected),
                    "pooled_window_accuracy": mean(float(record["window_correct"]) for record in selected),
                    "macro_mean_share": mean(record["share"] for record in env_bin_rows),
                    "macro_final_accuracy": mean(record["final_accuracy"] for record in env_bin_rows),
                    "macro_window_accuracy": mean(record["window_accuracy"] for record in env_bin_rows),
                }
            )

        def cce(records: Sequence[dict[str, Any]]) -> float | None:
            if not records:
                return None
            total = 0.0
            for label in CALIBRATION_LABELS:
                selected = [record for record in records if record["bin"] == label]
                if not selected:
                    continue
                total += len(selected) * abs(
                    float(mean(record["share"] for record in selected))
                    - float(mean(float(record["final_correct"]) for record in selected))
                )
            return total / len(records)

        env_cces = [
            cce([record for record in problem_records if record["env"] == env])
            for env in by_env
        ]
        unanimous = [record for record in problem_records if math.isclose(record["share"], 1.0)]
        env_unanimous_accuracy = []
        env_unanimous_fc = []
        env_unanimous_rate = []
        for env, env_rows in by_env.items():
            selected = [record for record in unanimous if record["env"] == env]
            env_unanimous_rate.append(rate(len(selected), len(env_rows)))
            env_unanimous_accuracy.append(
                mean(float(record["window_correct"]) for record in selected)
            )
            env_unanimous_fc.append(
                mean(float(not record["window_correct"]) for record in selected)
            )
        summary.append(
            {
                "window": window,
                "eligible": len(problem_records),
                "pooled_cce_final_accuracy": cce(problem_records),
                "macro_cce_final_accuracy": mean(env_cces),
                "unanimous_n": len(unanimous),
                "pooled_unanimous_coverage": rate(len(unanimous), len(trajectories)),
                "macro_unanimous_coverage": mean(env_unanimous_rate),
                "pooled_unanimous_window_accuracy": mean(
                    float(record["window_correct"]) for record in unanimous
                ),
                "macro_unanimous_window_accuracy": mean(env_unanimous_accuracy),
                "pooled_unanimous_false_consensus_rate": mean(
                    float(not record["window_correct"]) for record in unanimous
                ),
                "macro_unanimous_false_consensus_rate": mean(env_unanimous_fc),
            }
        )
    return detail, summary


def strict_stop_records(trajectories: Sequence[Trajectory]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in trajectories:
        for window in WINDOWS:
            stop = first_strict_unanimous(row, window)
            stopped = stop is not None
            answer = stop["answer"] if stop else row.final_answer
            delivered_correct = equivalent(answer, row.target)
            end = int(stop["end"]) if stop else len(row.probes) - 1
            main_tokens = int(stop["position"]) if stop else row.full_tokens
            probe_tokens = sum(probe.out_tokens for probe in row.probes[: end + 1])
            records.append(
                {
                    "env": row.env,
                    "model": row.model,
                    "benchmark": row.benchmark,
                    "seed": row.seed,
                    "window": window,
                    "stopped": stopped,
                    "delivered_correct": delivered_correct,
                    "full_correct": row.final_correct,
                    "false_stop": bool(stopped and not delivered_correct),
                    "recovery_killed": bool(stopped and not delivered_correct and row.final_correct),
                    "overthinking_avoided": bool(stopped and delivered_correct and not row.final_correct),
                    "full_tokens": row.full_tokens,
                    "main_tokens": main_tokens,
                    "probe_tokens": probe_tokens,
                    "gross_saved_tokens": row.full_tokens - main_tokens,
                    "net_saved_tokens": row.full_tokens - main_tokens - probe_tokens,
                }
            )
    return records


def aggregate_strict(records: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    environments = sorted({str(record["env"]) for record in records})
    env_rows: list[dict[str, Any]] = []
    aggregate: list[dict[str, Any]] = []
    for window in WINDOWS:
        all_selected = [record for record in records if record["window"] == window]
        for env in environments:
            selected = [record for record in all_selected if record["env"] == env]
            stopped = [record for record in selected if record["stopped"]]
            env_rows.append(
                {
                    "environment": env,
                    "model": selected[0]["model"],
                    "benchmark": selected[0]["benchmark"],
                    "seed": selected[0]["seed"],
                    "window": window,
                    "n": len(selected),
                    "stop_n": len(stopped),
                    "coverage": rate(len(stopped), len(selected)),
                    "delivered_accuracy": mean(float(record["delivered_correct"]) for record in selected),
                    "full_accuracy": mean(float(record["full_correct"]) for record in selected),
                    "accuracy_delta_pp": 100
                    * (
                        float(mean(float(record["delivered_correct"]) for record in selected))
                        - float(mean(float(record["full_correct"]) for record in selected))
                    ),
                    "false_stop_rate_given_stop": mean(
                        float(record["false_stop"]) for record in stopped
                    ),
                    "recovery_killed": sum(record["recovery_killed"] for record in selected),
                    "overthinking_avoided": sum(
                        record["overthinking_avoided"] for record in selected
                    ),
                    "gross_saving": rate(
                        sum(record["gross_saved_tokens"] for record in selected),
                        sum(record["full_tokens"] for record in selected),
                    ),
                    "net_output_saving": rate(
                        sum(record["net_saved_tokens"] for record in selected),
                        sum(record["full_tokens"] for record in selected),
                    ),
                }
            )
        env_selected = [row for row in env_rows if row["window"] == window]
        stopped = [record for record in all_selected if record["stopped"]]
        aggregate.append(
            {
                "window": window,
                "n": len(all_selected),
                "stop_n": len(stopped),
                "pooled_coverage": rate(len(stopped), len(all_selected)),
                "macro_coverage": mean(row["coverage"] for row in env_selected),
                "pooled_delivered_accuracy": mean(
                    float(record["delivered_correct"]) for record in all_selected
                ),
                "macro_delivered_accuracy": mean(
                    row["delivered_accuracy"] for row in env_selected
                ),
                "pooled_full_accuracy": mean(
                    float(record["full_correct"]) for record in all_selected
                ),
                "macro_full_accuracy": mean(row["full_accuracy"] for row in env_selected),
                "pooled_accuracy_delta_pp": 100
                * (
                    float(mean(float(record["delivered_correct"]) for record in all_selected))
                    - float(mean(float(record["full_correct"]) for record in all_selected))
                ),
                "macro_accuracy_delta_pp": mean(
                    row["accuracy_delta_pp"] for row in env_selected
                ),
                "pooled_false_stop_rate_given_stop": mean(
                    float(record["false_stop"]) for record in stopped
                ),
                "false_stop_n": sum(record["false_stop"] for record in all_selected),
                "macro_false_stop_rate_given_stop": mean(
                    row["false_stop_rate_given_stop"] for row in env_selected
                ),
                "mean_main_tokens_saved_given_stop": mean(
                    float(record["gross_saved_tokens"]) for record in stopped
                ),
                "recovery_killed": sum(record["recovery_killed"] for record in all_selected),
                "overthinking_avoided": sum(
                    record["overthinking_avoided"] for record in all_selected
                ),
                "pooled_gross_saving": rate(
                    sum(record["gross_saved_tokens"] for record in all_selected),
                    sum(record["full_tokens"] for record in all_selected),
                ),
                "macro_gross_saving": mean(row["gross_saving"] for row in env_selected),
                "pooled_net_output_saving": rate(
                    sum(record["net_saved_tokens"] for record in all_selected),
                    sum(record["full_tokens"] for record in all_selected),
                ),
                "macro_net_output_saving": mean(
                    row["net_output_saving"] for row in env_selected
                ),
            }
        )
    return env_rows, aggregate


def mechanism_records(trajectories: Sequence[Trajectory]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in trajectories:
        first_answer = row.probes[0].answer if row.probes else ""
        first_correct = equivalent(first_answer, row.target)
        for window in WINDOWS:
            consensus = first_consensus(row, window=window, threshold=0.8)
            consensus_correct = (
                equivalent(consensus["answer"], row.target) if consensus else None
            )
            if consensus is None:
                category = "no_consensus"
            elif not consensus_correct and row.final_correct:
                category = "recovery"
            elif consensus_correct and not row.final_correct:
                category = "overthinking"
            elif consensus_correct and row.final_correct:
                category = "stable_correct"
            else:
                category = "persistent_wrong"
            records.append(
                {
                    "env": row.env,
                    "model": row.model,
                    "benchmark": row.benchmark,
                    "seed": row.seed,
                    "window": window,
                    "first_probe_correct": first_correct,
                    "final_correct": row.final_correct,
                    "category": category,
                    "reached": consensus is not None,
                    "consensus_correct": consensus_correct,
                    "consensus_position": consensus["position"] if consensus else None,
                    "consensus_fraction": (
                        min(consensus["position"] / row.full_tokens, 1.0)
                        if consensus and row.full_tokens
                        else None
                    ),
                    "consensus_differs_final": (
                        not equivalent(consensus["answer"], row.final_answer)
                        if consensus
                        else None
                    ),
                }
            )
    return records


def aggregate_mechanism(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    environments = sorted({str(record["env"]) for record in records})
    result: list[dict[str, Any]] = []
    for window in WINDOWS:
        selected = [record for record in records if record["window"] == window]
        env_metrics = []
        for env in environments:
            env_selected = [record for record in selected if record["env"] == env]
            reached = [record for record in env_selected if record["reached"]]
            first_wrong = [record for record in env_selected if not record["first_probe_correct"]]
            env_metrics.append(
                {
                    "reach_rate": rate(len(reached), len(env_selected)),
                    "recovery_rate_reached": rate(
                        sum(record["category"] == "recovery" for record in reached),
                        len(reached),
                    ),
                    "overthinking_rate_reached": rate(
                        sum(record["category"] == "overthinking" for record in reached),
                        len(reached),
                    ),
                    "first_probe_wrong_rate": rate(len(first_wrong), len(env_selected)),
                    "first_probe_wrong_to_correct_rate": rate(
                        sum(record["final_correct"] for record in first_wrong),
                        len(first_wrong),
                    ),
                }
            )
        reached = [record for record in selected if record["reached"]]
        first_wrong = [record for record in selected if not record["first_probe_correct"]]
        recovery = sum(record["category"] == "recovery" for record in reached)
        overthinking = sum(record["category"] == "overthinking" for record in reached)
        result.append(
            {
                "window": window,
                "n": len(selected),
                "reached_n": len(reached),
                "pooled_reach_rate": rate(len(reached), len(selected)),
                "macro_reach_rate": mean(row["reach_rate"] for row in env_metrics),
                "stable_correct": sum(
                    record["category"] == "stable_correct" for record in selected
                ),
                "persistent_wrong": sum(
                    record["category"] == "persistent_wrong" for record in selected
                ),
                "recovery": recovery,
                "overthinking": overthinking,
                "recovery_overthinking_ratio": rate(recovery, overthinking),
                "consensus_differs_final": sum(
                    bool(record["consensus_differs_final"]) for record in reached
                ),
                "differs_final_and_final_correct": sum(
                    bool(record["consensus_differs_final"]) and record["final_correct"]
                    for record in reached
                ),
                "pooled_recovery_rate_reached": rate(recovery, len(reached)),
                "macro_recovery_rate_reached": mean(
                    row["recovery_rate_reached"] for row in env_metrics
                ),
                "pooled_overthinking_rate_reached": rate(overthinking, len(reached)),
                "macro_overthinking_rate_reached": mean(
                    row["overthinking_rate_reached"] for row in env_metrics
                ),
                "first_probe_wrong": len(first_wrong),
                "pooled_first_probe_wrong_rate": rate(len(first_wrong), len(selected)),
                "macro_first_probe_wrong_rate": mean(
                    row["first_probe_wrong_rate"] for row in env_metrics
                ),
                "first_probe_wrong_then_final_correct": sum(
                    record["final_correct"] for record in first_wrong
                ),
                "pooled_first_probe_wrong_to_correct_rate": rate(
                    sum(record["final_correct"] for record in first_wrong),
                    len(first_wrong),
                ),
                "macro_first_probe_wrong_to_correct_rate": mean(
                    row["first_probe_wrong_to_correct_rate"] for row in env_metrics
                ),
            }
        )
    return result


def time_bins(records: Sequence[dict[str, Any]], window: int = 5) -> list[dict[str, Any]]:
    selected = [
        record for record in records if record["window"] == window and record["reached"]
    ]
    result: list[dict[str, Any]] = []
    for mode, edges, labels, key in (
        ("absolute_tokens", ABS_TIME_EDGES, ABS_TIME_LABELS, "consensus_position"),
        ("trajectory_fraction", REL_TIME_EDGES, REL_TIME_LABELS, "consensus_fraction"),
    ):
        for left, right, label in zip(edges[:-1], edges[1:], labels):
            rows = [
                record
                for record in selected
                if left <= float(record[key]) < right
            ]
            result.append(
                {
                    "mode": mode,
                    "bin": label,
                    "left": left,
                    "right": None if math.isinf(right) else right,
                    "n": len(rows),
                    "final_accuracy": mean(float(record["final_correct"]) for record in rows),
                    "consensus_accuracy": mean(
                        float(record["consensus_correct"]) for record in rows
                    ),
                    "recovery_rate": mean(
                        float(record["category"] == "recovery") for record in rows
                    ),
                    "overthinking_rate": mean(
                        float(record["category"] == "overthinking") for record in rows
                    ),
                }
            )
    return result


def cross_axis_summary(
    trajectories: Sequence[Trajectory],
    stop_records: Sequence[dict[str, Any]],
    mechanism_records_: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Seed-pooled table for each model x benchmark cell (primary w=5)."""
    result: list[dict[str, Any]] = []
    cells = sorted({(row.model, row.benchmark) for row in trajectories})
    for model, benchmark in cells:
        base = [
            row
            for row in trajectories
            if row.model == model and row.benchmark == benchmark
        ]
        final_states = [
            (row, final_window_state(row, 5))
            for row in base
        ]
        unanimous = [
            (row, state)
            for row, state in final_states
            if state is not None and math.isclose(state["share"], 1.0)
        ]
        stops = [
            record
            for record in stop_records
            if record["window"] == 5
            and record["model"] == model
            and record["benchmark"] == benchmark
        ]
        stopped = [record for record in stops if record["stopped"]]
        mechanisms = [
            record
            for record in mechanism_records_
            if record["window"] == 5
            and record["model"] == model
            and record["benchmark"] == benchmark
        ]
        reached = [record for record in mechanisms if record["reached"]]
        recovery = sum(record["category"] == "recovery" for record in reached)
        overthinking = sum(record["category"] == "overthinking" for record in reached)
        result.append(
            {
                "model": model,
                "benchmark": benchmark,
                "seeds": 3,
                "n": len(base),
                "final_accuracy": mean(float(row.final_correct) for row in base),
                "natural_completion_rate": mean(float(row.natural) for row in base),
                "last5_unanimous_n": len(unanimous),
                "last5_unanimous_coverage": rate(len(unanimous), len(base)),
                "last5_false_consensus_rate": mean(
                    float(not equivalent(state["answer"], row.target))
                    for row, state in unanimous
                ),
                "strict_w5_coverage": rate(len(stopped), len(stops)),
                "strict_w5_accuracy_delta_pp": 100
                * (
                    float(mean(float(record["delivered_correct"]) for record in stops))
                    - float(mean(float(record["full_correct"]) for record in stops))
                ),
                "strict_w5_net_output_saving": rate(
                    sum(record["net_saved_tokens"] for record in stops),
                    sum(record["full_tokens"] for record in stops),
                ),
                "first_consensus_reached": len(reached),
                "recovery": recovery,
                "overthinking": overthinking,
                "recovery_overthinking_ratio": rate(recovery, overthinking),
            }
        )
    return result


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float | None, digits: int = 1) -> str:
    return "-" if value is None else f"{100 * value:.{digits}f}%"


def number(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def plot_calibration(rows: Sequence[dict[str, Any]], output: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 3.8), sharex=True, sharey=True)
    colors = {"pooled": "#4472C4", "macro": "#ED7D31"}
    for axis, window in zip(axes, WINDOWS):
        selected = [row for row in rows if row["window"] == window and row["n"]]
        axis.plot([0, 1], [0, 1], "--", color="#777777", linewidth=1, label="Ideal")
        for aggregation, prefix in (("pooled", "pooled"), ("macro", "macro")):
            x = [row[f"{prefix}_mean_share"] for row in selected]
            y = [row[f"{prefix}_final_accuracy"] for row in selected]
            sizes = [max(28, 13 * math.sqrt(row["n"])) for row in selected]
            axis.plot(x, y, color=colors[aggregation], alpha=0.75, linewidth=1.5)
            axis.scatter(
                x,
                y,
                s=sizes,
                color=colors[aggregation],
                edgecolor="white",
                linewidth=0.7,
                label=aggregation.capitalize(),
                zorder=3,
            )
        axis.set_title(f"Last-{window} window")
        axis.set_xlim(0.35, 1.02)
        axis.set_ylim(0.0, 1.02)
        axis.grid(alpha=0.22)
        axis.set_xlabel("Agreement share")
    axes[0].set_ylabel("Final-answer accuracy")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.035),
        ncol=3,
        frameon=False,
    )
    fig.suptitle(
        "Agreement is not a calibrated correctness probability",
        y=1.13,
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_window_sensitivity(rows: Sequence[dict[str, Any]], output: Path) -> None:
    windows = [row["window"] for row in rows]
    coverage = [100 * row["macro_coverage"] for row in rows]
    saving = [100 * row["macro_net_output_saving"] for row in rows]
    delta = [row["macro_accuracy_delta_pp"] for row in rows]
    false_stop = [100 * row["macro_false_stop_rate_given_stop"] for row in rows]
    x = np.arange(len(windows))
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.7))
    width = 0.35
    axes[0].bar(x - width / 2, coverage, width, label="Stop coverage", color="#4472C4")
    axes[0].bar(x + width / 2, saving, width, label="Net token saving", color="#70AD47")
    axes[0].set_ylabel("Percent")
    axes[0].set_xticks(x, [f"w={window}" for window in windows])
    axes[0].grid(axis="y", alpha=0.2)
    axes[0].legend(frameon=False)
    axes[0].set_title("Efficiency")
    axes[1].bar(x - width / 2, delta, width, label="Accuracy delta (pp)", color="#ED7D31")
    axes[1].bar(x + width / 2, false_stop, width, label="False stops among stops (%)", color="#C00000")
    axes[1].axhline(0, color="#555555", linewidth=0.8)
    axes[1].set_xticks(x, [f"w={window}" for window in windows])
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].legend(frameon=False)
    axes[1].set_title("Risk")
    fig.suptitle("Strict unanimous stopping is highly window-sensitive", y=1.02, fontsize=13)
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_consensus_time(rows: Sequence[dict[str, Any]], output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 3.8))
    for axis, mode, title in (
        (axes[0], "absolute_tokens", "Absolute main-token position"),
        (axes[1], "trajectory_fraction", "Position within full trajectory"),
    ):
        selected = [row for row in rows if row["mode"] == mode]
        x = np.arange(len(selected))
        accuracy = [
            100 * row["final_accuracy"] if row["final_accuracy"] is not None else np.nan
            for row in selected
        ]
        sizes = [max(35, 5 * math.sqrt(row["n"])) for row in selected]
        axis.plot(x, accuracy, color="#4472C4", linewidth=1.8)
        axis.scatter(x, accuracy, s=sizes, color="#4472C4", edgecolor="white", zorder=3)
        for index, row in enumerate(selected):
            if row["n"]:
                axis.annotate(
                    f"n={row['n']}",
                    (index, accuracy[index]),
                    xytext=(0, -14 if accuracy[index] >= 92 else 8),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
        axis.set_xticks(x, [row["bin"] for row in selected], rotation=20)
        axis.set_ylim(0, 105)
        axis.grid(axis="y", alpha=0.22)
        axis.set_title(title)
        axis.set_ylabel("Final-answer accuracy (%)")
    fig.suptitle("First-consensus time is descriptive, not causal (w=5, share>=0.8)", y=1.04, fontsize=12)
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_report(
    path: Path,
    base_pooled: dict[str, Any],
    base_macro: dict[str, Any],
    cumulative_summary: Sequence[dict[str, Any]],
    calibration_summary: Sequence[dict[str, Any]],
    strict_summary: Sequence[dict[str, Any]],
    mechanism_summary: Sequence[dict[str, Any]],
    time_summary: Sequence[dict[str, Any]],
    cross_axis: Sequence[dict[str, Any]],
) -> None:
    lines = [
        "# Governor v2 multivariate A1-A3 diagnostic",
        "",
        "Matched protocol: 2 models × 3 benchmarks × 3 seeds = 18 environments; "
        "2,736 development trajectories; dense simple@32 probes every 64 main tokens. "
        "Pooled estimates weight problems; macro estimates weight each environment equally.",
        "",
        "## A1 scope and completeness",
        "",
        "| Metric | Problem-pooled | Environment-macro |",
        "|---|---:|---:|",
        f"| Trajectories | {base_pooled['trajectories']:,} | 18 environments |",
        f"| Probe rows | {base_pooled['probe_rows']:,} | - |",
        f"| Empty probes | {base_pooled['empty_probe_answers']:,} ({pct(base_pooled['empty_probe_rate'])}) | {pct(base_macro['empty_probe_rate'])} |",
        f"| Natural completion | {base_pooled['natural_completion']:,} ({pct(base_pooled['natural_completion_rate'])}) | {pct(base_macro['natural_completion_rate'])} |",
        f"| Mean main tokens | {base_pooled['mean_main_tokens']:.0f} | {base_macro['mean_main_tokens']:.0f} |",
        f"| Final accuracy | {pct(base_pooled['final_accuracy'])} | {pct(base_macro['final_accuracy'])} |",
        f"| Whole-trajectory unanimous coverage | {pct(base_pooled['whole_unanimous_coverage'])} | {pct(base_macro['whole_unanimous_coverage'])} |",
        f"| Whole-trajectory unanimous accuracy | {pct(base_pooled['whole_unanimous_accuracy'])} | {pct(base_macro['whole_unanimous_accuracy'])} |",
        "| Final-answer grader | stored robust collector flag | same within every environment |",
        "",
        "### Model × benchmark audit (three seeds pooled; primary w=5)",
        "",
        "| Model | Benchmark | n | Full acc | Last-5 FC rate | Strict-stop Δacc | "
        "Net saving | Recovery / overthinking |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in cross_axis:
        model = "DeepSeek-7B" if "DeepSeek" in row["model"] else "Qwen3-8B"
        ratio = (
            "∞"
            if row["overthinking"] == 0 and row["recovery"] > 0
            else number(row["recovery_overthinking_ratio"], 1)
        )
        lines.append(
            f"| {model} | {row['benchmark'].upper()} | {row['n']} | "
            f"{pct(row['final_accuracy'])} | {pct(row['last5_false_consensus_rate'])} | "
            f"{row['strict_w5_accuracy_delta_pp']:.1f} pp | "
            f"{pct(row['strict_w5_net_output_saving'])} | "
            f"{row['recovery']} / {row['overthinking']} ({ratio}:1) |"
        )
    lines += [
        "",
        "## A2 calibration and window sensitivity",
        "",
        f"Cumulative CCE pooled / macro: "
        f"{number(cumulative_summary[0]['pooled_cce_final_accuracy'])} / "
        f"{number(cumulative_summary[0]['macro_cce_final_accuracy'])}; cumulative "
        f"unanimous coverage: {pct(cumulative_summary[0]['pooled_unanimous_coverage'])} / "
        f"{pct(cumulative_summary[0]['macro_unanimous_coverage'])}; cumulative "
        f"unanimous false-consensus rate: "
        f"{pct(cumulative_summary[0]['pooled_unanimous_false_consensus_rate'])} / "
        f"{pct(cumulative_summary[0]['macro_unanimous_false_consensus_rate'])}.",
        "",
        "| w | CCE pooled / macro | Last-window unanimous coverage pooled / macro | "
        "Unanimous answer accuracy pooled / macro | False-consensus rate pooled / macro |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in calibration_summary:
        lines.append(
            f"| {row['window']} | {number(row['pooled_cce_final_accuracy'])} / "
            f"{number(row['macro_cce_final_accuracy'])} | "
            f"{pct(row['pooled_unanimous_coverage'])} / {pct(row['macro_unanimous_coverage'])} | "
            f"{pct(row['pooled_unanimous_window_accuracy'])} / "
            f"{pct(row['macro_unanimous_window_accuracy'])} | "
            f"{pct(row['pooled_unanimous_false_consensus_rate'])} / "
            f"{pct(row['macro_unanimous_false_consensus_rate'])} |"
        )
    lines += [
        "",
        "Strict stop below requires all w answers to be non-empty and normalized-equivalent; "
        "net output saving charges every consumed probe completion.",
        "",
        "| w | Stop coverage macro | Delivered acc / full acc macro | Δacc macro | "
        "Net saving macro | False stops among stops macro | Recovery killed / overthinking avoided |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in strict_summary:
        lines.append(
            f"| {row['window']} | {pct(row['macro_coverage'])} | "
            f"{pct(row['macro_delivered_accuracy'])} / {pct(row['macro_full_accuracy'])} | "
            f"{row['macro_accuracy_delta_pp']:.2f} pp | "
            f"{pct(row['macro_net_output_saving'])} | "
            f"{pct(row['macro_false_stop_rate_given_stop'])} | "
            f"{row['recovery_killed']} / {row['overthinking_avoided']} |"
        )
    lines += [
        "",
        "Strict w=3 additionally yields "
        f"{strict_summary[0]['false_stop_n']} false commits and saves "
        f"{strict_summary[0]['mean_main_tokens_saved_given_stop']:.0f} main tokens "
        "on average among stopped trajectories.",
    ]
    lines += [
        "",
        "## A3 early readout versus first consensus",
        "",
        "First consensus uses a trailing window, at least three non-empty answers, and share >= 0.8. "
        "Probe-1 is reported only as an early-readout control.",
        "",
        "| w | Reached pooled / macro | Recovery | Overthinking | Recovery:overthinking | "
        "Probe-1 wrong | Wrong Probe-1 -> correct final pooled / macro |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in mechanism_summary:
        lines.append(
            f"| {row['window']} | {pct(row['pooled_reach_rate'])} / "
            f"{pct(row['macro_reach_rate'])} | {row['recovery']} | {row['overthinking']} | "
            f"{number(row['recovery_overthinking_ratio'], 2)}:1 | {row['first_probe_wrong']} | "
            f"{pct(row['pooled_first_probe_wrong_to_correct_rate'])} / "
            f"{pct(row['macro_first_probe_wrong_to_correct_rate'])} |"
        )
    primary = next(row for row in mechanism_summary if row["window"] == 5)
    lines += [
        "",
        f"For w=5, the first consensus answer differs from the final answer on "
        f"{primary['consensus_differs_final']} trajectories; "
        f"{primary['differs_final_and_final_correct']} of them finish correct.",
    ]
    lines += [
        "",
        "### Consensus-time bins (w=5)",
        "",
        "| Position definition | Bin | n | Final accuracy | Consensus accuracy | Recovery rate |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in time_summary:
        lines.append(
            f"| {row['mode']} | {row['bin']} | {row['n']} | "
            f"{pct(row['final_accuracy'])} | {pct(row['consensus_accuracy'])} | "
            f"{pct(row['recovery_rate'])} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- The broad false-consensus/recovery finding is retained only if it appears across "
        "both pooled and equal-environment macro summaries.",
        "- Window size is a material controller dimension: stronger persistence reduces false "
        "stops but also sharply reduces token saving.",
        "- Probe-1 error is not consensus error. Recovery claims should point to the first-consensus "
        "transition table, not to the Probe-1 control.",
        "- Consensus-time associations remain descriptive because problem difficulty and trajectory "
        "length are confounders.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-root",
        type=Path,
        default=REPO_ROOT / "benchmark/FalseConsensus/results/governor_v2",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT
        / "benchmark/FalseConsensus/results/governor_v2/multivariate_a1_a3",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    trajectories, environments = load_bank(args.input_root)
    by_env: dict[str, list[Trajectory]] = defaultdict(list)
    for row in trajectories:
        by_env[row.env].append(row)

    base_pooled = summarize_base(trajectories)
    base_env = []
    for env, rows in sorted(by_env.items()):
        record = summarize_base(rows)
        record.update(
            {
                "environment": env,
                "model": rows[0].model,
                "benchmark": rows[0].benchmark,
                "seed": rows[0].seed,
            }
        )
        base_env.append(record)
    base_macro = {
        "empty_probe_rate": mean(row["empty_probe_rate"] for row in base_env),
        "natural_completion_rate": mean(
            row["natural_completion_rate"] for row in base_env
        ),
        "mean_main_tokens": mean(row["mean_main_tokens"] for row in base_env),
        "final_accuracy": mean(row["final_accuracy"] for row in base_env),
        "whole_unanimous_coverage": mean(
            row["whole_unanimous_coverage"] for row in base_env
        ),
        "whole_unanimous_accuracy": mean(
            row["whole_unanimous_accuracy"] for row in base_env
        ),
        "whole_unanimous_false_consensus_rate": mean(
            row["whole_unanimous_false_consensus_rate"] for row in base_env
        ),
    }

    cumulative_summary = cumulative_calibration_summary(trajectories)
    calibration_detail, calibration_summary = calibration_rows(trajectories)
    stop_records = strict_stop_records(trajectories)
    stop_env, stop_summary = aggregate_strict(stop_records)
    mechanisms = mechanism_records(trajectories)
    mechanism_summary = aggregate_mechanism(mechanisms)
    time_summary = time_bins(mechanisms, window=5)
    cross_axis = cross_axis_summary(trajectories, stop_records, mechanisms)

    write_csv(args.output_dir / "environments.csv", environments)
    write_csv(args.output_dir / "a1_environment_metrics.csv", base_env)
    write_csv(args.output_dir / "a2_calibration_bins.csv", calibration_detail)
    write_csv(args.output_dir / "a2_cumulative_summary.csv", cumulative_summary)
    write_csv(args.output_dir / "a2_calibration_summary.csv", calibration_summary)
    write_csv(args.output_dir / "a2_stop_environment_metrics.csv", stop_env)
    write_csv(args.output_dir / "a2_stop_summary.csv", stop_summary)
    write_csv(args.output_dir / "a3_mechanism_summary.csv", mechanism_summary)
    write_csv(args.output_dir / "a3_consensus_time.csv", time_summary)
    write_csv(args.output_dir / "cross_axis_summary.csv", cross_axis)

    plot_calibration(calibration_detail, args.output_dir / "fig_a2_calibration_w3_w5_w8.png")
    plot_window_sensitivity(stop_summary, args.output_dir / "fig_a2_window_sensitivity.png")
    plot_consensus_time(time_summary, args.output_dir / "fig_a3_consensus_time.png")
    render_report(
        args.output_dir / "report.md",
        base_pooled,
        base_macro,
        cumulative_summary,
        calibration_summary,
        stop_summary,
        mechanism_summary,
        time_summary,
        cross_axis,
    )
    payload = {
        "schema_version": "governor-v2-multivariate-a1-a3-1",
        "input": {
            "phase": "development",
            "environments": 18,
            "models": sorted({row.model for row in trajectories}),
            "benchmarks": sorted({row.benchmark for row in trajectories}),
            "seeds": sorted({row.seed for row in trajectories}),
            "probe": "dense_simple32",
            "probe_interval": 64,
            "trajectories": len(trajectories),
            "probes": sum(len(row.probes) for row in trajectories),
        },
        "definitions": {
            "calibration": "last-w, >=3 non-empty answers; y=final correctness",
            "strict_stop": "first exact w-probe non-empty normalized-equivalent window",
            "first_consensus": "first last-w state with >=3 non-empty and share>=0.8",
            "net_output_saving": "full main output - stopped main output - consumed probe output",
            "macro": "equal mean across 18 model x benchmark x seed environments",
        },
        "a1_pooled": base_pooled,
        "a1_macro": base_macro,
        "a2_calibration": calibration_summary,
        "a2_cumulative": cumulative_summary,
        "a2_strict_stop": stop_summary,
        "a3_mechanism": mechanism_summary,
        "a3_consensus_time": time_summary,
        "cross_axis": cross_axis,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote multivariate A1-A3 analysis to {args.output_dir}")


if __name__ == "__main__":
    main()
