"""Audit, summarize, and deterministically pack the DEER cap-30 bank."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from . import common
from .deer_confidence_bank import (
    DEFAULT_MAX_ATTEMPTS,
    METHOD,
    PROBE_SCHEMA,
    RUN_SCHEMA,
)


ARCHIVE_NAME = "trials.jsonl.gz"
MANIFEST_NAME = "bank_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iter_archive(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def iter_payloads(
    environment: Path, *, archives_only: bool = False
) -> Iterable[dict[str, Any]]:
    trial_dir = environment / "trials"
    paths = sorted(trial_dir.glob("problem_*.json"))
    if paths and not archives_only:
        for path in paths:
            yield common.load_json(path)
        return
    archive = environment / ARCHIVE_NAME
    if not archive.exists():
        raise ValueError(f"no trial records or archive in {environment}")
    yield from _iter_archive(archive)


def pack_environment(environment: Path) -> dict[str, Any]:
    """Write one deterministic gzip JSONL archive without deleting raw files."""
    paths = sorted((environment / "trials").glob("problem_*.json"))
    if not paths:
        raise ValueError(f"cannot pack without raw trials: {environment}")
    destination = environment / ARCHIVE_NAME
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as zipped:
            for path in paths:
                payload = common.load_json(path)
                line = (
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                zipped.write(line.encode("utf-8"))
    os.replace(temporary, destination)
    # Verify decompression and row count before returning.
    archived_rows = sum(1 for _ in _iter_archive(destination))
    if archived_rows != len(paths):
        raise ValueError(
            f"archive row count {archived_rows} != raw count {len(paths)}"
        )
    return {
        "archive": str(destination),
        "rows": archived_rows,
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def wilson_interval(successes: int, total: int, z: float = 1.95996398454) -> list[float]:
    if total <= 0:
        return [float("nan"), float("nan")]
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return [center - radius, center + radius]


def environment_metadata(environment: Path) -> tuple[str, str, int]:
    # <scope>/<model_key>__<benchmark>__seed_<seed>
    parts = environment.name.split("__")
    if len(parts) != 3 or not parts[2].startswith("seed_"):
        raise ValueError(f"unexpected environment name: {environment.name}")
    return parts[0], parts[1], int(parts[2].removeprefix("seed_"))


def audit_environment(
    environment: Path, *, archives_only: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = environment / MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(f"missing manifest: {manifest_path}")
    manifest = common.load_json(manifest_path)
    settings = manifest.get("bank_settings", {})
    completion = manifest.get("completion", {})
    if manifest.get("schema_version") != RUN_SCHEMA:
        raise ValueError(f"wrong run schema: {manifest_path}")
    if settings.get("method") != METHOD:
        raise ValueError(f"wrong method: {manifest_path}")
    if int(settings.get("max_attempts", -1)) != DEFAULT_MAX_ATTEMPTS:
        raise ValueError(f"wrong max_attempts: {manifest_path}")
    if settings.get("formal_readout") is not False:
        raise ValueError(f"readout must be disabled: {manifest_path}")
    if settings.get("early_exit") is not False:
        raise ValueError(f"early exit must be disabled: {manifest_path}")
    if (
        completion.get("complete") is not True
        or int(completion.get("missing_problem_count", -1)) != 0
        or int(completion.get("recorded_failures", -1)) != 0
    ):
        raise ValueError(f"incomplete collection: {manifest_path}")

    model_key, benchmark, seed = environment_metadata(environment)
    payloads = list(iter_payloads(environment, archives_only=archives_only))
    expected = int(settings["expected_problem_count"])
    if len(payloads) != expected:
        raise ValueError(
            f"{environment}: {len(payloads)} payloads != expected {expected}"
        )

    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    reused = generated = invalid_answers = 0
    for payload in payloads:
        if payload.get("schema_version") != PROBE_SCHEMA:
            raise ValueError(f"{environment}: wrong problem schema")
        if payload.get("method") != METHOD:
            raise ValueError(f"{environment}: wrong problem method")
        if int(payload.get("max_attempts", -1)) != DEFAULT_MAX_ATTEMPTS:
            raise ValueError(f"{environment}: wrong problem cap")
        if payload.get("formal_readout") is not False or "readout" in payload:
            raise ValueError(f"{environment}: forbidden formal readout")
        problem_id = int(payload["problem_id"])
        if problem_id in seen:
            raise ValueError(f"{environment}: duplicate problem {problem_id}")
        seen.add(problem_id)
        trials = payload.get("trials")
        if not isinstance(trials, list):
            raise ValueError(f"{environment}: non-list trials")
        expected_candidates = int(payload["expected_candidate_count"])
        if len(trials) != expected_candidates:
            raise ValueError(
                f"{environment}/p{problem_id}: {len(trials)} trials != "
                f"{expected_candidates}"
            )
        ids = [int(row.get("candidate_id", -1)) for row in trials]
        if ids != list(range(1, expected_candidates + 1)):
            raise ValueError(f"{environment}/p{problem_id}: non-sequential ids")
        if any("error" in row for row in trials):
            raise ValueError(f"{environment}/p{problem_id}: recorded trial error")
        if any(not isinstance(row.get("logprobs"), list) or not row["logprobs"] for row in trials):
            raise ValueError(f"{environment}/p{problem_id}: missing logprobs")

        payload_reused = int(payload.get("reused_trial_count", 0))
        payload_generated = int(payload.get("generated_trial_count", 0))
        if payload_reused + payload_generated != len(trials):
            raise ValueError(
                f"{environment}/p{problem_id}: reuse/generated accounting "
                "does not equal trials"
            )
        reused += payload_reused
        generated += payload_generated
        invalid_answers += sum(not str(row.get("trial_answer", "")).strip() for row in trials)
        raw_hits = {
            cap: any(
                int(row["candidate_id"]) <= cap
                and float(row["confidence"]) > 0.995
                for row in trials
            )
            for cap in (10, 20, 30)
        }
        valid_hits = {
            cap: any(
                int(row["candidate_id"]) <= cap
                and float(row["confidence"]) > 0.995
                and bool(str(row.get("trial_answer", "")).strip())
                for row in trials
            )
            for cap in (10, 20, 30)
        }
        rows.append(
            {
                "scope": environment.parent.name,
                "model_key": model_key,
                "benchmark": benchmark,
                "seed": seed,
                "problem_id": problem_id,
                "candidate_count": len(trials),
                **{f"raw_hit_{cap}": raw_hits[cap] for cap in (10, 20, 30)},
                **{
                    f"valid_hit_{cap}": valid_hits[cap]
                    for cap in (10, 20, 30)
                },
            }
        )

    archive = environment / ARCHIVE_NAME
    return (
        {
            "scope": environment.parent.name,
            "environment": environment.name,
            "model_key": model_key,
            "benchmark": benchmark,
            "seed": seed,
            "problems": len(payloads),
            "trials": sum(row["candidate_count"] for row in rows),
            "reused_trials": reused,
            "generated_trials": generated,
            "invalid_trial_answers": invalid_answers,
            "archive": (
                {
                    "path": str(archive),
                    "bytes": archive.stat().st_size,
                    "sha256": _sha256(archive),
                }
                if archive.exists()
                else None
            ),
        },
        rows,
    )


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[("all", "all")].append(row)
        groups[(str(row["scope"]), "all")].append(row)
        groups[("all", str(row["model_key"]))].append(row)
        groups[(str(row["scope"]), str(row["model_key"]))].append(row)

    summary: dict[str, Any] = {}
    for (scope, model), group in sorted(groups.items()):
        key = f"{scope}__{model}"
        total = len(group)
        item: dict[str, Any] = {"n": total}
        for validity in ("raw", "valid"):
            for cap in (10, 20, 30):
                hits = sum(bool(row[f"{validity}_hit_{cap}"]) for row in group)
                item[f"{validity}_hit_{cap}"] = {
                    "hits": hits,
                    "probability": hits / total,
                    "wilson_95": wilson_interval(hits, total),
                }
            item[f"{validity}_increment_10_to_20_pp"] = 100 * (
                item[f"{validity}_hit_20"]["probability"]
                - item[f"{validity}_hit_10"]["probability"]
            )
            item[f"{validity}_increment_20_to_30_pp"] = 100 * (
                item[f"{validity}_hit_30"]["probability"]
                - item[f"{validity}_hit_20"]["probability"]
            )
        summary[key] = item
    return summary


def find_environments(root: Path) -> list[Path]:
    return sorted(
        path.parent
        for path in root.glob("*/*/" + MANIFEST_NAME)
        if path.parent.is_dir()
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and pack the DEER cap-30 confidence bank"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack", action="store_true")
    parser.add_argument(
        "--archives-only",
        action="store_true",
        help="ignore resumable raw trials and validate committed archives",
    )
    parser.add_argument("--expected-environments", type=int, default=36)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    environments = find_environments(args.root)
    if len(environments) != args.expected_environments:
        raise ValueError(
            f"found {len(environments)} environments, expected "
            f"{args.expected_environments}"
        )
    if args.pack:
        for environment in environments:
            packed = pack_environment(environment)
            print(
                f"packed {environment}: {packed['rows']} rows, "
                f"{packed['bytes']} bytes"
            )

    environment_rows: list[dict[str, Any]] = []
    problem_rows: list[dict[str, Any]] = []
    for environment in environments:
        environment_row, rows = audit_environment(
            environment, archives_only=args.archives_only
        )
        environment_rows.append(environment_row)
        problem_rows.extend(rows)

    scope_counts = Counter(row["scope"] for row in problem_rows)
    result = {
        "schema_version": "deer-confidence-bank-cap30-audit-1",
        "method": METHOD,
        "root": str(args.root),
        "max_attempts": DEFAULT_MAX_ATTEMPTS,
        "confidence_threshold_of_interest": 0.995,
        "direct_submit_validity_gate": "non-empty parsed trial_answer",
        "environment_count": len(environment_rows),
        "problem_count": len(problem_rows),
        "scope_problem_counts": dict(sorted(scope_counts.items())),
        "trial_count": sum(row["trials"] for row in environment_rows),
        "reused_trial_count": sum(
            row["reused_trials"] for row in environment_rows
        ),
        "generated_trial_count": sum(
            row["generated_trials"] for row in environment_rows
        ),
        "invalid_trial_answer_count": sum(
            row["invalid_trial_answers"] for row in environment_rows
        ),
        "environments": environment_rows,
        "hit_summary": summarize_rows(problem_rows),
    }
    common.atomic_write_json(args.output, result)
    print(json.dumps(result["hit_summary"]["all__all"], indent=2))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
