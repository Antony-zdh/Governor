#!/usr/bin/env python3
"""Fail-fast validation of all local artifacts needed before GPU collection."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))

from benchmark.FalseConsensus.governor_v2.build_experiment_matrix import (
    build_matrix,
)
from benchmark.FalseConsensus.governor_v2.make_splits import (
    file_sha256,
    validate_manifest,
)
from benchmark.FalseConsensus.governor_v2.rule_schema import (
    RuleSpec,
    expand_search_space,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-model-template-check",
        action="store_true",
        help=(
            "validate frozen artifacts without loading transformers; the "
            "full check remains mandatory on the GPU server"
        ),
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    args = parse_args()
    protocol_path = HERE / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    generated = HERE / "generated"
    split_path = generated / "split_manifest.json"
    split = json.loads(split_path.read_text(encoding="utf-8"))
    for benchmark in protocol["environments"]["benchmarks"]:
        if not benchmark.get("enabled", True):
            continue
        source = Path(benchmark["source"]["path"])
        source = source if source.is_absolute() else REPO_ROOT / source
        if not source.exists():
            raise FileNotFoundError(source)
        expected = split["summaries"][benchmark["name"]]["source_sha256"]
        if file_sha256(source) != expected:
            raise ValueError(f"source hash mismatch: {benchmark['name']}")
    assignments = split["assignments"]
    validate_manifest(assignments)
    counts = Counter((row["benchmark"], row["split"]) for row in assignments)
    expected_counts = {
        ("math500", "train"): 300,
        ("math500", "dev"): 100,
        ("math500", "test"): 100,
        ("amc23", "train"): 24,
        ("amc23", "dev"): 8,
        ("amc23", "test"): 8,
        ("aime24", "train"): 18,
        ("aime24", "dev"): 6,
        ("aime24", "test"): 6,
    }
    if counts != Counter(expected_counts):
        raise ValueError(f"unexpected split counts: {counts}")
    rules_path = generated / "candidate_rules.jsonl"
    rules = [RuleSpec.from_dict(row) for row in load_jsonl(rules_path)]
    if len(rules) != 17712 or len({rule.rule_id for rule in rules}) != len(rules):
        raise ValueError("candidate rule count/IDs are not frozen as expected")
    expected_rules = expand_search_space(protocol["rule_search"])
    if [rule.to_dict() for rule in rules] != [
        rule.to_dict() for rule in expected_rules
    ]:
        raise ValueError("candidate rules do not exactly match protocol expansion")
    selection = protocol["selection"]
    operating_points = selection.get("operating_points", [])
    names = [str(point.get("name", "")) for point in operating_points]
    if (
        names != ["conservative", "balanced", "token_efficient"]
        or len(set(names)) != len(names)
        or int(selection.get("minimum_distinct_selected_rules", 0)) != 3
    ):
        raise ValueError("three distinct Pareto operating points are not frozen")
    for point in operating_points:
        if (
            float(point["accuracy_drop_pp_max_per_model"]) < 0
            or float(point["accuracy_drop_pp_max_per_benchmark"]) < 0
            or not 0
            < float(
                point[
                    "minimum_fraction_environments_with_positive_saving"
                ]
            )
            <= 1
        ):
            raise ValueError(f"invalid operating-point gates: {point}")
    maximum_capture_cap = max(
        int(benchmark["capture_cap"])
        for benchmark in protocol["environments"]["benchmarks"]
        if benchmark.get("enabled_for_collection", False)
    )
    for model in protocol["environments"]["models"]:
        maximum_model_length = int(model["maximum_model_length"])
        if maximum_model_length < maximum_capture_cap + 8192:
            raise ValueError(
                f"{model['id']}: maximum_model_length leaves less than "
                "8192 tokens above the largest capture cap"
            )
    expected_matrices = {
        "development_matrix.jsonl": (
            54,
            "development",
            build_matrix(protocol, phase="development"),
        ),
        "confirmation_matrix_base64.jsonl": (
            72,
            "confirmation",
            build_matrix(protocol, phase="confirmation"),
        ),
        "confirmation_small_models_base64.jsonl": (
            63,
            "confirmation",
            build_matrix(
                protocol,
                phase="confirmation",
                excluded_model_roles=("heldout_scale",),
            ),
        ),
    }
    for filename, (expected_rows, phase, expected) in expected_matrices.items():
        rows = load_jsonl(generated / filename)
        if len(rows) != expected_rows:
            raise ValueError(f"{filename}: expected {expected_rows}, got {len(rows)}")
        if rows != expected:
            raise ValueError(f"{filename}: stale or edited matrix")
        if {row["phase"] for row in rows} != {phase}:
            raise ValueError(f"{filename}: phase contamination")
        for row in rows:
            if any(Path(value).is_absolute() for value in row["command"] if "/" in value):
                raise ValueError(f"{filename}: non-portable absolute command path")
    ids_dir = generated / "problem_ids"
    for benchmark in (
        item
        for item in protocol["environments"]["benchmarks"]
        if item.get("enabled_for_collection", False)
    ):
        name = str(benchmark["name"])
        benchmark_rows = [
            row for row in assignments if row["benchmark"] == name
        ]
        by_split = {
            split_name: sorted(
                int(row["dataset_index"])
                for row in benchmark_rows
                if row["split"] == split_name
            )
            for split_name in ("train", "dev", "test")
        }
        by_split["train_dev"] = sorted(
            by_split["train"] + by_split["dev"]
        )
        for split_name, expected_ids in by_split.items():
            path = ids_dir / f"{name}__{split_name}.txt"
            observed_ids = [
                int(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if observed_ids != expected_ids:
                raise ValueError(f"problem ID file disagrees with split: {path}")
    if not args.skip_model_template_check:
        from clients import apply_chat_template

        for model in protocol["environments"]["models"]:
            rendered = apply_chat_template("Return \\boxed{1}.", model["id"])
            if not rendered or "boxed" not in rendered:
                raise ValueError(f"chat template failed: {model['id']}")
    handoff = json.loads(
        (HERE / "heldout_32b_config.json").read_text(encoding="utf-8")
    )
    scale_model = next(
        model
        for model in protocol["environments"]["models"]
        if model["role"] == "heldout_scale"
    )
    if (
        handoff["protocol_version"] != protocol["protocol_version"]
        or handoff["model"] != scale_model["id"]
        or handoff["hardware"]["minimum_gpu_count"]
        != scale_model["target_a100_80gb_gpus"]
        or handoff["hardware"]["maximum_model_length"]
        != scale_model["maximum_model_length"]
    ):
        raise ValueError("32B handoff config disagrees with frozen protocol")
    base_scale_jobs = [
        row
        for row in load_jsonl(generated / "confirmation_matrix_base64.jsonl")
        if row["model"] == handoff["model"]
    ]
    if len(base_scale_jobs) != 9:
        raise ValueError(
            "32B handoff matrix must contain 3 three-stage environments"
        )
    print(
        json.dumps(
            {
                "protocol_version": protocol["protocol_version"],
                "protocol_sha256": file_sha256(protocol_path),
                "split_manifest_sha256": file_sha256(split_path),
                "problems": len(assignments),
                "candidate_rules": len(rules),
                "model_template_check": (
                    "skipped_locally"
                    if args.skip_model_template_check
                    else "passed"
                ),
                "matrices": {
                    name: count
                    for name, (count, _, _) in expected_matrices.items()
                },
                "status": "READY_FOR_GPU_SMOKE",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
