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
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
FC_DIR = HERE.parent
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
    return parser.parse_args()


def frozen_config(name: str, spec: dict) -> dict:
    config = dict(spec)
    config["config_id"] = name
    return config


def load_problems(
    run_dir: Path, difficulty_csv: Path
) -> tuple[dict[int, dict], pd.DataFrame]:
    probes = pd.read_csv(run_dir / "probes.csv", keep_default_na=False)
    problems = rules.load_qwen_problems(
        run_dir / "probes.csv",
        run_dir / "traj",
        difficulty_csv,
    )
    trajectories = rules.load_trajectories(run_dir / "traj")
    for pid, problem in problems.items():
        trajectory = trajectories[pid]
        problem["accounting"] = trajectory.get("accounting", {})
        problem["probe_records"] = trajectory.get("probes", [])
        problem["finished_naturally"] = bool(
            trajectory.get("finished_naturally", False)
        )
    return problems, probes


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
        stop_index, _ = rules.simulate(config, problems[int(pid)])
        extras.append(accounting_for(problems[int(pid)], stop_index))
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
                        }
                    )
    return configs


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text())
    out_dir = args.out_dir or args.run_dir / "final_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    problems, _ = load_problems(args.run_dir, args.difficulty_csv)
    if len(problems) != 500:
        raise ValueError(
            f"Frozen MATH500 evaluation requires 500 trajectories, got "
            f"{len(problems)}"
        )

    method_frames = [full_rows(problems)]
    for cap in protocol["frozen_methods"]["fixed_budget"]["caps"]:
        method_frames.append(fixed_budget_rows(int(cap), problems))

    configs = {}
    for name in ["naive_agreement", "conservative", "balanced_math"]:
        configs[name] = frozen_config(
            name, protocol["frozen_methods"][name]
        )
        method_frames.append(governor_rows(name, configs[name], problems))

    # Same-stream adaptation only. A faithful CertaIndex result requires its
    # own prompt stream and is intentionally not mislabeled here.
    certa_adapted = {
        "config_id": "certaindex_adapted_simple32",
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
            "certaindex_adapted_simple32", certa_adapted, problems
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

    factorial_frames = [
        governor_rows(config["config_id"], config, problems)
        for config in factorial_configs()
    ]
    factorial_details = pd.concat(factorial_frames, ignore_index=True)
    factorial_summary = pd.DataFrame(
        [
            summarize(frame)
            for _, frame in factorial_details.groupby("method", sort=False)
        ]
    )
    factorial_details.to_csv(
        out_dir / "factorial_per_problem.csv", index=False
    )
    factorial_summary.to_csv(out_dir / "factorial_summary.csv", index=False)

    manifest = {
        "protocol_version": protocol["protocol_version"],
        "run_dir": str(args.run_dir),
        "n_problems": len(problems),
        "faithful_certaindex_status": (
            "not evaluated: requires a separately generated CertaIndex "
            "prompt stream"
        ),
        "primary_frozen_methods": [
            "full_generation",
            "naive_agreement",
            "conservative",
            "balanced_math",
        ],
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
                "factorial_cells": int(factorial_summary.shape[0]),
                "output": str(out_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
