#!/usr/bin/env python3
"""Build per-rule Dev/Test coordinates for the A8 same-model Pareto plot.

Dev uses only the development-phase ``dev`` split. Test uses confirmation rows
from the same two development models and excludes held-out scale/architecture
models. This keeps both panels matched and prevents the invalid Llama run from
contaminating the cross-split comparison.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


OPERATING_BUDGET = {"math500": 16384, "amc23": 16384, "aime24": 32768}


def load_rows(paths: Sequence[Path]) -> Iterable[dict]:
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    index = quantile * (len(ordered) - 1)
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def aggregate(rows: Iterable[Mapping[str, object]], expected_envs: int) -> dict[str, dict]:
    by_rule: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        by_rule[str(row["rule_id"])].append(row)
    result: dict[str, dict] = {}
    for rule_id, rule_rows in by_rule.items():
        if len(rule_rows) != expected_envs:
            raise ValueError(
                f"{rule_id}: expected {expected_envs} environments, "
                f"observed {len(rule_rows)}"
            )
        model_drops: dict[str, list[float]] = defaultdict(list)
        benchmark_drops: dict[str, list[float]] = defaultdict(list)
        savings = []
        for row in rule_rows:
            model_drops[str(row["model"])].append(float(row["accuracy_drop_pp"]))
            benchmark_drops[str(row["benchmark"])].append(
                float(row["accuracy_drop_pp"])
            )
            savings.append(float(row["saving_fraction"]))
        result[rule_id] = {
            "drop": max(statistics.fmean(values) for values in model_drops.values()),
            "benchmark_drop": max(
                statistics.fmean(values) for values in benchmark_drops.values()
            ),
            "q20_saving": percentile(savings, 0.2),
            "positive_saving_fraction": (
                sum(value > 0 for value in savings) / len(savings)
            ),
        }
    return result


def frontier_ids(points: Mapping[str, Mapping[str, float]]) -> set[str]:
    """Return the 2-D frontier: minimize drop and maximize q20 saving."""
    ordered = sorted(
        points.items(),
        key=lambda item: (
            float(item[1]["drop"]),
            -float(item[1]["q20_saving"]),
            item[0],
        ),
    )
    frontier: set[str] = set()
    best_saving = float("-inf")
    for rule_id, metrics in ordered:
        saving = float(metrics["q20_saving"])
        if saving > best_saving + 1e-15:
            frontier.add(rule_id)
            best_saving = saving
    return frontier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", type=Path, nargs="+", required=True)
    parser.add_argument("--test", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dev_rows = (
        row
        for row in load_rows(args.dev)
        if row["phase"] == "development" and row["split"] == "dev"
    )
    test_rows = (
        row
        for row in load_rows(args.test)
        if row["phase"] == "confirmation"
        and row["split"] == "test"
        and row.get("model_role") == "development"
        and int(row["budget"]) == OPERATING_BUDGET[str(row["benchmark"])]
    )
    dev = aggregate(dev_rows, expected_envs=18)
    test = aggregate(test_rows, expected_envs=18)
    if set(dev) != set(test) or len(dev) != 17712:
        raise ValueError(
            f"rule coverage mismatch: dev={len(dev)} test={len(test)} "
            f"intersection={len(set(dev) & set(test))}"
        )
    dev_frontier = frontier_ids(dev)
    test_frontier = frontier_ids(test)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rule_id",
                "dev_worst_model_drop_pp",
                "dev_worst_benchmark_drop_pp",
                "dev_q20_total_token_saving",
                "dev_positive_saving_fraction",
                "dev_frontier",
                "test_worst_model_drop_pp",
                "test_worst_benchmark_drop_pp",
                "test_q20_total_token_saving",
                "test_positive_saving_fraction",
                "test_frontier",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for rule_id in sorted(dev):
            writer.writerow(
                {
                    "rule_id": rule_id,
                    "dev_worst_model_drop_pp": dev[rule_id]["drop"],
                    "dev_worst_benchmark_drop_pp": dev[rule_id][
                        "benchmark_drop"
                    ],
                    "dev_q20_total_token_saving": dev[rule_id]["q20_saving"],
                    "dev_positive_saving_fraction": dev[rule_id][
                        "positive_saving_fraction"
                    ],
                    "dev_frontier": rule_id in dev_frontier,
                    "test_worst_model_drop_pp": test[rule_id]["drop"],
                    "test_worst_benchmark_drop_pp": test[rule_id][
                        "benchmark_drop"
                    ],
                    "test_q20_total_token_saving": test[rule_id]["q20_saving"],
                    "test_positive_saving_fraction": test[rule_id][
                        "positive_saving_fraction"
                    ],
                    "test_frontier": rule_id in test_frontier,
                }
            )
    print(
        json.dumps(
            {
                "rules": len(dev),
                "dev_frontier": len(dev_frontier),
                "test_frontier": len(test_frontier),
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
