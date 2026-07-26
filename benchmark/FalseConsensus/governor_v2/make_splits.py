#!/usr/bin/env python3
"""Create deterministic problem-level train/dev/test manifests per benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SPLIT_NAMES = ("train", "dev", "test")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=HERE / "generated/split_manifest.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=HERE / "generated/split_manifest.csv",
    )
    parser.add_argument(
        "--ids-dir",
        type=Path,
        default=HERE / "generated/problem_ids",
        help="write dataset-index files consumed by the collection matrix",
    )
    return parser.parse_args()


def canonical_text(value: Any) -> str:
    return " ".join(str(value).strip().split()).lower()


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_text(value).encode("utf-8")).hexdigest()


def resolve_source_path(source: Mapping[str, Any]) -> Path:
    path = Path(str(source["path"]))
    return path if path.is_absolute() else REPO_ROOT / path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_seed(*parts: Any) -> int:
    joined = "\x1f".join(str(part) for part in parts)
    return int(hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16], 16)


def apportion(total: int, ratios: Mapping[str, float]) -> Dict[str, int]:
    if set(ratios) != set(SPLIT_NAMES):
        raise ValueError(
            f"ratios must define exactly {SPLIT_NAMES}, got {sorted(ratios)}"
        )
    if any(float(value) < 0.0 for value in ratios.values()):
        raise ValueError("split ratios cannot be negative")
    if abs(sum(float(value) for value in ratios.values()) - 1.0) > 1e-9:
        raise ValueError("split ratios must sum to 1")
    exact = {name: total * float(ratios[name]) for name in SPLIT_NAMES}
    counts = {name: int(exact[name]) for name in SPLIT_NAMES}
    remaining = total - sum(counts.values())
    order = sorted(
        SPLIT_NAMES,
        key=lambda name: (-(exact[name] - counts[name]), SPLIT_NAMES.index(name)),
    )
    for name in order[:remaining]:
        counts[name] += 1
    return counts


def read_records(source: Mapping[str, Any]) -> List[Dict[str, Any]]:
    path = resolve_source_path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    source_format = str(source.get("format", path.suffix.lstrip("."))).lower()
    if source_format == "jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    if source_format == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(row) for row in payload]
        records_key = str(source.get("records_key", "records"))
        return [dict(row) for row in payload[records_key]]
    if source_format == "csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ValueError(f"unsupported source format: {source_format}")


def stratum_for(
    record: Mapping[str, Any], fields: Sequence[str]
) -> Tuple[str, ...]:
    if not fields:
        return ("all",)
    return tuple(str(record.get(field, "unknown")) for field in fields)


def load_benchmark(
    benchmark: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    records = read_records(benchmark["source"])
    id_field = benchmark.get("id_field")
    text_field = str(benchmark.get("text_field", "problem"))
    strata_fields = tuple(benchmark.get("stratify_fields", []))
    rows = []
    seen_ids = set()
    for index, record in enumerate(records):
        problem_id = record.get(id_field) if id_field else index
        if problem_id is None:
            problem_id = index
        problem_id = str(problem_id)
        if problem_id in seen_ids:
            raise ValueError(
                f"{benchmark['name']} has duplicate problem_id {problem_id}"
            )
        seen_ids.add(problem_id)
        if text_field not in record:
            raise ValueError(
                f"{benchmark['name']} record {problem_id} lacks {text_field}"
            )
        strata = stratum_for(record, strata_fields)
        rows.append(
            {
                "benchmark": str(benchmark["name"]),
                "dataset_index": index,
                "problem_id": problem_id,
                "content_hash": content_hash(record[text_field]),
                "stratum": "\x1f".join(strata),
                "strata": {
                    field: str(record.get(field, "unknown"))
                    for field in strata_fields
                },
            }
        )
    return rows


def initial_stratified_assignment(
    rows: List[Dict[str, Any]],
    ratios: Mapping[str, float],
    seed: int,
) -> None:
    by_stratum: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_stratum[row["stratum"]].append(row)
    for stratum, items in sorted(by_stratum.items()):
        rng = random.Random(stable_seed(seed, rows[0]["benchmark"], stratum))
        rng.shuffle(items)
        counts = apportion(len(items), ratios)
        offset = 0
        for split in SPLIT_NAMES:
            for row in items[offset : offset + counts[split]]:
                row["split"] = split
            offset += counts[split]


def rebalance_to_exact_totals(
    rows: List[Dict[str, Any]], ratios: Mapping[str, float]
) -> None:
    target = apportion(len(rows), ratios)
    strata_sizes = Counter(row["stratum"] for row in rows)
    ideal_by_stratum = {
        stratum: apportion(size, ratios)
        for stratum, size in strata_sizes.items()
    }
    while True:
        totals = Counter(row["split"] for row in rows)
        deficits = {
            split: target[split] - totals[split]
            for split in SPLIT_NAMES
            if totals[split] < target[split]
        }
        excesses = {
            split: totals[split] - target[split]
            for split in SPLIT_NAMES
            if totals[split] > target[split]
        }
        if not deficits and not excesses:
            return
        destination = max(deficits, key=lambda split: (deficits[split], split))
        source = max(excesses, key=lambda split: (excesses[split], split))
        stratum_counts: Dict[Tuple[str, str], int] = Counter(
            (row["stratum"], row["split"]) for row in rows
        )
        candidates = [row for row in rows if row["split"] == source]
        candidates.sort(
            key=lambda row: (
                -(
                    stratum_counts[(row["stratum"], source)]
                    - ideal_by_stratum[row["stratum"]][source]
                ),
                (
                    stratum_counts[(row["stratum"], destination)]
                    - ideal_by_stratum[row["stratum"]][destination]
                ),
                row["content_hash"],
            )
        )
        if not candidates:
            raise RuntimeError("unable to rebalance split totals")
        candidates[0]["split"] = destination


def assign_benchmark(
    benchmark: Mapping[str, Any],
    rows: List[Dict[str, Any]],
    split_config: Mapping[str, Any],
) -> None:
    minimum_size = int(split_config["minimum_ratio_benchmark_size"])
    policy = str(benchmark.get("split_policy", "ratio"))
    if policy == "external_stress" or len(rows) < minimum_size:
        for row in rows:
            row["split"] = "external_stress"
        return
    if policy != "ratio":
        raise ValueError(f"unsupported split_policy: {policy}")
    ratios = split_config["ratios"]
    initial_stratified_assignment(rows, ratios, int(split_config["seed"]))
    rebalance_to_exact_totals(rows, ratios)


def validate_manifest(rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    keys = [(row["benchmark"], row["problem_id"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate benchmark/problem_id assignments")
    hash_splits: Dict[str, set] = defaultdict(set)
    hash_benchmarks: Dict[str, set] = defaultdict(set)
    for row in rows:
        hash_splits[row["content_hash"]].add(row["split"])
        hash_benchmarks[row["content_hash"]].add(row["benchmark"])
    conflicts = [
        {
            "content_hash": digest,
            "benchmarks": sorted(hash_benchmarks[digest]),
            "splits": sorted(splits),
        }
        for digest, splits in hash_splits.items()
        if len(hash_benchmarks[digest]) > 1 and len(splits) > 1
    ]
    if conflicts:
        raise ValueError(
            "cross-benchmark duplicate questions landed in different splits; "
            f"deduplicate or add an explicit shared group: {conflicts[:5]}"
        )


def build_manifest(protocol: Mapping[str, Any]) -> Dict[str, Any]:
    split_config = protocol["data_split"]
    all_rows = []
    summaries = {}
    for benchmark in protocol["environments"]["benchmarks"]:
        if not benchmark.get("enabled", True):
            continue
        if not benchmark.get("source", {}).get("path"):
            continue
        rows = load_benchmark(benchmark)
        assign_benchmark(benchmark, rows, split_config)
        all_rows.extend(rows)
        source_path = resolve_source_path(benchmark["source"])
        summaries[str(benchmark["name"])] = {
            "n_problems": len(rows),
            "split_policy": str(benchmark.get("split_policy", "ratio")),
            "counts": dict(sorted(Counter(row["split"] for row in rows).items())),
            "stratify_fields": list(benchmark.get("stratify_fields", [])),
            "source_path": str(benchmark["source"]["path"]),
            "source_sha256": file_sha256(source_path),
        }
    validate_manifest(all_rows)
    return {
        "schema_version": "governor-v2-splits-1",
        "protocol_version": protocol["protocol_version"],
        "split_seed": split_config["seed"],
        "ratios": split_config["ratios"],
        "group_unit": "canonical benchmark problem",
        "summaries": summaries,
        "assignments": sorted(
            all_rows,
            key=lambda row: (row["benchmark"], row["problem_id"]),
        ),
    }


def write_manifest(
    manifest: Mapping[str, Any],
    output_json: Path,
    output_csv: Path,
    ids_dir: Path,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    fields = [
        "benchmark",
        "dataset_index",
        "problem_id",
        "content_hash",
        "stratum",
        "split",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in manifest["assignments"]:
            writer.writerow({field: row[field] for field in fields})
    ids_dir.mkdir(parents=True, exist_ok=True)
    grouped: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for row in manifest["assignments"]:
        grouped[(str(row["benchmark"]), str(row["split"]))].append(
            int(row["dataset_index"])
        )
    for (benchmark, split), indices in sorted(grouped.items()):
        path = ids_dir / f"{benchmark}__{split}.txt"
        path.write_text(
            "".join(f"{index}\n" for index in sorted(indices)),
            encoding="utf-8",
        )
    benchmarks = sorted({benchmark for benchmark, _ in grouped})
    for benchmark in benchmarks:
        train_dev = sorted(
            grouped.get((benchmark, "train"), [])
            + grouped.get((benchmark, "dev"), [])
        )
        if train_dev:
            (ids_dir / f"{benchmark}__train_dev.txt").write_text(
                "".join(f"{index}\n" for index in train_dev),
                encoding="utf-8",
            )


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    manifest = build_manifest(protocol)
    write_manifest(
        manifest,
        args.output_json,
        args.output_csv,
        args.ids_dir,
    )
    print(json.dumps(manifest["summaries"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
