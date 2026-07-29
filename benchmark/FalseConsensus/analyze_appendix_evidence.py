#!/usr/bin/env python3
"""Recompute the broad, fixed evidence used by Appendix A4--A15.

This is deliberately a read-only audit of existing artifacts.  It does not
touch test labels beyond the already-aggregated Governor confirmation reports,
does not rerun a model, and does not select a new policy.  The only optional
non-stdlib dependency is the project's robust math grader, used for paired
trial/readout and branch-answer comparisons.

Run from the repository root:

    PYTHONPATH=/path/to/grading/deps:$PYTHONPATH \
      python benchmark/FalseConsensus/analyze_appendix_evidence.py
"""

from __future__ import annotations

import csv
import glob
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.related_work.common import real_answers_equal


BENCH = REPO / "benchmark" / "FalseConsensus"
RESULTS = BENCH / "results"
OUT = RESULTS / "appendix_evidence_upgrade"

MODEL_NAMES = {
    "Qwen/Qwen3-8B": "Qwen3-8B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "DeepSeek-7B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": "DeepSeek-Qwen-32B",
    "deepseek-ai/DeepSeek-R1-Distill-Llama-8B": "DeepSeek-Llama-8B",
}
MODEL_SLUGS = {
    "qwen-qwen3-8b": ("Qwen3-8B", "seen-development"),
    "deepseek-ai-deepseek-r1-distill-qwen-7b": (
        "DeepSeek-7B",
        "seen-development",
    ),
    "deepseek-ai-deepseek-r1-distill-qwen-32b": (
        "DeepSeek-Qwen-32B",
        "heldout-scale",
    ),
    "deepseek-ai-deepseek-r1-distill-llama-8b": (
        "DeepSeek-Llama-8B",
        "heldout-architecture",
    ),
}
METHOD_NAMES = {
    "certaindex_mid_frozen": "CertaIndex",
    "deer_frozen": "DEER",
    "tje_frozen": "TJE",
    "governor_balanced_task_aware_secondary": "Governor balanced-task-aware",
    "governor_conservative": "Governor conservative",
    "governor_naive_agreement": "Governor naive",
}
EXPECTED_TEST_N = {"math500": 100, "amc23": 8, "aime24": 6}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.fmean(values) if values else 0.0


def bootstrap_ci(values: list[float], *, seed: int, samples: int = 10_000) -> list[float]:
    rng = random.Random(seed)
    draws = []
    for _ in range(samples):
        draws.append(mean(values[rng.randrange(len(values))] for _ in values))
    draws.sort()
    return [draws[int(0.025 * samples)], draws[int(0.975 * samples)]]


def bootstrap_ci_with_rng(
    values: list[float], *, rng: random.Random, samples: int = 10_000
) -> list[float]:
    draws = []
    for _ in range(samples):
        draws.append(mean(values[rng.randrange(len(values))] for _ in values))
    draws.sort()
    return [draws[int(0.025 * samples)], draws[int(0.975 * samples)]]


def parse_confirmation_frontier() -> dict[str, Any]:
    path = BENCH / "governor_v2" / "analysis" / "confirmation_frontier.txt"
    text = path.read_text()

    def number(pattern: str, cast: type = float) -> Any:
        match = re.search(pattern, text)
        if not match:
            raise RuntimeError(f"missing confirmation-frontier pattern: {pattern}")
        return cast(match.group(1))

    percentiles = {}
    for label in ("0", "1", "5", "25", "50"):
        percentiles[label] = number(rf"p\s*{label}\s*=\s*([-0-9.]+) pp")
    return {
        "source": str(path.relative_to(REPO)),
        "rows": number(r"rows\(at operating budget\)=(\d+)", int),
        "rules": number(r"rules=(\d+)", int),
        "environments_per_rule": number(r"envs/rule \(mode\)=(\d+)", int),
        "worst_case_drop_percentiles_pp": percentiles,
        "test_gate_pass": number(r"rules clearing gate on test: (\d+)", int),
        "accuracy_half_pass": number(
            r"rules with worst-case per-model drop <= 1.5pp \(accuracy half only\): (\d+)",
            int,
        ),
        "all_rules_positive_worst_case": number(
            r"rules losing \(worst-case per-model drop>0\): (\d+)/", int
        ),
        "cell_lose_fraction": number(r"cells: n=\d+ lose>0=([0-9.]+)%") / 100,
        "cell_gain_fraction": number(r"gain<0=([0-9.]+)%") / 100,
        "mean_cell_drop_pp": number(r"mean drop=([-0-9.]+)pp"),
    }


def audit_confirmation_coverage() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = RESULTS / "governor_v2"
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for env in sorted(root.glob("confirmation__*")):
        if not env.is_dir():
            continue
        parts = env.name.split("__")
        if len(parts) != 4:
            continue
        _, model_slug, benchmark, seed_text = parts
        if model_slug not in MODEL_SLUGS:
            errors.append(f"unknown model slug: {model_slug}")
            continue
        seed = int(seed_text.removeprefix("seed_"))
        model, role = MODEL_SLUGS[model_slug]
        main_files = sorted((env / "main" / "traj").glob("problem_*.json"))
        dense_files = sorted(
            (env / "dense_simple32" / "probes").glob("problem_*.json")
        )
        adaptive_files = sorted(
            (env / "adaptive_simple32" / "probes").glob("problem_*.json")
        )
        expected = EXPECTED_TEST_N[benchmark]
        dense_probes = sum(len(load_json(path).get("probes", [])) for path in dense_files)
        adaptive_probes = sum(
            len(load_json(path).get("probes", [])) for path in adaptive_files
        )
        main_payloads = [load_json(path) for path in main_files]
        truncated = sum(not bool(row.get("finished_naturally")) for row in main_payloads)
        empty_final_answers = sum(
            not str(row.get("final_answer", "")).strip() for row in main_payloads
        )
        final_correct = sum(bool(row.get("final_correct")) for row in main_payloads)
        scientific_valid = not (
            model == "DeepSeek-Llama-8B"
            and empty_final_answers > len(main_payloads) / 2
        )
        complete = (
            len(main_files) == expected
            and len(dense_files) == expected
            and len(adaptive_files) == expected
        )
        if not complete:
            errors.append(env.name)
        rows.append(
            {
                "model": model,
                "role": role,
                "benchmark": benchmark,
                "seed": seed,
                "expected_trajectories": expected,
                "main_trajectories": len(main_files),
                "dense_probe_files": len(dense_files),
                "adaptive_probe_files": len(adaptive_files),
                "dense_probes": dense_probes,
                "adaptive_probes": adaptive_probes,
                "truncated": truncated,
                "empty_final_answers": empty_final_answers,
                "final_correct": final_correct,
                "scientific_valid": scientific_valid,
                "complete": complete,
            }
        )

    by_model: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["model"], row["role"])].append(row)
    for (model, role), group in sorted(grouped.items()):
        trajectories = sum(row["main_trajectories"] for row in group)
        truncated = sum(row["truncated"] for row in group)
        by_model.append(
            {
                "model": model,
                "role": role,
                "seeds": sorted({row["seed"] for row in group}),
                "benchmarks": sorted({row["benchmark"] for row in group}),
                "environments": len(group),
                "main_trajectories": trajectories,
                "dense_probes": sum(row["dense_probes"] for row in group),
                "adaptive_probes": sum(row["adaptive_probes"] for row in group),
                "truncated": truncated,
                "truncation_rate": truncated / trajectories if trajectories else 0.0,
                "empty_final_answers": sum(
                    row["empty_final_answers"] for row in group
                ),
                "final_correct": sum(row["final_correct"] for row in group),
                "scientific_valid": all(row["scientific_valid"] for row in group),
                "complete": all(row["complete"] for row in group),
            }
        )
    frontier = parse_confirmation_frontier()
    frontier["valid"] = False
    frontier["invalid_reason"] = (
        "four-model aggregate includes invalid degenerate Llama generation"
    )
    summary = {
        "planned_environments": 24,
        "planned_trajectories": 912,
        "environments": len(rows),
        "main_trajectories": sum(row["main_trajectories"] for row in rows),
        "dense_probes": sum(row["dense_probes"] for row in rows),
        "adaptive_probes": sum(row["adaptive_probes"] for row in rows),
        "truncated": sum(row["truncated"] for row in rows),
        "complete": not errors and len(rows) == 24,
        "errors": errors,
        "by_model": by_model,
        "frontier": frontier,
    }
    return summary, rows


def related_work_benchmark_audit() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = RESULTS / "related_work" / "aggregate" / "environment_split.csv"
    with path.open(newline="") as handle:
        source = list(csv.DictReader(handle))
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in source:
        if row["split"] == "dev":
            grouped[(row["model"], row["method"], row["dataset"])].append(row)
    rows = []
    for (model, method, benchmark), group in sorted(grouped.items()):
        if method not in METHOD_NAMES:
            continue
        rows.append(
            {
                "model": MODEL_NAMES[model],
                "method": METHOD_NAMES[method],
                "benchmark": benchmark,
                "seeds": len(group),
                "n": sum(int(row["n"]) for row in group),
                "accuracy_diff_pp": mean(float(row["accuracy_diff_pp"]) for row in group),
                "all_generated_saving_fraction": mean(
                    float(row["all_generated_token_saving_fraction"]) for row in group
                ),
                "stop_rate": mean(float(row["stop_rate"]) for row in group),
                "invalid_aux_response_rate": mean(
                    float(row["invalid_aux_response_rate"]) for row in group
                ),
            }
        )

    ranges = []
    for key in sorted({(row["model"], row["method"]) for row in rows}):
        group = [row for row in rows if (row["model"], row["method"]) == key]
        ranges.append(
            {
                "model": key[0],
                "method": key[1],
                "benchmark_accuracy_diff_min_pp": min(
                    row["accuracy_diff_pp"] for row in group
                ),
                "benchmark_accuracy_diff_max_pp": max(
                    row["accuracy_diff_pp"] for row in group
                ),
                "benchmark_saving_min_fraction": min(
                    row["all_generated_saving_fraction"] for row in group
                ),
                "benchmark_saving_max_fraction": max(
                    row["all_generated_saving_fraction"] for row in group
                ),
            }
        )

    governor_path = (
        RESULTS
        / "governor_v2"
        / "existing_methods_matched"
        / "governor_dev_macro.csv"
    )
    with governor_path.open(newline="") as handle:
        governor = list(csv.DictReader(handle))
    governor_macro = [
        {
            "model": MODEL_NAMES[row["model"]],
            "method": METHOD_NAMES[row["method"]],
            "accuracy_diff_pp": float(row["accuracy_diff_pp"]),
            "all_generated_saving_fraction": float(
                row["all_generated_token_saving_fraction"]
            ),
            "stop_rate": float(row["stop_rate"]),
        }
        for row in governor
    ]
    return {
        "source_rows": len(source),
        "dev_model_method_benchmark_rows": len(rows),
        "ranges": ranges,
        "matched_governor_macro": governor_macro,
        "test_rows": sum(row["split"] == "test" for row in source),
    }, rows


def trajectory_targets() -> dict[tuple[str, str, int, int], str]:
    targets = {}
    pattern = RESULTS / "governor_v2" / "development__*" / "main" / "traj"
    for directory in glob.glob(str(pattern)):
        for path_text in glob.glob(str(Path(directory) / "problem_*.json")):
            payload = load_json(Path(path_text))
            settings = payload["run_settings"]
            key = (
                settings["model"],
                payload["dataset"],
                int(settings["base_seed"]),
                int(payload["problem_id"]),
            )
            targets[key] = str(payload["target"])
    return targets


def deer_replay_splits() -> dict[tuple[str, str, int, int], str]:
    splits = {}
    pattern = RESULTS / "related_work" / "full" / "_replay" / "*__deer"
    for directory in glob.glob(str(pattern)):
        for line in (Path(directory) / "replay_rows.jsonl").read_text().splitlines():
            row = json.loads(line)
            key = (
                row["model"],
                row["dataset"],
                int(row["base_seed"]),
                int(row["problem_id"]),
            )
            splits[key] = row["split"]
    return splits


def trial_readout_audit() -> dict[str, Any]:
    splits = deer_replay_splits()
    targets = trajectory_targets()
    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pattern = RESULTS / "related_work" / "full" / "*" / "deer" / "trials"
    for directory in glob.glob(str(pattern)):
        for path_text in glob.glob(str(Path(directory) / "problem_*.json")):
            payload = load_json(Path(path_text))
            readout = payload.get("readout")
            if not readout:
                continue
            key = (
                payload["model"],
                payload["dataset"],
                int(payload["base_seed"]),
                int(payload["problem_id"]),
            )
            # F5.1 is a Dev claim.  Restricting the robust symbolic grader to
            # this preregistered split also avoids an unnecessary 1,507-pair
            # train regrade and keeps the audit laptop-friendly.
            if splits[key] != "dev":
                continue
            trial = next(
                row
                for row in payload["trials"]
                if row["candidate_id"] == readout["at_candidate_id"]
            )
            trial_answer = str(trial.get("trial_answer", ""))
            readout_answer = str(readout.get("readout_answer", ""))
            target = targets[key]
            by_split["dev"].append(
                {
                    # Use the same project equivalence relation as replay.
                    # In particular, the single empty/empty pair is not an
                    # artificial disagreement.
                    "same": bool(real_answers_equal(trial_answer, readout_answer)),
                    "trial_correct": bool(
                        trial_answer and real_answers_equal(trial_answer, target)
                    ),
                    "readout_correct": bool(
                        readout_answer and real_answers_equal(readout_answer, target)
                    ),
                    "readout_tokens": int(readout["readout_out_tokens"]),
                }
            )
    summary = {}
    for split, rows in sorted(by_split.items()):
        summary[split] = {
            "triggered_pairs": len(rows),
            "trial_readout_disagreements": sum(not row["same"] for row in rows),
            "disagreement_rate": mean(not row["same"] for row in rows),
            "trial_accuracy": mean(row["trial_correct"] for row in rows),
            "readout_accuracy": mean(row["readout_correct"] for row in rows),
            "mean_readout_output_tokens": mean(row["readout_tokens"] for row in rows),
        }
    return summary


def baseline_lookup(model: str, benchmark: str, seed: int) -> dict[int, tuple[int, int]]:
    slug = model.replace("/", "-").lower()
    directory = (
        RESULTS
        / "governor_v2"
        / f"development__{slug}__{benchmark}__seed_{seed}"
        / "main"
        / "traj"
    )
    rows = {}
    for path in directory.glob("problem_*.json"):
        payload = load_json(path)
        rows[int(payload["problem_id"])] = (
            int(bool(payload["final_correct"])),
            int(payload["tokens_used"]),
        )
    return rows


def audit_online_deer() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    roots = {42: "online_dev", 43: "online_dev_nonformal", 44: "online_dev_nonformal"}
    methods = ("deer_inspired_online_v1", "deer_online_reference")
    model_keys = {
        "qwen3": "Qwen/Qwen3-8B",
        "deepseek": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    }
    benchmarks = ("math500", "amc23", "aime24")
    raw_rows = []
    run_audit = []
    errors = []
    for seed, root_name in roots.items():
        for method in methods:
            for model_key, model in model_keys.items():
                for benchmark in benchmarks:
                    directory = (
                        RESULTS
                        / "deer_inspired"
                        / root_name
                        / method
                        / f"{model_key}__{benchmark}__seed_{seed}"
                    )
                    manifest_path = directory / "run_manifest.json"
                    files = sorted((directory / "problems").glob("problem_*.json"))
                    expected = 100 if benchmark == "math500" else 8 if benchmark == "amc23" else 6
                    manifest = load_json(manifest_path) if manifest_path.exists() else {}
                    complete = (
                        len(files) == expected
                        and bool(manifest.get("completion", {}).get("complete"))
                        and int(
                            manifest.get("completion", {}).get(
                                "observed_problem_count", -1
                            )
                        )
                        == expected
                    )
                    if not complete:
                        errors.append(str(directory.relative_to(REPO)))
                    run_audit.append(
                        {
                            "method": method,
                            "model": MODEL_NAMES[model],
                            "benchmark": benchmark,
                            "seed": seed,
                            "root": root_name,
                            "expected": expected,
                            "observed": len(files),
                            "complete": complete,
                            "protocol_version": manifest.get("run_settings", {}).get(
                                "protocol_version"
                            ),
                            "config_hash": manifest.get("run_settings", {}).get(
                                "config_hash"
                            ),
                        }
                    )
                    baseline = baseline_lookup(model, benchmark, seed)
                    for path in files:
                        payload = load_json(path)
                        problem_id = int(payload["problem_id"])
                        base_correct, base_tokens = baseline[problem_id]
                        all_tokens = int(payload["accounting"]["all_generated_tokens"])
                        # Retain the full payload only for the small branch
                        # subset needed by the component audit.  Main texts
                        # are large enough that keeping all 1,368 payloads in
                        # memory can exceed a laptop's process limit.
                        branch_payload = (
                            payload
                            if method == "deer_inspired_online_v1"
                            and payload.get("branches")
                            else None
                        )
                        raw_rows.append(
                            {
                                "method": method,
                                "model": MODEL_NAMES[model],
                                "model_full": model,
                                "benchmark": benchmark,
                                "seed": seed,
                                "problem_id": problem_id,
                                "correct": int(bool(payload["correct"])),
                                "baseline_correct": base_correct,
                                "baseline_tokens": base_tokens,
                                "all_generated_tokens": all_tokens,
                                "fair_saving": (
                                    (base_tokens - all_tokens) / base_tokens
                                    if base_tokens
                                    else 0.0
                                ),
                                "terminal_state": payload["terminal_state"],
                                "payload": branch_payload,
                            }
                        )

    env_groups: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        env_groups[
            (row["method"], row["model"], row["benchmark"], row["seed"])
        ].append(row)
    env_rows = []
    for (method, model, benchmark, seed), rows in sorted(env_groups.items()):
        env_rows.append(
            {
                "method": method,
                "model": model,
                "benchmark": benchmark,
                "seed": seed,
                "n": len(rows),
                "accuracy": mean(row["correct"] for row in rows),
                "baseline_accuracy": mean(row["baseline_correct"] for row in rows),
                "accuracy_delta_pp": 100
                * mean(row["correct"] - row["baseline_correct"] for row in rows),
                "fair_saving_fraction": mean(row["fair_saving"] for row in rows),
            }
        )

    macro = {}
    for method in methods:
        selected = [row for row in env_rows if row["method"] == method]
        macro[method] = {
            "environments": len(selected),
            "accuracy": mean(row["accuracy"] for row in selected),
            "baseline_accuracy": mean(row["baseline_accuracy"] for row in selected),
            "accuracy_delta_pp": mean(row["accuracy_delta_pp"] for row in selected),
            "fair_saving_fraction": mean(row["fair_saving_fraction"] for row in selected),
        }
    per_seed = {}
    for seed in roots:
        per_seed[str(seed)] = {}
        for method in methods:
            selected = [
                row
                for row in env_rows
                if row["method"] == method and row["seed"] == seed
            ]
            per_seed[str(seed)][method] = {
                "environments": len(selected),
                "accuracy_delta_pp": mean(row["accuracy_delta_pp"] for row in selected),
                "fair_saving_fraction": mean(
                    row["fair_saving_fraction"] for row in selected
                ),
            }

    pooled = {}
    for method in methods:
        selected = [row for row in raw_rows if row["method"] == method]
        pooled[method] = {
            "problems": len(selected),
            "accuracy": mean(row["correct"] for row in selected),
            "fair_saving_fraction": mean(row["fair_saving"] for row in selected),
        }

    inspired_env = {
        (row["model"], row["benchmark"], row["seed"]): row
        for row in env_rows
        if row["method"] == "deer_inspired_online_v1"
    }
    deer_env = {
        (row["model"], row["benchmark"], row["seed"]): row
        for row in env_rows
        if row["method"] == "deer_online_reference"
    }
    paired_keys = sorted(set(inspired_env) & set(deer_env))
    accuracy_diffs = [
        inspired_env[key]["accuracy_delta_pp"] - deer_env[key]["accuracy_delta_pp"]
        for key in paired_keys
    ]
    saving_diffs = [
        100
        * (
            inspired_env[key]["fair_saving_fraction"]
            - deer_env[key]["fair_saving_fraction"]
        )
        for key in paired_keys
    ]

    branch_records = [
        row
        for row in raw_rows
        if row["method"] == "deer_inspired_online_v1"
        and row["payload"] is not None
    ]
    transitions = Counter()
    branch_commits = []
    verification_lengths = []
    verification_finish = Counter()
    counterfactual_tokens_saved = 0
    counterfactual_by_env: dict[tuple[str, str, int], list[tuple[int, float]]] = defaultdict(list)
    current_by_env: dict[tuple[str, str, int], list[tuple[int, float]]] = defaultdict(list)
    for row in branch_records:
        payload = row["payload"]
        branch = payload["branches"][0]
        target = str(payload["target"])
        stage1_correct = bool(branch["answer_a"]) and real_answers_equal(
            str(branch["answer_a"]), target
        )
        final_correct = bool(payload["delivered_answer"]) and real_answers_equal(
            str(payload["delivered_answer"]), target
        )
        transitions[
            f"{'correct' if stage1_correct else 'wrong'}_to_"
            f"{'correct' if final_correct else 'wrong'}"
        ] += 1
        if payload["terminal_state"] == "branch_commit":
            branch_commits.append((int(final_correct), row["baseline_correct"]))
        verification = branch["verification"]
        verification_lengths.append(int(verification["output_tokens"]))
        verification_finish[str(verification["finish_reason"])] += 1

        candidate_id = int(branch["candidate_id"])
        probe_tokens = sum(
            int((event.get("trial") or {}).get("output_tokens", 0))
            for event in payload["wait_events"]
            if int(event["candidate_id"]) <= candidate_id
        )
        direct_tokens = int(branch["native_main_token_position"]) + probe_tokens
        saved = row["all_generated_tokens"] - direct_tokens
        counterfactual_tokens_saved += saved
        direct_saving = (
            (row["baseline_tokens"] - direct_tokens) / row["baseline_tokens"]
            if row["baseline_tokens"]
            else 0.0
        )
        key = (row["model"], row["benchmark"], row["seed"])
        counterfactual_by_env[key].append((int(stage1_correct), direct_saving))
        current_by_env[key].append((row["correct"], row["fair_saving"]))

    all_inspired = [
        row for row in raw_rows if row["method"] == "deer_inspired_online_v1"
    ]
    branch_keys = {
        (row["model"], row["benchmark"], row["seed"], row["problem_id"])
        for row in branch_records
    }
    for row in all_inspired:
        key4 = (row["model"], row["benchmark"], row["seed"], row["problem_id"])
        if key4 in branch_keys:
            continue
        key3 = (row["model"], row["benchmark"], row["seed"])
        counterfactual_by_env[key3].append((row["correct"], row["fair_saving"]))
        current_by_env[key3].append((row["correct"], row["fair_saving"]))
    cf_macro_accuracy = mean(mean(v[0] for v in rows) for rows in counterfactual_by_env.values())
    cf_macro_saving = mean(mean(v[1] for v in rows) for rows in counterfactual_by_env.values())
    current_macro_accuracy = mean(mean(v[0] for v in rows) for rows in current_by_env.values())
    current_macro_saving = mean(mean(v[1] for v in rows) for rows in current_by_env.values())

    branch_audit = {
        "first_branch_candidate_records": len(branch_records),
        "records_with_multiple_branches": sum(
            len(row["payload"]["branches"]) > 1 for row in branch_records
        ),
        "stage1_to_final_transitions": dict(sorted(transitions.items())),
        "branch_commits": len(branch_commits),
        "branch_commit_accuracy": mean(row[0] for row in branch_commits),
        "matched_full_accuracy": mean(row[1] for row in branch_commits),
        "verification_output_token_min": min(verification_lengths),
        "verification_output_token_max": max(verification_lengths),
        "verification_finish_reasons": dict(sorted(verification_finish.items())),
        "direct_stage1_counterfactual": {
            "macro_accuracy": cf_macro_accuracy,
            "observed_macro_accuracy": current_macro_accuracy,
            "accuracy_delta_pp": 100 * (cf_macro_accuracy - current_macro_accuracy),
            "fair_saving_fraction": cf_macro_saving,
            "observed_fair_saving_fraction": current_macro_saving,
            "saving_delta_pp": 100 * (cf_macro_saving - current_macro_saving),
            "output_tokens_saved": counterfactual_tokens_saved,
        },
    }
    # Match the original multiseed audit exactly: one deterministic RNG is
    # consumed by the accuracy bootstrap and then by the saving bootstrap.
    bootstrap_rng = random.Random(20260729)
    accuracy_ci = bootstrap_ci_with_rng(accuracy_diffs, rng=bootstrap_rng)
    saving_ci = bootstrap_ci_with_rng(saving_diffs, rng=bootstrap_rng)
    return {
        "run_directories": len(run_audit),
        "method_problem_rows": len(raw_rows),
        "complete": not errors and len(run_audit) == 36 and len(raw_rows) == 1368,
        "errors": errors,
        "protocol_versions": dict(
            Counter(row["protocol_version"] for row in run_audit)
        ),
        "config_hashes": dict(Counter(row["config_hash"] for row in run_audit)),
        "macro": macro,
        "per_seed": per_seed,
        "problem_pooled": pooled,
        "paired_environment_bootstrap": {
            "environments": len(paired_keys),
            "accuracy_advantage_pp": mean(accuracy_diffs),
            "accuracy_95ci_pp": accuracy_ci,
            "saving_advantage_pp": mean(saving_diffs),
            "saving_95ci_pp": saving_ci,
        },
        "branch_audit": branch_audit,
        "run_audit": run_audit,
    }, env_rows


def fast_path_split_table() -> list[dict[str, Any]]:
    payload = load_json(
        RESULTS / "deer_inspired" / "fast_path_only_replay" / "summary.json"
    )
    rows = []
    for split, models in payload["macro_over_benchmarks"].items():
        for model, metrics in models.items():
            rows.append(
                {
                    "split": split,
                    "model": MODEL_NAMES[model],
                    **metrics,
                }
            )
    return rows


def render_report(summary: dict[str, Any]) -> str:
    conf = summary["confirmation"]
    online = summary["deer_inspired_online"]
    branch = online["branch_audit"]
    readout = summary["trial_readout"]["dev"]
    lines = [
        "# Appendix Evidence Upgrade Audit",
        "",
        "This report recomputes broader evidence from fixed local artifacts. It "
        "does not run a model or select a policy.",
        "",
        "## Confirmation",
        "",
        f"- Observed {conf['environments']}/{conf['planned_environments']} "
        f"planned environments and {conf['main_trajectories']}/"
        f"{conf['planned_trajectories']} trajectories, "
        f"{conf['dense_probes']:,} dense probes, "
        f"{conf['adaptive_probes']:,} adaptive probes; complete={conf['complete']}.",
        "- The retained four-model Test frontier is invalid because the Llama "
        "run generated degenerate punctuation/repetition; same-model Dev/Test "
        "and Qwen-32B scale evidence must be reported separately.",
        "",
        "## Related work",
        "",
        f"- {summary['related_work']['dev_model_method_benchmark_rows']} "
        "model-method-benchmark Dev rows cover 2 models, 3 methods, 3 "
        "benchmarks, and 3 seeds per cell.",
        f"- Test rows available: {summary['related_work']['test_rows']}.",
        "",
        "## DEER components",
        "",
        f"- Frozen DEER Dev readouts: {readout['triggered_pairs']} paired cases; "
        f"trial/readout disagreement {100*readout['disagreement_rate']:.2f}%; "
        f"trial/readout accuracy {100*readout['trial_accuracy']:.2f}%/"
        f"{100*readout['readout_accuracy']:.2f}%; mean readout "
        f"{readout['mean_readout_output_tokens']:.1f} output tokens.",
        f"- Online raw audit: {online['run_directories']} complete run dirs, "
        f"{online['method_problem_rows']} method-problem rows; "
        f"complete={online['complete']}.",
        f"- First branches: {branch['first_branch_candidate_records']}; "
        f"transitions={branch['stage1_to_final_transitions']}.",
        f"- All first-branch verifications terminate at "
        f"{branch['verification_output_token_min']}-"
        f"{branch['verification_output_token_max']} tokens; finish reasons "
        f"{branch['verification_finish_reasons']}.",
        f"- Direct Stage-1 counterfactual changes macro accuracy by "
        f"{branch['direct_stage1_counterfactual']['accuracy_delta_pp']:+.3f} pp "
        f"and saving by "
        f"{branch['direct_stage1_counterfactual']['saving_delta_pp']:+.3f} pp.",
        "",
        "## Unchanged gaps",
        "",
        "- No returned Task-A/Task-B human annotation CSV is present; taxonomy "
        "claims remain preliminary.",
        "- Related-work baselines and the full online boundary controller still "
        "have no held-out Test run in the retained artifacts.",
        "- No interval × probe-length × KV-reuse factorial ablation or DEER-v3 "
        "`C_cali` implementation is present.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    confirmation, confirmation_rows = audit_confirmation_coverage()
    related_work, related_work_rows = related_work_benchmark_audit()
    readout = trial_readout_audit()
    online, online_env_rows = audit_online_deer()
    fast_path = fast_path_split_table()
    summary = {
        "schema_version": "appendix-evidence-upgrade-1",
        "scope": "fixed-artifact audit; no model generation; no policy selection",
        "confirmation": confirmation,
        "related_work": related_work,
        "trial_readout": readout,
        "deer_inspired_online": online,
        "fast_path_split_rows": fast_path,
        "taxonomy_human_return_artifacts": [],
    }
    write_json(OUT / "summary.json", summary)
    write_csv(OUT / "confirmation_environment_audit.csv", confirmation_rows)
    write_csv(OUT / "related_work_benchmark_macro.csv", related_work_rows)
    write_csv(OUT / "deer_online_environment_metrics.csv", online_env_rows)
    write_csv(OUT / "fast_path_split_macro.csv", fast_path)
    (OUT / "report.md").write_text(render_report(summary))
    print(render_report(summary))


if __name__ == "__main__":
    main()
