#!/usr/bin/env python3
"""Fail-fast validation of all local artifacts needed before GPU collection."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))

from benchmark.FalseConsensus.governor_v2.make_splits import file_sha256
from benchmark.FalseConsensus.governor_v2.rule_schema import RuleSpec
from clients import apply_chat_template


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    protocol_path = HERE / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    generated = HERE / "generated"
    split_path = generated / "split_manifest.json"
    split = json.loads(split_path.read_text(encoding="utf-8"))
    for benchmark in protocol["environments"]["benchmarks"]:
        source = Path(benchmark["source"]["path"])
        source = source if source.is_absolute() else REPO_ROOT / source
        if not source.exists():
            raise FileNotFoundError(source)
        expected = split["summaries"][benchmark["name"]]["source_sha256"]
        if file_sha256(source) != expected:
            raise ValueError(f"source hash mismatch: {benchmark['name']}")
    assignments = split["assignments"]
    counts = Counter((row["benchmark"], row["split"]) for row in assignments)
    expected_counts = {
        ("math500", "train"): 300,
        ("math500", "dev"): 100,
        ("math500", "test"): 100,
        ("gsm8k", "train"): 791,
        ("gsm8k", "dev"): 264,
        ("gsm8k", "test"): 264,
        ("amc23", "external_stress"): 40,
        ("aime24", "external_stress"): 30,
    }
    if counts != Counter(expected_counts):
        raise ValueError(f"unexpected split counts: {counts}")
    rules_path = generated / "candidate_rules.jsonl"
    rules = [RuleSpec.from_dict(row) for row in load_jsonl(rules_path)]
    if len(rules) != 16848 or len({rule.rule_id for rule in rules}) != len(rules):
        raise ValueError("candidate rule count/IDs are not frozen as expected")
    expected_matrices = {
        "development_matrix.jsonl": (24, "development"),
        "confirmation_matrix_base64.jsonl": (64, "confirmation"),
        "confirmation_small_models_base64.jsonl": (56, "confirmation"),
    }
    for filename, (expected_rows, phase) in expected_matrices.items():
        rows = load_jsonl(generated / filename)
        if len(rows) != expected_rows:
            raise ValueError(f"{filename}: expected {expected_rows}, got {len(rows)}")
        if {row["phase"] for row in rows} != {phase}:
            raise ValueError(f"{filename}: phase contamination")
        for row in rows:
            if any(Path(value).is_absolute() for value in row["command"] if "/" in value):
                raise ValueError(f"{filename}: non-portable absolute command path")
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
        != scale_model["minimum_bf16_gpus_32gb"]
    ):
        raise ValueError("32B handoff config disagrees with frozen protocol")
    base_scale_jobs = [
        row
        for row in load_jsonl(generated / "confirmation_matrix_base64.jsonl")
        if row["model"] == handoff["model"]
    ]
    if len(base_scale_jobs) != 8:
        raise ValueError("32B handoff matrix must contain 4 environments")
    print(
        json.dumps(
            {
                "protocol_version": protocol["protocol_version"],
                "protocol_sha256": file_sha256(protocol_path),
                "split_manifest_sha256": file_sha256(split_path),
                "problems": len(assignments),
                "candidate_rules": len(rules),
                "matrices": {
                    name: count for name, (count, _) in expected_matrices.items()
                },
                "status": "READY_FOR_GPU_SMOKE",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
