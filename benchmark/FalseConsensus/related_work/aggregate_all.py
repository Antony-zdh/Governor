"""Deterministic cross-environment aggregation for related-work replays.

Consumes the per-environment ``replay_rows.jsonl`` files produced by
``replay.py`` and writes the preregistered split/model/benchmark/seed,
dev-pooled, train+dev diagnostic, and benchmark-macro views.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import common, metrics


IDENTITY = ("method", "model", "dataset", "base_seed", "problem_id")
EXPECTED_METHODS = {
    "certaindex_mid_frozen", "tje_frozen", "deer_frozen",
}


def load_rows(paths: Iterable[Path], allow_test: bool = False) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple] = set()
    for path in sorted(Path(p) for p in paths):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                key = tuple(row.get(k) for k in IDENTITY)
                if key in seen:
                    raise ValueError(f"duplicate row {key} at {path}:{line_number}")
                if row.get("split") == "test" and not allow_test:
                    raise ValueError(f"test leakage at {path}:{line_number}")
                seen.add(key)
                rows.append(row)
    return rows


def baseline_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    return [
        {
            "model": row.get("model"),
            "dataset": row.get("dataset"),
            "base_seed": row.get("base_seed"),
            "problem_id": row.get("problem_id"),
            "correct": row.get("baseline_correct"),
            "all_generated_tokens": row.get("baseline_all_generated_tokens"),
            "baseline_all_generated_tokens": row.get("baseline_all_generated_tokens"),
        }
        for row in rows
    ]


def validate_coverage(
    rows: Sequence[Mapping[str, Any]],
    *,
    require_all_methods: bool,
    split_manifest: Path | None = None,
    allow_test: bool = False,
) -> dict:
    methods = {str(row.get("method")) for row in rows}
    if require_all_methods and methods != EXPECTED_METHODS:
        raise ValueError(f"method set {sorted(methods)} != {sorted(EXPECTED_METHODS)}")
    groups: dict[tuple, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row.get("method"), row.get("model"), row.get("dataset"),
            row.get("base_seed"),
        )
        groups[key].append(row)
    expected_envs = len(methods) * common.EXPECTED_ENV_COUNT
    if len(groups) != expected_envs:
        raise ValueError(f"environment count {len(groups)} != {expected_envs}")
    expected_ids = common.split_sets(split_manifest) if split_manifest else None
    for (method, model, dataset, seed), group in groups.items():
        if model not in common.DEVELOPMENT_MODELS:
            raise ValueError(f"unauthorized model in aggregate: {model}")
        if dataset not in common.DEVELOPMENT_BENCHMARKS:
            raise ValueError(f"unauthorized dataset in aggregate: {dataset}")
        if seed not in common.DEVELOPMENT_SEEDS and seed not in (45, 46, 47):
            raise ValueError(f"unauthorized seed in aggregate: {seed}")
        expected = common.EXPECTED_PROBLEM_COUNTS[dataset]
        if allow_test:
            # Test split has fewer problems than train+dev
            test_counts = {"math500": 100, "amc23": 8, "aime24": 6}
            expected = test_counts.get(dataset, expected)
        if len(group) != expected:
            raise ValueError(
                f"{method}/{model}/{dataset}/seed{seed}: {len(group)} != {expected}"
            )
        if expected_ids is not None:
            observed_ids = {int(row["problem_id"]) for row in group}
            allowed_ids = (
                expected_ids[dataset]["train"] | expected_ids[dataset]["dev"]
            )
            test_ids = expected_ids[dataset].get("test", set())
            # For test-phase data, allow test IDs; for dev data, allow train+dev
            if observed_ids != allowed_ids and not (observed_ids == test_ids):
                raise ValueError(
                    f"{method}/{model}/{dataset}/seed{seed}: problem ID set mismatch"
                )
        split_counts = defaultdict(int)
        for row in group:
            split_counts[str(row.get("split"))] += 1
        train, dev, _test = common.EXPECTED_SPLIT_COUNTS[dataset]
        # Accept dev-only (dev phase) or test-only (confirmation phase)
        if (split_counts["train"], split_counts["dev"], split_counts["test"]) != (train, dev, 0):
            # Check if it's a test-only group (confirmation phase)
            if split_counts["test"] != len(group):
                raise ValueError(
                f"{method}/{model}/{dataset}/seed{seed}: split counts "
                f"{dict(split_counts)}"
            )
    per_method = {
        method: sum(1 for row in rows if row.get("method") == method)
        for method in sorted(methods)
    }
    expected_total = common.EXPECTED_TOTAL_TRAJECTORIES
    if allow_test:
        expected_total = 684  # 2 models × 342 test trajectories/model
    for method, count in per_method.items():
        if count != expected_total:
            raise ValueError(f"{method}: {count} rows != {expected_total}")
    return {
        "ok": True,
        "method_count": len(methods),
        "environment_count": len(groups),
        "rows_per_method": per_method,
        "test_rows": 0,
    }


def summarize_group(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap: bool,
    n_samples: int,
    seed: int,
) -> dict:
    summary = metrics.aggregate(rows)
    if bootstrap:
        summary["ci"] = metrics.paired_hierarchical_ci(
            rows, baseline_rows(rows), n_samples=n_samples, seed=seed
        )
    return summary


def grouped_summaries(
    rows: Sequence[Mapping[str, Any]],
    *,
    keys: Sequence[str],
    bootstrap: bool,
    n_samples: int,
    seed: int,
) -> list[dict]:
    groups: dict[tuple, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k) for k in keys)].append(row)
    output: list[dict] = []
    for key in sorted(groups, key=lambda values: tuple(str(v) for v in values)):
        summary = summarize_group(
            groups[key], bootstrap=bootstrap, n_samples=n_samples, seed=seed
        )
        output.append({**dict(zip(keys, key)), **summary})
    return output


def macro_dev(dev_pooled: Sequence[Mapping[str, Any]]) -> list[dict]:
    groups: dict[tuple, list[Mapping[str, Any]]] = defaultdict(list)
    for row in dev_pooled:
        groups[(row["method"], row["model"])].append(row)
    fields = (
        "accuracy", "baseline_accuracy", "accuracy_diff_pp",
        "avg_main_tokens", "avg_probe_out_tokens", "avg_all_generated_tokens",
        "main_only_token_saving_fraction",
        "all_generated_token_saving_fraction", "stop_rate",
        "invalid_aux_response_rate", "capped_rate",
    )
    output = []
    for key, summaries in sorted(groups.items()):
        item = {"method": key[0], "model": key[1], "benchmark_count": len(summaries)}
        for field in fields:
            values = [float(row[field]) for row in summaries if row.get(field) is not None]
            # CPython 3.12 changed float ``sum`` relative to 3.11.  Use a
            # stable, accurately rounded reduction so identical replay rows
            # regenerate byte-identical macro aggregates across interpreters.
            item[field] = math.fsum(values) / len(values) if values else None
        output.append(item)
    return output


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key == "ci":
                continue
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: row.get(key, "") if not isinstance(row.get(key), (dict, list))
                else json.dumps(row.get(key), ensure_ascii=False, sort_keys=True)
                for key in fields
            })
    temporary.replace(path)


def build_views(
    rows: Sequence[Mapping[str, Any]],
    *,
    n_samples: int = metrics.BOOTSTRAP_SAMPLES,
    seed: int = metrics.BOOTSTRAP_SEED,
) -> dict:
    environment_split = grouped_summaries(
        rows,
        keys=("method", "model", "dataset", "base_seed", "split"),
        bootstrap=False,
        n_samples=n_samples,
        seed=seed,
    )
    dev_rows = [row for row in rows if row.get("split") == "dev"]
    test_rows = [row for row in rows if row.get("split") == "test"]
    dev_pooled = grouped_summaries(
        dev_rows if dev_rows else test_rows,
        keys=("method", "model", "dataset"),
        bootstrap=True,
        n_samples=n_samples,
        seed=seed,
    )
    train_dev = grouped_summaries(
        rows,
        keys=("method", "model", "dataset"),
        bootstrap=True,
        n_samples=n_samples,
        seed=seed,
    )
    return {
        "schema_version": "related-work-aggregate-1",
        "bootstrap_samples": n_samples,
        "bootstrap_seed": seed,
        "row_count": len(rows),
        "methods": sorted({row.get("method") for row in rows}),
        "environment_split": environment_split,
        "dev_pooled": dev_pooled,
        "train_dev_diagnostic": train_dev,
        "dev_macro": macro_dev(dev_pooled),
    }


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate related-work replay rows")
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=common.GOVERNOR_V2 / "generated" / "split_manifest.json",
    )
    parser.add_argument("--bootstrap-samples", type=int, default=metrics.BOOTSTRAP_SAMPLES)
    parser.add_argument("--bootstrap-seed", type=int, default=metrics.BOOTSTRAP_SEED)
    parser.add_argument("--allow-test", action="store_true",
                       help="allow test-split rows (confirmation phase)"),
    parser.add_argument(
        "--allow-partial", action="store_true",
        help="permit one or two methods for incremental diagnostics",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    rows = load_rows(args.inputs, allow_test=args.allow_test)
    coverage = validate_coverage(
        rows,
        require_all_methods=not args.allow_partial,
        split_manifest=args.split_manifest,
        allow_test=args.allow_test,
    )
    views = build_views(
        rows, n_samples=args.bootstrap_samples, seed=args.bootstrap_seed
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    views["coverage"] = coverage
    common.atomic_write_json(args.output_dir / "aggregate.json", views)
    for name in (
        "environment_split", "dev_pooled", "train_dev_diagnostic", "dev_macro"
    ):
        write_csv(args.output_dir / f"{name}.csv", views[name])
    print(json.dumps({
        "row_count": views["row_count"],
        "methods": views["methods"],
        "dev_cells": len(views["dev_pooled"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
