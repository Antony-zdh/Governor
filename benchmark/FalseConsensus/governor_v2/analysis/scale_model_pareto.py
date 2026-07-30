#!/usr/bin/env python3
"""Validate and summarize a single-model Governor-v2 scale sweep.

The sweep file may contain train/dev/test rows, but the protocol Pareto
frontier and operating-point eligibility use train+dev only. Test is reported
solely as a held-out cross-split diagnostic.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.governor_v2.replay_rules import (  # noqa: E402
    load_jsonl,
    pareto_frontier,
    percentile,
    selection_candidates,
)
from benchmark.FalseConsensus.governor_v2.rule_schema import RuleSpec  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_metrics(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error


def split_metrics(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["split"])].append(row)
    for split, split_rows in grouped.items():
        benchmark_drops: dict[str, list[float]] = defaultdict(list)
        savings = []
        drops = []
        for row in split_rows:
            drop = float(row["accuracy_drop_pp"])
            benchmark_drops[str(row["benchmark"])].append(drop)
            drops.append(drop)
            savings.append(float(row["saving_fraction"]))
        result[split] = {
            "mean_accuracy_drop_pp": statistics.fmean(drops),
            "worst_benchmark_accuracy_drop_pp": max(
                statistics.fmean(values)
                for values in benchmark_drops.values()
            ),
            "q20_saving_fraction": percentile(savings, 0.2),
            "mean_saving_fraction": statistics.fmean(savings),
            "positive_saving_fraction": (
                sum(value > 0 for value in savings) / len(savings)
            ),
        }
    return result


def pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Pearson correlation requires matched nontrivial inputs")
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    covariance = sum(
        (x - mean_left) * (y - mean_right)
        for x, y in zip(left, right)
    )
    scale_left = math.sqrt(sum((x - mean_left) ** 2 for x in left))
    scale_right = math.sqrt(sum((y - mean_right) ** 2 for y in right))
    return covariance / (scale_left * scale_right)


def main() -> None:
    args = parse_args()
    rule_specs = [
        RuleSpec.from_dict(row) for row in load_jsonl(args.rules)
    ]
    rules = {rule.rule_id: rule for rule in rule_specs}
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))

    rows_by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    environment_reference: set[tuple[Any, ...]] | None = None
    models = set()
    identities = set()
    row_count = 0
    for row in load_metrics(args.metrics):
        row_count += 1
        rule_id = str(row["rule_id"])
        if rule_id not in rules:
            raise ValueError(f"unknown rule in metrics: {rule_id}")
        if row["phase"] != "development":
            raise ValueError(f"non-development row in scale sweep: {row}")
        identity = (
            rule_id,
            str(row["split"]),
            str(row["model"]),
            str(row["benchmark"]),
            int(row["seed"]),
            int(row["budget"]),
        )
        if identity in identities:
            raise ValueError(f"duplicate metric identity: {identity}")
        identities.add(identity)
        models.add(str(row["model"]))
        rows_by_rule[rule_id].append(row)

    if len(models) != 1:
        raise ValueError(f"expected exactly one model, observed {sorted(models)}")
    if set(rows_by_rule) != set(rules):
        raise ValueError(
            "rule coverage mismatch: "
            f"metrics={len(rows_by_rule)} candidates={len(rules)}"
        )
    for rule_id, rows in rows_by_rule.items():
        environments = {
            (
                str(row["split"]),
                str(row["model"]),
                str(row["benchmark"]),
                int(row["seed"]),
                int(row["budget"]),
            )
            for row in rows
        }
        if environment_reference is None:
            environment_reference = environments
        elif environments != environment_reference:
            raise ValueError(
                f"incomplete/contaminated environment coverage: {rule_id}"
            )
    if environment_reference is None:
        raise ValueError("empty metrics file")
    split_counts = Counter(item[0] for item in environment_reference)
    if set(split_counts) != {"train", "dev", "test"}:
        raise ValueError(f"unexpected split coverage: {split_counts}")

    selection_rows = [
        row
        for rows in rows_by_rule.values()
        for row in rows
        if row["split"] in {"train", "dev"}
    ]
    candidates = selection_candidates(selection_rows, rules)
    frontier = pareto_frontier(candidates)
    frontier_ids = {str(row["rule_id"]) for row in frontier}
    candidate_by_id = {str(row["rule_id"]): row for row in candidates}
    per_split = {
        rule_id: split_metrics(rows)
        for rule_id, rows in rows_by_rule.items()
    }

    profiles = protocol["selection"]["operating_points"]
    operating_points = {}
    for profile in profiles:
        eligible = [
            row
            for row in frontier
            if float(row["max_model_accuracy_drop_pp"])
            <= float(profile["accuracy_drop_pp_max_per_model"])
            and float(row["max_benchmark_accuracy_drop_pp"])
            <= float(profile["accuracy_drop_pp_max_per_benchmark"])
            and float(row["positive_saving_fraction"])
            >= float(
                profile[
                    "minimum_fraction_environments_with_positive_saving"
                ]
            )
        ]
        eligible.sort(
            key=lambda row: (
                -float(row["dev_q20_saving_fraction"]),
                -float(row["positive_saving_fraction"]),
                int(row["complexity"]),
                str(row["rule_id"]),
            )
        )
        operating_points[str(profile["name"])] = {
            "eligible_frontier_rules": len(eligible),
            "best_rule_id": (
                str(eligible[0]["rule_id"]) if eligible else None
            ),
            "best_metrics": dict(eligible[0]) if eligible else None,
        }

    ordered_rule_ids = sorted(rules)
    dev_worst = [
        per_split[rule_id]["dev"]["worst_benchmark_accuracy_drop_pp"]
        for rule_id in ordered_rule_ids
    ]
    test_worst = [
        per_split[rule_id]["test"]["worst_benchmark_accuracy_drop_pp"]
        for rule_id in ordered_rule_ids
    ]
    dev_floor_rule = min(
        ordered_rule_ids,
        key=lambda rule_id: (
            per_split[rule_id]["dev"][
                "worst_benchmark_accuracy_drop_pp"
            ],
            -per_split[rule_id]["dev"]["q20_saving_fraction"],
            int(candidate_by_id[rule_id]["complexity"]),
            rule_id,
        ),
    )
    test_floor_rule = min(
        ordered_rule_ids,
        key=lambda rule_id: (
            per_split[rule_id]["test"][
                "worst_benchmark_accuracy_drop_pp"
            ],
            -per_split[rule_id]["test"]["q20_saving_fraction"],
            int(candidate_by_id[rule_id]["complexity"]),
            rule_id,
        ),
    )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rule_id",
        "pareto_frontier",
        "complexity",
        "train_dev_worst_model_accuracy_drop_pp",
        "train_dev_worst_benchmark_accuracy_drop_pp",
        "dev_q20_saving_fraction",
        "train_q20_saving_fraction",
        "mean_dev_saving_fraction",
        "train_dev_positive_saving_fraction",
        "dev_worst_benchmark_accuracy_drop_pp",
        "dev_mean_accuracy_drop_pp",
        "dev_mean_saving_fraction",
        "test_worst_benchmark_accuracy_drop_pp",
        "test_mean_accuracy_drop_pp",
        "test_q20_saving_fraction",
        "test_mean_saving_fraction",
    ]
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for rule_id in ordered_rule_ids:
            candidate = candidate_by_id[rule_id]
            dev = per_split[rule_id]["dev"]
            test = per_split[rule_id]["test"]
            writer.writerow(
                {
                    "rule_id": rule_id,
                    "pareto_frontier": rule_id in frontier_ids,
                    "complexity": candidate["complexity"],
                    "train_dev_worst_model_accuracy_drop_pp": candidate[
                        "max_model_accuracy_drop_pp"
                    ],
                    "train_dev_worst_benchmark_accuracy_drop_pp": candidate[
                        "max_benchmark_accuracy_drop_pp"
                    ],
                    "dev_q20_saving_fraction": candidate[
                        "dev_q20_saving_fraction"
                    ],
                    "train_q20_saving_fraction": candidate[
                        "train_q20_saving_fraction"
                    ],
                    "mean_dev_saving_fraction": candidate[
                        "mean_dev_saving_fraction"
                    ],
                    "train_dev_positive_saving_fraction": candidate[
                        "positive_saving_fraction"
                    ],
                    "dev_worst_benchmark_accuracy_drop_pp": dev[
                        "worst_benchmark_accuracy_drop_pp"
                    ],
                    "dev_mean_accuracy_drop_pp": dev[
                        "mean_accuracy_drop_pp"
                    ],
                    "dev_mean_saving_fraction": dev[
                        "mean_saving_fraction"
                    ],
                    "test_worst_benchmark_accuracy_drop_pp": test[
                        "worst_benchmark_accuracy_drop_pp"
                    ],
                    "test_mean_accuracy_drop_pp": test[
                        "mean_accuracy_drop_pp"
                    ],
                    "test_q20_saving_fraction": test[
                        "q20_saving_fraction"
                    ],
                    "test_mean_saving_fraction": test[
                        "mean_saving_fraction"
                    ],
                }
            )

    summary = {
        "model": next(iter(models)),
        "metric_rows": row_count,
        "candidate_rules": len(rules),
        "environments_per_rule": len(environment_reference),
        "split_environment_counts": dict(sorted(split_counts.items())),
        "pareto_frontier_rules": len(frontier),
        "dev_test_worst_benchmark_drop_pearson_r": pearson(
            dev_worst, test_worst
        ),
        "dev_floor": {
            "rule_id": dev_floor_rule,
            **per_split[dev_floor_rule]["dev"],
            "corresponding_test": per_split[dev_floor_rule]["test"],
        },
        "test_floor_optimistic": {
            "rule_id": test_floor_rule,
            **per_split[test_floor_rule]["test"],
        },
        "operating_points": operating_points,
        "inputs": {
            "metrics": str(args.metrics),
            "metrics_sha256": sha256_file(args.metrics),
            "rules": str(args.rules),
            "rules_sha256": sha256_file(args.rules),
            "protocol": str(args.protocol),
            "protocol_sha256": sha256_file(args.protocol),
        },
        "output_csv": str(args.output_csv),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
