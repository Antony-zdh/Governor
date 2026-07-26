#!/usr/bin/env python3
"""Expand the Governor v2 multi-environment collection matrix."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Mapping


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "generated/experiment_matrix.jsonl",
    )
    parser.add_argument(
        "--include-32-grid",
        action="store_true",
        help=(
            "add the complementary 32,96,160,... probe pass; merge it with "
            "the base 64,128,192,... pass to obtain a 32-token grid"
        ),
    )
    parser.add_argument(
        "--phase",
        choices=("development", "confirmation", "all"),
        default="development",
        help="respect preregistered model roles and split visibility",
    )
    parser.add_argument(
        "--problem-ids-dir",
        type=Path,
        default=Path(
            "benchmark/FalseConsensus/governor_v2/generated/problem_ids"
        ),
    )
    parser.add_argument(
        "--exclude-model-role",
        action="append",
        default=[],
        help="omit a model role from the generated matrix; repeatable",
    )
    return parser.parse_args()


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()


def command_text(arguments: List[str]) -> str:
    return shlex.join(arguments)


def build_matrix(
    protocol: Mapping[str, Any],
    *,
    include_32_grid: bool = False,
    phase: str = "development",
    excluded_model_roles: tuple[str, ...] = (),
    problem_ids_dir: Path = Path(
        "benchmark/FalseConsensus/governor_v2/generated/problem_ids"
    ),
) -> List[Dict[str, Any]]:
    if phase not in {"development", "confirmation", "all"}:
        raise ValueError(f"unsupported phase: {phase}")
    collection = protocol["collection"]
    selection = protocol["selection"]
    output_root = Path(str(collection["output_root"]))
    collect_main = "benchmark/FalseConsensus/governor_v2/collect_main.py"
    dense_probe = "benchmark/FalseConsensus/governor_v2/dense_probe.py"
    jobs = []
    excluded_roles = set(excluded_model_roles)
    phases = (
        ("development", "confirmation") if phase == "all" else (phase,)
    )
    for current_phase in phases:
      phase_policy = selection["phase_policy"][current_phase]
      allowed_roles = set(phase_policy["model_roles"])
      visible_ratio_splits = list(phase_policy["splits"])
      include_external = bool(phase_policy["include_external_stress"])
      for benchmark in protocol["environments"]["benchmarks"]:
        if not benchmark.get("enabled_for_collection", False):
            continue
        benchmark_name = str(benchmark["name"])
        split_policy = str(benchmark.get("split_policy", "ratio"))
        if split_policy == "external_stress":
            if not include_external:
                continue
            split_labels = ["external_stress"]
            split_file_label = "external_stress"
        else:
            split_labels = visible_ratio_splits
            split_file_label = "_".join(split_labels)
        problem_ids_file = (
            problem_ids_dir
            / f"{benchmark_name}__{split_file_label}.txt"
        )
        budget = int(
            benchmark.get("capture_cap", benchmark.get("budget", 0))
        )
        if budget <= 0:
            raise ValueError(
                f"{benchmark_name} requires a positive capture_cap"
            )
        for model in protocol["environments"]["models"]:
            if not model.get("enabled", True):
                continue
            model_role = str(model.get("role", "development"))
            if model_role not in allowed_roles:
                continue
            if model_role in excluded_roles:
                continue
            model_id = str(model["id"])
            environment_slug = f"{slug(model_id)}__{slug(benchmark_name)}"
            seed_key = f"{current_phase}_seeds"
            seeds = list(
                model.get(
                    seed_key,
                    protocol["environments"].get(seed_key, []),
                )
            )
            for seed in seeds:
                run_slug = (
                    f"{current_phase}__{environment_slug}"
                    f"__seed_{int(seed)}"
                )
                main_output = output_root / run_slug / "main"
                probe_output = output_root / run_slug / "dense_simple32"
                main_job_id = f"main__{run_slug}"
                main_command = [
                    "python",
                    collect_main,
                    "--dataset",
                    benchmark_name,
                    "--model",
                    model_id,
                    "--budget",
                    str(budget),
                    "--temperature",
                    str(collection["temperature"]),
                    "--top-p",
                    str(collection["top_p"]),
                    "--seed",
                    str(seed),
                    "--workers",
                    str(collection["workers"]),
                    "--url",
                    str(collection["url"]),
                    "--problem-ids-file",
                    str(problem_ids_file),
                    "--protocol-version",
                    str(protocol["protocol_version"]),
                    "--phase",
                    current_phase,
                    "--model-role",
                    model_role,
                    "--split-labels",
                    ",".join(split_labels),
                    "--output",
                    str(main_output),
                ]
                source_path = benchmark.get("source", {}).get("path")
                if source_path:
                    source_path = Path(str(source_path))
                    main_command.extend(["--dataset-path", str(source_path)])
                probe_command = [
                    "python",
                    dense_probe,
                    "--main-run",
                    str(main_output),
                    "--output",
                    str(probe_output),
                    "--url",
                    str(collection["url"]),
                    "--interval",
                    str(collection["dense_probe_interval"]),
                    "--start-token",
                    str(collection["dense_probe_start_token"]),
                    "--probe-tokens",
                    str(collection["probe_output_cap"]),
                    "--workers",
                    str(collection["workers"]),
                ]
                common = {
                    "model": model_id,
                    "model_family": model.get("family", "unknown"),
                    "model_role": model_role,
                    "benchmark": benchmark_name,
                    "benchmark_role": benchmark.get(
                        "split_policy", "ratio"
                    ),
                    "seed": int(seed),
                    "phase": current_phase,
                    "visible_splits": split_labels,
                    "problem_ids_file": str(problem_ids_file),
                    "minimum_bf16_gpus_32gb": int(
                        model.get("minimum_bf16_gpus_32gb", 1)
                    ),
                    "capture_cap": budget,
                    "evaluation_budgets": list(
                        benchmark.get("evaluation_budgets", [])
                    ),
                }
                jobs.append(
                    {
                        "job_id": main_job_id,
                        "stage": "main_generation",
                        "depends_on": None,
                        "output": str(main_output),
                        "command": main_command,
                        "command_shell": command_text(main_command),
                        **common,
                    }
                )
                if include_32_grid:
                    offset_output = (
                        output_root
                        / run_slug
                        / "dense_simple32_offset32_stride64"
                    )
                    offset_command = [
                        "python",
                        dense_probe,
                        "--main-run",
                        str(main_output),
                        "--output",
                        str(offset_output),
                        "--url",
                        str(collection["url"]),
                        "--interval",
                        "64",
                        "--start-token",
                        "32",
                        "--probe-tokens",
                        str(collection["probe_output_cap"]),
                        "--workers",
                        str(collection["workers"]),
                    ]
                    jobs.append(
                        {
                            "job_id": f"probe32offset__{run_slug}",
                            "stage": "dense_probe_32_offset",
                            "depends_on": main_job_id,
                            "output": str(offset_output),
                            "command": offset_command,
                            "command_shell": command_text(offset_command),
                            **common,
                        }
                    )
                jobs.append(
                    {
                        "job_id": f"probe__{run_slug}",
                        "stage": "dense_probe",
                        "depends_on": main_job_id,
                        "output": str(probe_output),
                        "command": probe_command,
                        "command_shell": command_text(probe_command),
                        **common,
                    }
                )
    return jobs


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    jobs = build_matrix(
        protocol,
        include_32_grid=bool(args.include_32_grid),
        phase=args.phase,
        excluded_model_roles=tuple(args.exclude_model_role),
        problem_ids_dir=args.problem_ids_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    counts = {}
    for job in jobs:
        counts[job["stage"]] = counts.get(job["stage"], 0) + 1
    print(json.dumps({"jobs": len(jobs), "by_stage": counts}, indent=2))


if __name__ == "__main__":
    main()
