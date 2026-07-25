#!/usr/bin/env python3
"""Evaluate one frozen simple@32 logging run without tuning on its results.

The primary Governor configurations come from protocol.json. Baseline sweeps
and the 2x2x2x2 factorial are predeclared comparisons, not a search that may
replace the frozen primary configurations.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
FC_DIR = HERE.parent
UNTOUCHED_PROTOCOL = HERE / "untouched_protocol.json"
THIRD_MODEL_PROTOCOL = HERE / "third_model_protocol.json"
sys.path.insert(0, str(FC_DIR / "replay"))

import sweep_stop_rules_v2 as rules  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    parser.add_argument(
        "--difficulty-csv",
        type=Path,
        default=FC_DIR
        / "results/stage9_difficulty/per_problem_with_difficulty.csv",
    )
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260725)
    parser.add_argument("--model", default=None, help="legacy-run override")
    parser.add_argument("--seed", type=int, default=None, help="legacy-run override")
    parser.add_argument(
        "--allow-partial-smoke",
        action="store_true",
        help="allow a deliberately incomplete run for isolated smoke testing",
    )
    return parser.parse_args()


def frozen_config(name: str, spec: dict) -> dict:
    config = dict(spec)
    config["config_id"] = name
    return config


def load_problems(
    run_dir: Path, difficulty_csv: Path
) -> tuple[dict[int, dict], pd.DataFrame]:
    probes = pd.read_csv(run_dir / "probes.csv", keep_default_na=False)
    trajectories = rules.load_trajectories(run_dir / "traj")
    if not trajectories:
        raise ValueError(f"No trajectories found under {run_dir / 'traj'}")
    duplicate_probes = probes.duplicated(["problem_id", "probe_id"], keep=False)
    if duplicate_probes.any():
        examples = (
            probes.loc[duplicate_probes, ["problem_id", "probe_id"]]
            .drop_duplicates()
            .head()
            .to_dict("records")
        )
        raise ValueError(f"Duplicate probe rows detected: {examples}")
    unknown_probe_ids = set(probes["problem_id"].astype(int)) - set(
        trajectories
    )
    if unknown_probe_ids:
        raise ValueError(
            "probes.csv contains problem IDs without trajectories: "
            f"{sorted(unknown_probe_ids)[:10]}"
        )
    difficulty = None
    if difficulty_csv.exists():
        difficulty = pd.read_csv(
            difficulty_csv, keep_default_na=False
        ).set_index("problem_id")
    problems = {}
    grouped_probes = {
        int(pid): stream for pid, stream in probes.groupby("problem_id")
    }
    for pid, trajectory in sorted(trajectories.items()):
        stream = grouped_probes.get(pid, probes.iloc[0:0].copy())
        trajectory = trajectories[pid]
        if (
            trajectory.get("dataset") == "math500"
            and difficulty is not None
            and pid in difficulty.index
        ):
            level = int(difficulty.loc[pid]["level"])
            subject = str(difficulty.loc[pid]["subject"])
        else:
            level = int(trajectory.get("level", 0))
            subject = str(
                trajectory.get("subject", trajectory.get("dataset", "unknown"))
            )
        default_probe_cost = int(
            trajectory.get("run_settings", {}).get("probe_tokens", 10)
        )
        problem = rules.prepare_problem(
            pid,
            stream,
            trajectory,
            level,
            subject,
            default_probe_cost=default_probe_cost,
        )
        if trajectory.get("dataset") == "gsm8k":
            numeric_ids = [
                answer_id
                if re.fullmatch(r"-?(?:\d+(?:\.\d+)?|\.\d+)", answer)
                else -1
                for answer, answer_id in zip(
                    problem["answers"], problem["validity"]["nonempty"]
                )
            ]
            problem["validity"]["schema"] = numeric_ids
            (
                problem["switches"]["schema"],
                problem["stable_spans"]["schema"],
            ) = rules.history_features(problem["tokens"], numeric_ids)
            problem["online_hard"]["schema"] = rules.online_hard(numeric_ids)
        problems[pid] = problem
    for pid, problem in problems.items():
        trajectory = trajectories[pid]
        problem["accounting"] = trajectory.get("accounting", {})
        problem["probe_records"] = trajectory.get("probes", [])
        problem["finished_naturally"] = bool(
            trajectory.get("finished_naturally", False)
        )
        problem["run_settings"] = trajectory.get("run_settings", {})
        problem["dataset"] = trajectory.get("dataset", "")
    return problems, probes


def validate_registered_run(
    problems: dict[int, dict],
    probes: pd.DataFrame,
    protocol: dict,
    *,
    allow_partial_smoke: bool,
) -> tuple[str, dict]:
    first_pid = min(problems)
    first = problems[first_pid]
    dataset = str(
        first["run_settings"].get("dataset", first.get("dataset", ""))
    )
    settings = first["run_settings"]
    required_setting_keys = {
        "model",
        "dataset",
        "budget",
        "probe_interval",
        "probe_tokens",
        "probe_suffix_style",
        "temperature",
        "top_p",
        "base_seed",
    }
    missing = required_setting_keys - set(settings)
    if missing:
        raise ValueError(
            f"Trajectory {first_pid} lacks run settings: {sorted(missing)}"
        )
    for pid, problem in problems.items():
        if problem.get("dataset") != dataset:
            raise ValueError(
                f"Mixed datasets: problem {pid} has {problem.get('dataset')}, "
                f"expected {dataset}"
            )
        candidate = problem["run_settings"]
        differences = {
            key: (settings.get(key), candidate.get(key))
            for key in required_setting_keys
            if settings.get(key) != candidate.get(key)
        }
        if differences:
            raise ValueError(
                f"Mixed run settings at problem {pid}: {differences}"
            )

    if "dataset" in probes and len(probes):
        if set(probes["dataset"].astype(str)) != {dataset}:
            raise ValueError("probes.csv contains mixed datasets")
    if "model" in probes and len(probes):
        if set(probes["model"].astype(str)) != {str(settings["model"])}:
            raise ValueError("probes.csv contains mixed models")
    if "base_seed" in probes and len(probes):
        csv_seeds = set(pd.to_numeric(probes["base_seed"]).astype(int))
        if csv_seeds != {int(settings["base_seed"])}:
            raise ValueError("probes.csv contains mixed base seeds")

    third = json.loads(THIRD_MODEL_PROTOCOL.read_text())
    untouched = json.loads(UNTOUCHED_PROTOCOL.read_text())
    if dataset == protocol["dataset"]:
        if settings["model"] in protocol["models"]:
            registered_generation = protocol["generation"]
        elif settings["model"] == third["model"]:
            registered_generation = third["generation"]
        else:
            raise ValueError(
                f"Unregistered model for {dataset}: {settings['model']}"
            )
        expected_count = int(protocol["problem_ids"]["end_exclusive"])
        expected_ids = set(
            range(
                int(protocol["problem_ids"]["start"]),
                int(protocol["problem_ids"]["end_exclusive"]),
            )
        )
    elif dataset == untouched["dataset"]["name"]:
        if settings["model"] not in untouched["models"]:
            raise ValueError(
                f"Unregistered model for {dataset}: {settings['model']}"
            )
        registered_generation = untouched["generation"]
        count_match = re.search(
            r"\d+", str(untouched["dataset"]["examples"])
        )
        if count_match is None:
            raise ValueError("GSM8K protocol does not declare example count")
        expected_count = int(count_match.group())
        expected_ids = set(range(expected_count))
    else:
        raise ValueError(f"Dataset is not registered for final evaluation: {dataset}")

    expected_generation = {
        "budget": int(registered_generation["max_reasoning_tokens"]),
        "temperature": float(registered_generation["temperature"]),
        "top_p": float(registered_generation["top_p"]),
    }
    generation_mismatches = {
        key: (expected, settings.get(key))
        for key, expected in expected_generation.items()
        if settings.get(key) != expected
    }
    if int(settings["base_seed"]) not in {
        int(seed) for seed in registered_generation["seeds"]
    }:
        generation_mismatches["base_seed"] = (
            registered_generation["seeds"],
            settings["base_seed"],
        )
    if generation_mismatches:
        raise ValueError(
            f"Run violates registered generation settings: "
            f"{generation_mismatches}"
        )

    stream = (
        str(settings["probe_suffix_style"]),
        int(settings["probe_interval"]),
        int(settings["probe_tokens"]),
    )
    simple_stream = (
        str(protocol["probing"]["suffix_style"]),
        int(protocol["probing"]["interval"]),
        int(protocol["probing"]["probe_output_cap"]),
    )
    registered_streams = {simple_stream}
    if (
        dataset == protocol["dataset"]
        and settings["model"] in protocol["models"]
    ):
        for spec in protocol["formal_baselines"].values():
            registered_streams.add(
                (
                    str(spec["probe_suffix_style"]),
                    int(spec["probe_interval"]),
                    int(spec["probe_output_cap"]),
                )
            )
    if stream not in registered_streams:
        raise ValueError(
            f"Unregistered probe stream {stream}; expected one of "
            f"{sorted(registered_streams)}"
        )

    observed_ids = set(problems)
    if allow_partial_smoke:
        if not observed_ids <= expected_ids:
            raise ValueError("Smoke run contains out-of-range problem IDs")
    elif len(problems) != expected_count or observed_ids != expected_ids:
        missing_ids = sorted(expected_ids - observed_ids)
        unexpected_ids = sorted(observed_ids - expected_ids)
        raise ValueError(
            f"Frozen {dataset} evaluation requires {expected_count} exact "
            f"problem IDs; got {len(problems)}. Missing "
            f"{missing_ids[:10]}, unexpected {unexpected_ids[:10]}"
        )
    return dataset, settings


def sum_metric(records: list[dict], key: str, end: int) -> float:
    values = [record.get(key) for record in records[: end + 1]]
    if any(value is None for value in values):
        return math.nan
    return float(sum(values))


def accounting_for(
    problem: dict,
    stop_index: int | None,
    *,
    fixed_budget: bool = False,
) -> dict:
    accounting = problem["accounting"]
    records = problem["probe_records"]
    if stop_index is None:
        return {
            "main_prompt_tokens": accounting.get(
                "main_prompt_tokens", math.nan
            ),
            "probe_prompt_tokens": accounting.get(
                "probe_prompt_tokens", math.nan
            ),
            "main_wall_clock_seconds": accounting.get(
                "main_wall_clock_seconds", math.nan
            ),
            "probe_wall_clock_seconds": accounting.get(
                "probe_wall_clock_seconds", math.nan
            ),
            "trajectory_wall_clock_seconds": accounting.get(
                "trajectory_wall_clock_seconds", math.nan
            ),
        }

    main_prompt = sum_metric(records, "main_prompt_tokens", stop_index)
    main_seconds = sum_metric(records, "main_latency_seconds", stop_index)
    if fixed_budget:
        probe_prompt = float(
            records[stop_index].get("probe_prompt_tokens", math.nan)
        )
        probe_seconds = float(
            records[stop_index].get("probe_latency_seconds", math.nan)
        )
    else:
        probe_prompt = sum_metric(records, "probe_prompt_tokens", stop_index)
        probe_seconds = sum_metric(records, "probe_latency_seconds", stop_index)
    return {
        "main_prompt_tokens": main_prompt,
        "probe_prompt_tokens": probe_prompt,
        "main_wall_clock_seconds": main_seconds,
        "probe_wall_clock_seconds": probe_seconds,
        "trajectory_wall_clock_seconds": main_seconds + probe_seconds,
    }


def governor_rows(
    name: str, config: dict, problems: dict[int, dict]
) -> pd.DataFrame:
    frame = rules.evaluate_rows(
        config, problems, set(problems), method=name
    ).copy()
    extras = []
    for pid in frame["problem_id"]:
        problem = problems[int(pid)]
        stop_index, _ = rules.simulate(config, problem)
        if stop_index is None:
            stop_window = []
            stop_token = math.nan
        else:
            patience = int(config.get("patience", 1))
            start = max(0, stop_index - patience + 1)
            stop_window = list(range(start, stop_index + 1))
            stop_token = int(problem["tokens"][stop_index])
        extras.append(
            {
                **accounting_for(problem, stop_index),
                "stop_index": (
                    int(stop_index) if stop_index is not None else math.nan
                ),
                "stop_token": stop_token,
                "stop_invalid_schema_window": bool(
                    stop_window
                    and any(
                        problem["validity"]["schema"][index] < 0
                        for index in stop_window
                    )
                ),
                "stop_before_1024": bool(
                    stop_index is not None and stop_token < 1024
                ),
                "stop_uncertain_window": bool(
                    stop_window
                    and any(
                        not problem["certain"][index]
                        for index in stop_window
                    )
                ),
            }
        )
    return pd.concat([frame.reset_index(drop=True), pd.DataFrame(extras)], axis=1)


def full_rows(problems: dict[int, dict]) -> pd.DataFrame:
    frame = rules.evaluate_rows(
        None, problems, set(problems), method="full_generation"
    ).copy()
    extras = []
    for pid in frame["problem_id"]:
        extra = accounting_for(problems[int(pid)], None)
        extra["probe_prompt_tokens"] = 0
        extra["probe_wall_clock_seconds"] = 0.0
        extra["trajectory_wall_clock_seconds"] = extra[
            "main_wall_clock_seconds"
        ]
        extras.append(extra)
    return pd.concat([frame.reset_index(drop=True), pd.DataFrame(extras)], axis=1)


def fixed_budget_rows(
    cap: int, problems: dict[int, dict]
) -> pd.DataFrame:
    rows = []
    for pid in sorted(problems):
        problem = problems[pid]
        if problem["full_tokens"] <= cap and problem["finished_naturally"]:
            stopped = False
            delivered_correct = bool(problem["final_correct"])
            stop_correct = None
            main_tokens = problem["full_tokens"]
            probe_tokens = 0
            stop_index = None
            extra = accounting_for(problem, None)
            extra["probe_prompt_tokens"] = 0
            extra["probe_wall_clock_seconds"] = 0.0
            extra["trajectory_wall_clock_seconds"] = extra[
                "main_wall_clock_seconds"
            ]
        else:
            eligible = [
                index
                for index, token in enumerate(problem["tokens"])
                if token >= cap
            ]
            if not eligible:
                stop_index = len(problem["tokens"]) - 1
            else:
                stop_index = eligible[0]
            answer_id = problem["validity"]["nonempty"][stop_index]
            stop_correct = bool(
                answer_id >= 0
                and problem["representative_correct"].get(answer_id, False)
            )
            delivered_correct = stop_correct
            stopped = True
            main_tokens = problem["tokens"][stop_index]
            probe_tokens = problem["probe_costs"][stop_index]
            extra = accounting_for(problem, stop_index, fixed_budget=True)
        rows.append(
            {
                "method": f"fixed_budget_{cap}",
                "config_id": f"fixed_budget_{cap}",
                "problem_id": pid,
                "level": problem["level"],
                "subject": problem["subject"],
                "delivered_correct": delivered_correct,
                "final_correct": problem["final_correct"],
                "stopped": stopped,
                "stop_correct": stop_correct,
                "main_tokens": main_tokens,
                "probe_tokens": probe_tokens,
                "probe_calls": int(stopped),
                "total_tokens": main_tokens + probe_tokens,
                "recovery_truncated": bool(
                    stopped and problem["final_correct"] and not stop_correct
                ),
                "overthinking_avoided": bool(
                    stopped and stop_correct and not problem["final_correct"]
                ),
                **extra,
            }
        )
    return pd.DataFrame(rows)


def entropy_stop(
    problem: dict, threshold: float, minimum: int, patience: int
) -> tuple[int | None, int | None]:
    ids = problem["validity"]["nonempty"]
    for end in range(patience - 1, len(ids)):
        if problem["tokens"][end] < minimum:
            continue
        window = ids[end - patience + 1 : end + 1]
        if any(answer_id < 0 for answer_id in window):
            continue
        counts = Counter(ids[: end + 1])
        counts.pop(-1, None)
        n = sum(counts.values())
        if not n:
            continue
        probabilities = [count / n for count in counts.values()]
        entropy = -sum(p * math.log(p, 2) for p in probabilities)
        normalized = entropy / math.log(n, 2) if n > 1 else 0.0
        if normalized <= threshold:
            return end, counts.most_common(1)[0][0]
    return None, None


def majority_stop(
    problem: dict, window: int, share: float
) -> tuple[int | None, int | None]:
    ids = problem["validity"]["nonempty"]
    for end in range(window - 1, len(ids)):
        values = ids[end - window + 1 : end + 1]
        valid = [answer_id for answer_id in values if answer_id >= 0]
        if not valid:
            continue
        answer_id, count = Counter(valid).most_common(1)[0]
        if count / len(valid) >= share:
            return end, answer_id
    return None, None


def custom_rows(
    name: str,
    problems: dict[int, dict],
    simulator,
) -> pd.DataFrame:
    rows = []
    for pid in sorted(problems):
        problem = problems[pid]
        stop_index, answer_id = simulator(problem)
        stopped = stop_index is not None
        if stopped:
            stop_correct = bool(
                answer_id is not None
                and problem["representative_correct"].get(answer_id, False)
            )
            delivered_correct = stop_correct
            main_tokens = problem["tokens"][stop_index]
            probe_tokens = sum(problem["probe_costs"][: stop_index + 1])
            probe_calls = stop_index + 1
        else:
            stop_correct = None
            delivered_correct = bool(problem["final_correct"])
            main_tokens = problem["full_tokens"]
            probe_tokens = sum(problem["probe_costs"])
            probe_calls = len(problem["probe_costs"])
        rows.append(
            {
                "method": name,
                "config_id": name,
                "problem_id": pid,
                "level": problem["level"],
                "subject": problem["subject"],
                "delivered_correct": delivered_correct,
                "final_correct": problem["final_correct"],
                "stopped": stopped,
                "stop_correct": stop_correct,
                "main_tokens": main_tokens,
                "probe_tokens": probe_tokens,
                "probe_calls": probe_calls,
                "total_tokens": main_tokens + probe_tokens,
                "recovery_truncated": bool(
                    stopped and problem["final_correct"] and not stop_correct
                ),
                "overthinking_avoided": bool(
                    stopped and stop_correct and not problem["final_correct"]
                ),
                **accounting_for(problem, stop_index),
            }
        )
    return pd.DataFrame(rows)


def summarize(frame: pd.DataFrame) -> dict:
    stopped = frame[frame["stopped"]]
    result = {
        "method": str(frame["method"].iloc[0]),
        "n": int(len(frame)),
        "accuracy": float(frame["delivered_correct"].mean()),
        "mean_main_tokens": float(frame["main_tokens"].mean()),
        "mean_probe_decode_tokens": float(frame["probe_tokens"].mean()),
        "mean_total_generated_tokens": float(frame["total_tokens"].mean()),
        "mean_probe_calls": float(frame["probe_calls"].mean()),
        "stop_coverage": float(frame["stopped"].mean()),
        "false_stop_rate": (
            float(1 - stopped["stop_correct"].astype(bool).mean())
            if len(stopped)
            else math.nan
        ),
        "recovery_killed": int(frame["recovery_truncated"].sum()),
        "overthinking_prevented": int(
            frame["overthinking_avoided"].sum()
        ),
    }
    for column in [
        "main_prompt_tokens",
        "probe_prompt_tokens",
        "trajectory_wall_clock_seconds",
    ]:
        result[f"mean_{column}"] = float(
            pd.to_numeric(frame[column], errors="coerce").mean()
        )
    return result


def paired_intervals(
    summaries: pd.DataFrame,
    details: pd.DataFrame,
    bootstrap: int,
    seed: int,
) -> pd.DataFrame:
    summaries = summaries.copy()
    baseline = (
        details[details["method"] == "full_generation"]
        .sort_values("problem_id")
        .reset_index(drop=True)
    )
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(baseline), size=(bootstrap, len(baseline)))
    columns = [
        "accuracy_diff_vs_full",
        "accuracy_diff_ci_lo",
        "accuracy_diff_ci_hi",
        "total_token_saving_vs_full",
        "token_saving_ci_lo",
        "token_saving_ci_hi",
        "mcnemar_discordant_full_only",
        "mcnemar_discordant_method_only",
        "mcnemar_exact_p",
    ]
    for column in columns:
        summaries[column] = math.nan

    base_acc = baseline["delivered_correct"].astype(float).to_numpy()
    base_tok = baseline["total_tokens"].astype(float).to_numpy()
    for row_index, summary in summaries.iterrows():
        method_name = summary["method"]
        method = (
            details[details["method"] == method_name]
            .sort_values("problem_id")
            .reset_index(drop=True)
        )
        if not np.array_equal(
            baseline["problem_id"].to_numpy(),
            method["problem_id"].to_numpy(),
        ):
            raise ValueError(
                f"Unpaired problem rows for method {method_name}"
            )
        method_acc = method["delivered_correct"].astype(float).to_numpy()
        method_tok = method["total_tokens"].astype(float).to_numpy()
        accuracy_samples = (
            method_acc[indices].mean(axis=1)
            - base_acc[indices].mean(axis=1)
        )
        saving_samples = 1 - (
            method_tok[indices].mean(axis=1)
            / base_tok[indices].mean(axis=1)
        )
        full_only = int(((base_acc == 1) & (method_acc == 0)).sum())
        method_only = int(((base_acc == 0) & (method_acc == 1)).sum())
        discordant = full_only + method_only
        if discordant:
            tail = min(full_only, method_only)
            exact_p = min(
                1.0,
                2
                * sum(
                    math.comb(discordant, k) * 0.5**discordant
                    for k in range(tail + 1)
                ),
            )
        else:
            exact_p = 1.0
        summaries.loc[row_index, columns] = [
            method_acc.mean() - base_acc.mean(),
            *np.quantile(accuracy_samples, [0.025, 0.975]),
            1 - method_tok.mean() / base_tok.mean(),
            *np.quantile(saving_samples, [0.025, 0.975]),
            full_only,
            method_only,
            exact_p,
        ]
    return summaries


def factorial_configs() -> list[dict]:
    configs = []
    for schema in [False, True]:
        for maturity in [False, True]:
            for certainty in [False, True]:
                for persistent in [False, True]:
                    name = (
                        f"factorial_schema{int(schema)}_"
                        f"maturity{int(maturity)}_"
                        f"certain{int(certainty)}_"
                        f"persistent{int(persistent)}"
                    )
                    configs.append(
                        {
                            "config_id": name,
                            "family": "consecutive",
                            "patience": 8 if persistent else 3,
                            "floor_kind": "fixed",
                            "easy_min": 1024 if maturity else 0,
                            "hard_min": 1024 if maturity else 0,
                            "require_certain": certainty,
                            "validity_mode": (
                                "schema" if schema else "nonempty"
                            ),
                            "schema_on": schema,
                            "maturity_on": maturity,
                            "certainty_on": certainty,
                            "persistence_on": persistent,
                        }
                    )
    return configs


def factorial_effects(summary: pd.DataFrame) -> pd.DataFrame:
    components = {
        "schema": ("schema_on", "filters invalid readouts"),
        "maturity": ("maturity_on", "suppresses premature guesses"),
        "certainty": ("certainty_on", "excludes active self-correction"),
        "persistence": (
            "persistence_on",
            "separates transient from terminal consensus",
        ),
    }
    flag_columns = [value[0] for value in components.values()]
    metrics = [
        "accuracy",
        "mean_total_generated_tokens",
        "stop_coverage",
        "false_stop_rate",
        "recovery_killed",
        "overthinking_prevented",
    ]
    contrasts = []
    for component, (flag, failure_mode) in components.items():
        other_flags = [column for column in flag_columns if column != flag]
        for values, group in summary.groupby(other_flags, dropna=False):
            off = group[~group[flag].astype(bool)]
            on = group[group[flag].astype(bool)]
            if len(off) != 1 or len(on) != 1:
                raise ValueError(f"Unmatched factorial contrast for {component}")
            row = {
                "component": component,
                "targeted_failure_mode": failure_mode,
                "context": json.dumps(
                    dict(zip(other_flags, np.atleast_1d(values).tolist())),
                    sort_keys=True,
                ),
                "off_method": str(off.iloc[0]["method"]),
                "on_method": str(on.iloc[0]["method"]),
            }
            for metric in metrics:
                row[f"{metric}_on_minus_off"] = float(
                    on.iloc[0][metric] - off.iloc[0][metric]
                )
            contrasts.append(row)
    return pd.DataFrame(contrasts)


def factorial_failure_modes(
    details: pd.DataFrame, metadata: pd.DataFrame
) -> pd.DataFrame:
    annotated = details.merge(
        metadata, on="method", validate="many_to_one"
    )
    components = {
        "schema": ("schema_on", "stop_invalid_schema_window"),
        "maturity": ("maturity_on", "stop_before_1024"),
        "certainty": ("certainty_on", "stop_uncertain_window"),
        "persistence": ("persistence_on", "recovery_truncated"),
    }
    flag_columns = [value[0] for value in components.values()]
    rows = []
    for component, (flag, targeted_column) in components.items():
        other_flags = [column for column in flag_columns if column != flag]
        for values, group in annotated.groupby(other_flags, dropna=False):
            off = (
                group[~group[flag].astype(bool)]
                .sort_values("problem_id")
                .reset_index(drop=True)
            )
            on = (
                group[group[flag].astype(bool)]
                .sort_values("problem_id")
                .reset_index(drop=True)
            )
            if len(off) != len(on) or not np.array_equal(
                off["problem_id"].to_numpy(), on["problem_id"].to_numpy()
            ):
                raise ValueError(
                    f"Unpaired factorial problem rows for {component}"
                )
            off_false = off["stopped"].astype(bool) & ~off[
                "stop_correct"
            ].fillna(False).astype(bool)
            on_false = on["stopped"].astype(bool) & ~on[
                "stop_correct"
            ].fillna(False).astype(bool)
            targeted = off[targeted_column].fillna(False).astype(bool)
            rows.append(
                {
                    "component": component,
                    "context": json.dumps(
                        dict(
                            zip(
                                other_flags,
                                np.atleast_1d(values).tolist(),
                            )
                        ),
                        sort_keys=True,
                    ),
                    "off_method": str(off["method"].iloc[0]),
                    "on_method": str(on["method"].iloc[0]),
                    "n_problems": int(len(off)),
                    "off_false_stops": int(off_false.sum()),
                    "on_false_stops": int(on_false.sum()),
                    "false_stops_removed": int(
                        (off_false & ~on_false).sum()
                    ),
                    "targeted_off_stops": int(targeted.sum()),
                    "targeted_off_false_stops": int(
                        (targeted & off_false).sum()
                    ),
                    "targeted_false_stops_removed": int(
                        (targeted & off_false & ~on_false).sum()
                    ),
                    "targeted_definition": {
                        "schema": (
                            "off-rule stop window contains a "
                            "task-schema-invalid readout"
                        ),
                        "maturity": "off-rule stops before 1024 reasoning tokens",
                        "certainty": (
                            "off-rule stop window contains explicit "
                            "uncertainty"
                        ),
                        "persistence": "off-rule stop kills a later recovery",
                    }[component],
                }
            )
    return pd.DataFrame(rows)


def transition_rows(problems: dict[int, dict]) -> pd.DataFrame:
    """First last-5 consensus with >=3 valid answers and share >= 0.8."""
    columns = [
        "problem_id",
        "level",
        "subject",
        "consensus_token",
        "consensus_share",
        "consensus_correct",
        "final_correct",
        "finished_naturally",
        "hit_token_cap",
        "category",
    ]
    rows = []
    for pid in sorted(problems):
        problem = problems[pid]
        ids = problem["validity"]["nonempty"]
        first = None
        for end in range(len(ids)):
            start = max(0, end - 4)
            valid = [answer_id for answer_id in ids[start : end + 1] if answer_id >= 0]
            if len(valid) < 3:
                continue
            dominant_id, count = Counter(valid).most_common(1)[0]
            if count / len(valid) >= 0.8:
                first = (end, dominant_id, count / len(valid))
                break
        if first is None:
            continue
        end, dominant_id, share = first
        consensus_correct = bool(
            problem["representative_correct"].get(dominant_id, False)
        )
        final_correct = bool(problem["final_correct"])
        if not consensus_correct and final_correct:
            category = "recovery"
        elif consensus_correct and not final_correct:
            category = "overthinking"
        elif consensus_correct:
            category = "stable_correct"
        else:
            category = "persistent_wrong"
        rows.append(
            {
                "problem_id": pid,
                "level": problem["level"],
                "subject": problem["subject"],
                "consensus_token": problem["tokens"][end],
                "consensus_share": share,
                "consensus_correct": consensus_correct,
                "final_correct": final_correct,
                "finished_naturally": problem["finished_naturally"],
                "hit_token_cap": not problem["finished_naturally"],
                "category": category,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def transition_summary(
    transitions: pd.DataFrame, bootstrap: int, seed: int
) -> dict:
    counts = transitions["category"].value_counts()
    recovery = int(counts.get("recovery", 0))
    overthinking = int(counts.get("overthinking", 0))
    if transitions.empty:
        return {
            "definition": {
                "window": 5,
                "minimum_valid_answers": 3,
                "share_threshold": 0.8,
                "validity": "nonempty mathematical answer",
            },
            "reached": 0,
            "not_reached": None,
            "counts": {
                "recovery": 0,
                "overthinking": 0,
                "stable_correct": 0,
                "persistent_wrong": 0,
            },
            "recovery_minus_overthinking_fraction": None,
            "recovery_minus_overthinking_ci": [None, None],
            "recovery_overthinking_ratio_haldane": None,
            "recovery_overthinking_ratio_ci_haldane": [None, None],
        }
    rng = np.random.default_rng(seed)
    category = transitions["category"].to_numpy()
    indices = rng.integers(
        0, len(transitions), size=(bootstrap, len(transitions))
    )
    sampled = category[indices]
    recovery_samples = (sampled == "recovery").sum(axis=1)
    overthinking_samples = (sampled == "overthinking").sum(axis=1)
    difference_samples = (
        recovery_samples - overthinking_samples
    ) / len(transitions)
    ratio_samples = (recovery_samples + 0.5) / (
        overthinking_samples + 0.5
    )
    return {
        "definition": {
            "window": 5,
            "minimum_valid_answers": 3,
            "share_threshold": 0.8,
            "validity": "nonempty mathematical answer",
        },
        "reached": int(len(transitions)),
        "not_reached": None,
        "counts": {
            name: int(counts.get(name, 0))
            for name in [
                "recovery",
                "overthinking",
                "stable_correct",
                "persistent_wrong",
            ]
        },
        "recovery_minus_overthinking_fraction": (
            recovery - overthinking
        )
        / len(transitions),
        "recovery_minus_overthinking_ci": np.quantile(
            difference_samples, [0.025, 0.975]
        ).tolist(),
        "recovery_overthinking_ratio_haldane": (
            recovery + 0.5
        )
        / (overthinking + 0.5),
        "recovery_overthinking_ratio_ci_haldane": np.quantile(
            ratio_samples, [0.025, 0.975]
        ).tolist(),
    }


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text())
    out_dir = args.out_dir or args.run_dir / "final_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    problems, probes = load_problems(args.run_dir, args.difficulty_csv)
    dataset, validated_settings = validate_registered_run(
        problems,
        probes,
        protocol,
        allow_partial_smoke=args.allow_partial_smoke,
    )
    if args.model is not None and args.model != validated_settings["model"]:
        raise ValueError("--model override disagrees with trajectory settings")
    if (
        args.seed is not None
        and int(args.seed) != int(validated_settings["base_seed"])
    ):
        raise ValueError("--seed override disagrees with trajectory settings")
    first_problem = problems[min(problems)]

    stream_style = str(
        first_problem["run_settings"].get("probe_suffix_style", "simple")
    )
    method_frames = [full_rows(problems)]
    for cap in protocol["frozen_methods"]["fixed_budget"]["caps"]:
        method_frames.append(fixed_budget_rows(int(cap), problems))

    configs = {}
    primary_names = []
    if stream_style == "certaindex":
        interval = int(
            first_problem["run_settings"].get("probe_interval", 0)
        )
        probe_tokens = int(
            first_problem["run_settings"].get("probe_tokens", 0)
        )
        if (interval, probe_tokens) == (64, 20):
            certa_name = "certaindex_faithful_mid"
        elif (interval, probe_tokens) == (128, 32):
            certa_name = "certaindex_adapted_simple32"
        else:
            raise ValueError(
                "Unregistered CertaIndex stream: expected interval/probe "
                f"(64,20) or (128,32), got ({interval},{probe_tokens})"
            )
        faithful = {
            "config_id": certa_name,
            "family": "consecutive",
            "patience": 3,
            "floor_kind": "fixed",
            "easy_min": 0,
            "hard_min": 0,
            "require_certain": True,
            "validity_mode": "nonempty",
        }
        method_frames.append(
            governor_rows(
                certa_name,
                faithful,
                problems,
            )
        )
        primary_names = [certa_name]
    else:
        primary_names = ["naive_agreement", "conservative"]
        if dataset == "math500":
            primary_names.append("balanced_math")
        for name in primary_names:
            configs[name] = frozen_config(
                name, protocol["frozen_methods"][name]
            )
            method_frames.append(
                governor_rows(name, configs[name], problems)
            )
        if dataset != "math500":
            balanced_general = dict(
                protocol["non_math_policy"][
                    "optional_general_balanced_candidate"
                ]
            )
            balanced_general.pop("status", None)
            balanced_general["validity_mode"] = "schema"
            configs["balanced_general_secondary"] = frozen_config(
                "balanced_general_secondary", balanced_general
            )
            method_frames.append(
                governor_rows(
                    "balanced_general_secondary",
                    configs["balanced_general_secondary"],
                    problems,
                )
            )
            primary_names.append("balanced_general_secondary")

        # Same 128-token checkpoint schedule with the CertaIndex stop logic.
        # The separately logged 64/20 CertaIndex stream is the faithful result.
        dynasor_logic = {
            "config_id": "dynasor_stop_logic_on_simple32",
            "family": "consecutive",
            "patience": 3,
            "floor_kind": "fixed",
            "easy_min": 0,
            "hard_min": 0,
            "require_certain": True,
            "validity_mode": "nonempty",
        }
        method_frames.append(
            governor_rows(
                "dynasor_stop_logic_on_simple32",
                dynasor_logic,
                problems,
            )
        )

    for threshold in [0.1, 0.2, 0.3, 0.4]:
        for minimum in [0, 512, 1024]:
            for patience in [1, 3, 5]:
                name = (
                    f"entropy_h{threshold}_min{minimum}_p{patience}"
                )
                method_frames.append(
                    custom_rows(
                        name,
                        problems,
                        lambda problem, h=threshold, m=minimum, p=patience: (
                            entropy_stop(problem, h, m, p)
                        ),
                    )
                )

    for window in [3, 5, 8]:
        for share in [0.8, 1.0]:
            name = f"majority_w{window}_share{share}"
            method_frames.append(
                custom_rows(
                    name,
                    problems,
                    lambda problem, w=window, s=share: majority_stop(
                        problem, w, s
                    ),
                )
            )

    primary_details = pd.concat(method_frames, ignore_index=True)
    primary_summary = pd.DataFrame(
        [
            summarize(frame)
            for _, frame in primary_details.groupby("method", sort=False)
        ]
    )
    primary_summary = paired_intervals(
        primary_summary,
        primary_details,
        args.bootstrap,
        args.bootstrap_seed,
    )
    primary_details.to_csv(out_dir / "methods_per_problem.csv", index=False)
    primary_summary.to_csv(out_dir / "methods_summary.csv", index=False)

    if stream_style == "simple":
        factorial_specs = factorial_configs()
        factorial_frames = [
            governor_rows(config["config_id"], config, problems)
            for config in factorial_specs
        ]
        factorial_details = pd.concat(factorial_frames, ignore_index=True)
        factorial_summary = pd.DataFrame(
            [
                summarize(frame)
                for _, frame in factorial_details.groupby(
                    "method", sort=False
                )
            ]
        )
        factorial_metadata = pd.DataFrame(
            [
                {
                    "method": config["config_id"],
                    "schema_on": config["schema_on"],
                    "maturity_on": config["maturity_on"],
                    "certainty_on": config["certainty_on"],
                    "persistence_on": config["persistence_on"],
                }
                for config in factorial_specs
            ]
        )
        factorial_summary = factorial_summary.merge(
            factorial_metadata, on="method", validate="one_to_one"
        )
        component_contrasts = factorial_effects(factorial_summary)
        failure_modes = factorial_failure_modes(
            factorial_details, factorial_metadata
        )
        component_means = (
            component_contrasts.groupby(
                ["component", "targeted_failure_mode"], as_index=False
            )
            .mean(numeric_only=True)
        )
        factorial_details.to_csv(
            out_dir / "factorial_per_problem.csv", index=False
        )
        factorial_summary.to_csv(
            out_dir / "factorial_summary.csv", index=False
        )
        component_contrasts.to_csv(
            out_dir / "factorial_component_contrasts.csv", index=False
        )
        component_means.to_csv(
            out_dir / "factorial_component_mean_effects.csv", index=False
        )
        failure_modes.to_csv(
            out_dir / "factorial_failure_modes.csv", index=False
        )
        factorial_cell_count = int(factorial_summary.shape[0])
    else:
        factorial_cell_count = 0

    transitions = transition_rows(problems)
    transitions.to_csv(out_dir / "consensus_transitions.csv", index=False)
    mechanism = transition_summary(
        transitions, args.bootstrap, args.bootstrap_seed + 1
    )
    mechanism["not_reached"] = len(problems) - len(transitions)
    if transitions.empty:
        by_level = pd.DataFrame(columns=["level"])
        by_finish = pd.DataFrame(columns=["finished_naturally"])
    else:
        by_level = (
            transitions.groupby(["level", "category"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        by_finish = (
            transitions.groupby(["finished_naturally", "category"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
    by_level.to_csv(out_dir / "transitions_by_level.csv", index=False)
    by_finish.to_csv(out_dir / "transitions_by_finish.csv", index=False)
    (out_dir / "transition_summary.json").write_text(
        json.dumps(mechanism, indent=2) + "\n"
    )

    run_settings = first_problem.get("run_settings", {})
    manifest = {
        "protocol_version": protocol["protocol_version"],
        "evaluation_scope": (
            "partial_smoke_test"
            if args.allow_partial_smoke
            else "frozen_full_evaluation"
        ),
        "run_dir": str(args.run_dir),
        "n_problems": len(problems),
        "dataset": dataset,
        "model": validated_settings.get("model"),
        "base_seed": validated_settings.get("base_seed"),
        "probe_suffix_style": stream_style,
        "probe_interval": run_settings.get("probe_interval"),
        "probe_tokens": run_settings.get("probe_tokens"),
        "faithful_certaindex_status": (
            "evaluated"
            if "certaindex_faithful_mid" in primary_names
            else "requires separately logged interval64/probe20 stream"
        ),
        "primary_frozen_methods": ["full_generation", *primary_names],
        "predeclared_baseline_sweeps": {
            "fixed_budget": [512, 1024, 1536, 2048, 3072],
            "entropy_threshold": [0.1, 0.2, 0.3, 0.4],
            "entropy_min_tokens": [0, 512, 1024],
            "entropy_patience": [1, 3, 5],
            "majority_window": [3, 5, 8],
            "majority_share": [0.8, 1.0],
        },
    }
    (out_dir / "evaluation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "n_problems": len(problems),
                "methods": int(primary_summary.shape[0]),
                "factorial_cells": factorial_cell_count,
                "consensus_reached": int(len(transitions)),
                "output": str(out_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
