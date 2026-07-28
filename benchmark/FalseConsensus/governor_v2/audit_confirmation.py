#!/usr/bin/env python3
"""Audit the two-model Governor-v2 confirmation collection.

The audit is intentionally independent of model correctness.  It verifies the
preregistered collection envelope, exact test problem IDs, manifests, and the
one-to-one main/dense/adaptive artifact coverage needed before results are
reported or pushed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "governor-v2-preregistered-2026-07-27.10"
MODELS = {
    "deepseek-ai-deepseek-r1-distill-qwen-7b": (
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    ),
    "qwen-qwen3-8b": "Qwen/Qwen3-8B",
}
DATASETS = {
    "math500": 100,
    "amc23": 8,
    "aime24": 6,
}
SEEDS = (45, 46, 47)
PROBE_KINDS = ("dense_simple32", "adaptive_simple32")
PROBLEM_FILE_RE = re.compile(r"problem_(\d+)\.json\Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    repo_root = Path(__file__).resolve().parents[3]
    parser.add_argument(
        "--results-root",
        type=Path,
        default=repo_root
        / "benchmark"
        / "FalseConsensus"
        / "results"
        / "governor_v2",
    )
    parser.add_argument(
        "--problem-ids-root",
        type=Path,
        default=Path(__file__).resolve().parent
        / "generated"
        / "problem_ids",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Report progress without failing solely on missing artifacts.",
    )
    return parser.parse_args()


def read_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing file: {path}")
        return None
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {path}: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"expected JSON object: {path}")
        return None
    return payload


def check_equal(
    errors: list[str], label: str, observed: Any, expected: Any
) -> None:
    if observed != expected:
        errors.append(f"{label}: observed={observed!r}, expected={expected!r}")


def problem_files(
    directory: Path, errors: list[str]
) -> tuple[dict[int, Path], list[str]]:
    by_id: dict[int, Path] = {}
    malformed: list[str] = []
    if not directory.is_dir():
        return by_id, malformed
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        match = PROBLEM_FILE_RE.fullmatch(path.name)
        if match is None:
            if path.suffix == ".json":
                malformed.append(path.name)
            continue
        problem_id = int(match.group(1))
        if problem_id in by_id:
            errors.append(
                f"duplicate problem ID {problem_id}: "
                f"{by_id[problem_id]} and {path}"
            )
        by_id[problem_id] = path
    return by_id, malformed


def check_main_manifest(
    path: Path,
    *,
    model: str,
    dataset: str,
    seed: int,
    errors: list[str],
) -> dict[str, Any] | None:
    payload = read_json(path, errors)
    if payload is None:
        return None
    check_equal(
        errors,
        f"{path}: schema_version",
        payload.get("schema_version"),
        "governor-v2-main-run-1",
    )
    check_equal(
        errors, f"{path}: api_key_recorded", payload.get("api_key_recorded"), False
    )
    settings = payload.get("run_settings")
    if not isinstance(settings, dict):
        errors.append(f"{path}: missing run_settings object")
        return None
    expected = {
        "collection_schema": "governor-v2-main-1",
        "model": model,
        "dataset": dataset,
        "base_seed": seed,
        "protocol_version": PROTOCOL_VERSION,
        "phase": "confirmation",
        "model_role": "development",
        "split_labels": ["test"],
        "temperature": 0.6,
        "top_p": 0.95,
        "main_request_mode": "single_request",
    }
    for key, value in expected.items():
        check_equal(errors, f"{path}: run_settings.{key}", settings.get(key), value)
    expected_budget = 32768 if dataset == "aime24" else 16384
    check_equal(
        errors,
        f"{path}: run_settings.budget",
        settings.get("budget"),
        expected_budget,
    )
    dataset_path = str(settings.get("dataset_path", ""))
    if not dataset_path.endswith(f"/{dataset}/test.jsonl"):
        errors.append(f"{path}: wrong dataset_path {dataset_path!r}")
    ids_path = str(settings.get("problem_ids_file", ""))
    if not ids_path.endswith(f"/{dataset}__test.txt"):
        errors.append(f"{path}: wrong problem_ids_file {ids_path!r}")
    return settings


def check_probe_manifest(
    path: Path,
    *,
    kind: str,
    model: str,
    dataset: str,
    seed: int,
    errors: list[str],
) -> None:
    payload = read_json(path, errors)
    if payload is None:
        return
    expected_schema = (
        "governor-v2-probe-run-1"
        if kind == "dense_simple32"
        else "governor-v2-adaptive-probe-run-1"
    )
    check_equal(
        errors,
        f"{path}: schema_version",
        payload.get("schema_version"),
        expected_schema,
    )
    check_equal(
        errors, f"{path}: api_key_recorded", payload.get("api_key_recorded"), False
    )
    settings = payload.get("probe_settings")
    if not isinstance(settings, dict):
        errors.append(f"{path}: missing probe_settings object")
        return
    common = {
        "model": model,
        "dataset": dataset,
        "base_seed": seed,
        "probe_style": "simple",
        "probe_tokens": 32,
    }
    for key, value in common.items():
        check_equal(
            errors, f"{path}: probe_settings.{key}", settings.get(key), value
        )
    if kind == "dense_simple32":
        expected = {
            "collection_schema": "governor-v2-dense-probe-1",
            "dense_interval": 64,
            "start_token": 64,
        }
    else:
        expected = {
            "collection_schema": "governor-v2-adaptive-probe-1",
            "start_token": 256,
            "alignment": "next_step_boundary",
            "alignment_lookahead_tokens": 32,
            "entropy_metric": "teacher_forced_topk_entropy",
            "entropy_top_k": 20,
            "entropy_smooth_window_tokens": 16,
            "entropy_reference_window_tokens": 64,
            "entropy_candidate_min_drop": 0.1,
            "candidate_min_gap": 32,
            "max_candidate_probes": 128,
            "periodic_fallback_source": "dense_simple32",
        }
    for key, value in expected.items():
        check_equal(
            errors, f"{path}: probe_settings.{key}", settings.get(key), value
        )


def check_probe_records(
    path: Path,
    *,
    kind: str,
    problem_id: int,
    model: str,
    dataset: str,
    seed: int,
    main_tokens: int,
    finished_naturally: bool,
    errors: list[str],
) -> tuple[int, int, float, list[int]]:
    payload = read_json(path, errors)
    if payload is None:
        return 0, 0, 0.0, []
    expected_schema = (
        "governor-v2-probe-trajectory-1"
        if kind == "dense_simple32"
        else "governor-v2-adaptive-probe-trajectory-1"
    )
    expected_values = {
        "schema_version": expected_schema,
        "problem_id": problem_id,
        "model": model,
        "dataset": dataset,
        "base_seed": seed,
        "main_token_count_recorded": main_tokens,
    }
    for key, value in expected_values.items():
        check_equal(errors, f"{path}: {key}", payload.get(key), value)
    reencoded = payload.get("main_token_count_reencoded")
    if not isinstance(reencoded, int) or reencoded < 0:
        errors.append(f"{path}: invalid main_token_count_reencoded {reencoded!r}")
        reencoded = 0
    records = payload.get("probes")
    if not isinstance(records, list):
        errors.append(f"{path}: probes is not a list")
        return 0, 0, 0.0, []
    positions: list[int] = []
    output_tokens = 0
    latency = 0.0
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append(f"{path}: probe {index} is not an object")
            continue
        if "error" in record:
            errors.append(f"{path}: probe {index} contains error field")
        check_equal(
            errors, f"{path}: probe_id at row {index}", record.get("probe_id"), index
        )
        position = record.get("token_position")
        if not isinstance(position, int):
            errors.append(f"{path}: invalid token_position {position!r}")
            continue
        positions.append(position)
        out_tokens = record.get("probe_out_tokens")
        if not isinstance(out_tokens, int) or not 0 <= out_tokens <= 32:
            errors.append(f"{path}: invalid probe_out_tokens {out_tokens!r}")
        else:
            output_tokens += out_tokens
        prompt_tokens = record.get("probe_prompt_tokens")
        if not isinstance(prompt_tokens, int) or prompt_tokens <= 0:
            errors.append(f"{path}: invalid probe_prompt_tokens {prompt_tokens!r}")
        if not isinstance(record.get("probe_answer"), str):
            errors.append(f"{path}: invalid probe_answer at row {index}")
        if not isinstance(record.get("is_certain"), bool):
            errors.append(f"{path}: invalid is_certain at row {index}")
        record_latency = record.get("probe_latency_seconds")
        if not isinstance(record_latency, (int, float)) or record_latency <= 0:
            errors.append(f"{path}: invalid probe_latency_seconds {record_latency!r}")
        else:
            latency += float(record_latency)
    if positions != sorted(set(positions)):
        errors.append(f"{path}: probe positions are not strictly increasing/unique")
    if kind == "dense_simple32":
        inclusive_stop = min(reencoded, main_tokens) + (
            0 if finished_naturally else 1
        )
        expected_positions = list(range(64, inclusive_stop, 64))
        check_equal(
            errors, f"{path}: dense token positions", positions, expected_positions
        )
    else:
        if len(records) > 128:
            errors.append(f"{path}: adaptive probe count exceeds 128")
        if any(position < 256 for position in positions):
            errors.append(f"{path}: adaptive probe before token 256")
        if any(position > reencoded for position in positions):
            errors.append(f"{path}: adaptive probe after reencoded trajectory end")
        check_equal(
            errors,
            f"{path}: candidate_positions_probed",
            payload.get("candidate_positions_probed"),
            len(records),
        )
        before = payload.get("candidate_positions_before_thinning")
        if not isinstance(before, int) or before < len(records):
            errors.append(
                f"{path}: invalid candidate_positions_before_thinning {before!r}"
            )
        entropy_latency = payload.get("entropy_scoring_latency_seconds")
        if not isinstance(entropy_latency, (int, float)) or entropy_latency < 0:
            errors.append(
                f"{path}: invalid entropy_scoring_latency_seconds "
                f"{entropy_latency!r}"
            )
    return len(records), output_tokens, latency, positions


def check_flat_csv(
    path: Path,
    *,
    expected_keys: set[tuple[str, str]],
    model: str,
    dataset: str,
    seed: int,
    errors: list[str],
) -> None:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except FileNotFoundError:
        errors.append(f"missing file: {path}")
        return
    except OSError as exc:
        errors.append(f"cannot read {path}: {exc}")
        return
    check_equal(errors, f"{path}: row count", len(rows), len(expected_keys))
    keys = [(row.get("problem_id"), row.get("token_position")) for row in rows]
    if len(keys) != len(set(keys)):
        errors.append(f"{path}: duplicate (problem_id, token_position) rows")
    observed_keys = set(keys)
    missing_keys = expected_keys - observed_keys
    extra_keys = observed_keys - expected_keys
    if missing_keys:
        errors.append(
            f"{path}: missing JSON probe keys {sorted(missing_keys)[:20]}"
        )
    if extra_keys:
        errors.append(
            f"{path}: unexpected CSV probe keys {sorted(extra_keys)[:20]}"
        )
    for row_number, row in enumerate(rows, start=2):
        expected_metadata = {
            "model": model,
            "dataset": dataset,
            "base_seed": str(seed),
        }
        for key, value in expected_metadata.items():
            if row.get(key) != value:
                errors.append(
                    f"{path}:{row_number}: {key}={row.get(key)!r}, "
                    f"expected={value!r}"
                )


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    missing: list[str] = []
    expected_ids: dict[str, set[int]] = {}
    for dataset, expected_count in DATASETS.items():
        path = args.problem_ids_root / f"{dataset}__test.txt"
        try:
            ids = [
                int(line.strip())
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (FileNotFoundError, OSError, ValueError) as exc:
            errors.append(f"cannot read problem IDs {path}: {exc}")
            ids = []
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate problem IDs in {path}")
        check_equal(errors, f"{path}: ID count", len(ids), expected_count)
        expected_ids[dataset] = set(ids)

    summary: dict[str, Any] = {
        "schema_version": "governor-v2-confirmation-audit-1",
        "protocol_version": PROTOCOL_VERSION,
        "expected": {
            "models": len(MODELS),
            "environments": len(MODELS) * len(DATASETS) * len(SEEDS),
            "main_trajectories": len(MODELS) * sum(DATASETS.values()) * len(SEEDS),
            "probe_file_sets": list(PROBE_KINDS),
        },
        "observed": {
            "environments_complete": 0,
            "main_trajectories": 0,
            "dense_probe_files": 0,
            "adaptive_probe_files": 0,
            "main_decode_tokens": 0,
            "main_prompt_tokens": 0,
            "main_wall_clock_seconds_sum": 0.0,
            "finished_naturally": 0,
            "truncated": 0,
            "dense_probes": 0,
            "adaptive_probes": 0,
            "probe_output_tokens": 0,
            "probe_latency_seconds_sum": 0.0,
        },
        "by_environment": [],
        "missing": missing,
        "errors": errors,
    }

    expected_environment_names = {
        f"confirmation__{slug}__{dataset}__seed_{seed}"
        for slug in MODELS
        for dataset in DATASETS
        for seed in SEEDS
    }
    observed_environment_names = {
        path.name
        for path in args.results_root.glob("confirmation__*")
        if path.is_dir()
    }
    unexpected_environments = (
        observed_environment_names - expected_environment_names
    )
    if unexpected_environments:
        errors.append(
            "unexpected confirmation environments: "
            f"{sorted(unexpected_environments)}"
        )

    for slug, model in MODELS.items():
        for dataset in DATASETS:
            ids = expected_ids.get(dataset, set())
            for seed in SEEDS:
                env_name = f"confirmation__{slug}__{dataset}__seed_{seed}"
                env_dir = args.results_root / env_name
                env_errors_before = len(errors)
                env_missing_before = len(missing)
                env_summary: dict[str, Any] = {
                    "environment": env_name,
                    "expected_problem_count": len(ids),
                    "main": 0,
                    "dense_files": 0,
                    "adaptive_files": 0,
                    "dense_probes": 0,
                    "adaptive_probes": 0,
                    "complete": False,
                }
                if not env_dir.is_dir():
                    missing.append(f"missing environment: {env_dir}")
                    summary["by_environment"].append(env_summary)
                    continue
                main_dir = env_dir / "main"
                settings = check_main_manifest(
                    main_dir / "run_manifest.json",
                    model=model,
                    dataset=dataset,
                    seed=seed,
                    errors=errors,
                )
                main_files, malformed = problem_files(main_dir / "traj", errors)
                if malformed:
                    errors.append(
                        f"{main_dir / 'traj'}: malformed JSON names {malformed}"
                    )
                missing_main = ids - set(main_files)
                extra_main = set(main_files) - ids
                if missing_main:
                    missing.append(f"{env_name}: missing main IDs {sorted(missing_main)}")
                if extra_main:
                    errors.append(f"{env_name}: unexpected main IDs {sorted(extra_main)}")
                main_meta: dict[int, tuple[int, bool]] = {}
                for problem_id in sorted(ids & set(main_files)):
                    path = main_files[problem_id]
                    payload = read_json(path, errors)
                    if payload is None:
                        continue
                    expected_values = {
                        "schema_version": "governor-v2-main-trajectory-1",
                        "problem_id": problem_id,
                        "dataset": dataset,
                    }
                    for key, value in expected_values.items():
                        check_equal(errors, f"{path}: {key}", payload.get(key), value)
                    if "error" in payload:
                        errors.append(f"{path}: contains error field")
                    trajectory_settings = payload.get("run_settings")
                    if settings is not None and trajectory_settings != {
                        **settings,
                        "main_seed": seed + problem_id,
                    }:
                        errors.append(f"{path}: run_settings mismatch")
                    tokens = payload.get("tokens_used")
                    if not isinstance(tokens, int) or tokens < 0:
                        errors.append(f"{path}: invalid tokens_used {tokens!r}")
                        continue
                    finished = payload.get("finished_naturally")
                    if not isinstance(finished, bool):
                        errors.append(
                            f"{path}: invalid finished_naturally {finished!r}"
                        )
                        continue
                    finish_reason = payload.get("finish_reason")
                    if finish_reason not in {"stop", "length"}:
                        errors.append(
                            f"{path}: invalid finish_reason {finish_reason!r}"
                        )
                    check_equal(
                        errors,
                        f"{path}: finish_reason/finished_naturally",
                        (finish_reason, finished),
                        ("stop", True) if finished else ("length", False),
                    )
                    expected_budget = 32768 if dataset == "aime24" else 16384
                    if tokens > expected_budget:
                        errors.append(
                            f"{path}: tokens_used {tokens} exceeds "
                            f"budget {expected_budget}"
                        )
                    if finish_reason == "length" and tokens != expected_budget:
                        errors.append(
                            f"{path}: length finish has tokens_used={tokens}, "
                            f"expected budget={expected_budget}"
                        )
                    accounting = payload.get("accounting")
                    if not isinstance(accounting, dict):
                        errors.append(f"{path}: missing accounting object")
                        accounting = {}
                    check_equal(
                        errors,
                        f"{path}: accounting.main_decode_tokens",
                        accounting.get("main_decode_tokens"),
                        tokens,
                    )
                    check_equal(
                        errors,
                        f"{path}: accounting.main_calls",
                        accounting.get("main_calls"),
                        1,
                    )
                    summary["observed"]["main_decode_tokens"] += tokens
                    prompt_tokens = accounting.get("main_prompt_tokens", 0)
                    if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
                        summary["observed"]["main_prompt_tokens"] += prompt_tokens
                    else:
                        errors.append(
                            f"{path}: invalid main_prompt_tokens {prompt_tokens!r}"
                        )
                    wall = accounting.get("main_wall_clock_seconds", 0.0)
                    if isinstance(wall, (int, float)) and wall >= 0:
                        summary["observed"]["main_wall_clock_seconds_sum"] += float(
                            wall
                        )
                    else:
                        errors.append(
                            f"{path}: invalid main_wall_clock_seconds {wall!r}"
                        )
                    summary["observed"][
                        "finished_naturally" if finished else "truncated"
                    ] += 1
                    main_meta[problem_id] = (tokens, finished)
                env_summary["main"] = len(ids & set(main_files))
                summary["observed"]["main_trajectories"] += env_summary["main"]

                for kind in PROBE_KINDS:
                    probe_dir = env_dir / kind
                    check_probe_manifest(
                        probe_dir / "probe_manifest.json",
                        kind=kind,
                        model=model,
                        dataset=dataset,
                        seed=seed,
                        errors=errors,
                    )
                    probe_files, malformed = problem_files(
                        probe_dir / "probes", errors
                    )
                    if malformed:
                        errors.append(
                            f"{probe_dir / 'probes'}: malformed JSON names {malformed}"
                        )
                    missing_probe = ids - set(probe_files)
                    extra_probe = set(probe_files) - ids
                    if missing_probe:
                        missing.append(
                            f"{env_name}/{kind}: missing IDs "
                            f"{sorted(missing_probe)}"
                        )
                    if extra_probe:
                        errors.append(
                            f"{env_name}/{kind}: unexpected IDs "
                            f"{sorted(extra_probe)}"
                        )
                    probe_count = 0
                    flat_keys: set[tuple[str, str]] = set()
                    for problem_id in sorted(ids & set(probe_files)):
                        if problem_id not in main_meta:
                            continue
                        tokens, finished = main_meta[problem_id]
                        count, output_tokens, latency, positions = check_probe_records(
                            probe_files[problem_id],
                            kind=kind,
                            problem_id=problem_id,
                            model=model,
                            dataset=dataset,
                            seed=seed,
                            main_tokens=tokens,
                            finished_naturally=finished,
                            errors=errors,
                        )
                        probe_count += count
                        flat_keys.update(
                            (str(problem_id), str(position))
                            for position in positions
                        )
                        summary["observed"]["probe_output_tokens"] += output_tokens
                        summary["observed"]["probe_latency_seconds_sum"] += latency
                    file_key = (
                        "dense_files"
                        if kind == "dense_simple32"
                        else "adaptive_files"
                    )
                    probe_key = (
                        "dense_probes"
                        if kind == "dense_simple32"
                        else "adaptive_probes"
                    )
                    env_summary[file_key] = len(ids & set(probe_files))
                    env_summary[probe_key] = probe_count
                    summary["observed"][
                        "dense_probe_files"
                        if kind == "dense_simple32"
                        else "adaptive_probe_files"
                    ] += env_summary[file_key]
                    summary["observed"][probe_key] += probe_count
                    if kind == "dense_simple32" and len(probe_files) == len(ids):
                        check_flat_csv(
                            probe_dir / "probes.csv",
                            expected_keys=flat_keys,
                            model=model,
                            dataset=dataset,
                            seed=seed,
                            errors=errors,
                        )

                env_summary["complete"] = (
                    env_summary["main"] == len(ids)
                    and env_summary["dense_files"] == len(ids)
                    and env_summary["adaptive_files"] == len(ids)
                    and len(errors) == env_errors_before
                    and len(missing) == env_missing_before
                )
                if env_summary["complete"]:
                    summary["observed"]["environments_complete"] += 1
                summary["by_environment"].append(env_summary)

    summary["observed"]["truncation_rate"] = (
        summary["observed"]["truncated"]
        / summary["observed"]["main_trajectories"]
        if summary["observed"]["main_trajectories"]
        else None
    )
    summary["valid"] = not errors and not missing
    rendered = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if errors:
        return 1
    if missing and not args.allow_partial:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
