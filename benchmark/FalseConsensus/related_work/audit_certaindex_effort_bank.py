"""Audit and deterministically pack the CertaIndex effort bank (mild extension).

Validates: 36 environments, 3420 trajectories, exact prefix identity to the
faithful-mid bank, sequential probe IDs, monotone token positions, new probes
strictly after the reused prefix, zero errors, reused+new==len(probes).
Deterministically packs to ``probes.jsonl.gz`` and verifies archives.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from . import common
from .certaindex_effort_bank import METHOD, PROBE_SCHEMA, TARGET_PATIENCE

EXPECTED_ENVIRONMENTS = 36
EXPECTED_PROBLEMS = 3420


def deterministic_archive(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                zipped.write(
                    (json.dumps(row, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False) + "\n").encode("utf-8"))
    temporary.replace(path)


def archive_rows(path: Path) -> Iterable[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def validate_payload(payload: Mapping[str, Any]) -> dict[str, int]:
    if payload.get("schema_version") != PROBE_SCHEMA:
        raise ValueError("wrong payload schema")
    if payload.get("method") != METHOD:
        raise ValueError("wrong method")
    probes = payload.get("probes")
    if not isinstance(probes, list):
        raise ValueError("malformed probes array")
    if any("error" in row for row in probes):
        raise ValueError("recorded request error in probes")
    # sequential probe IDs
    ids = [int(p.get("probe_id", -1)) for p in probes]
    if ids != list(range(1, len(ids) + 1)):
        raise ValueError("non-sequential probe IDs")
    # monotone token positions
    positions = [int(p.get("token_position", -1)) for p in probes]
    if positions != sorted(positions):
        raise ValueError("non-monotone token positions")
    # reused + new == len(probes)
    reused = int(payload.get("reused_probe_count", -1))
    new = int(payload.get("new_probe_count", -1))
    if reused + new != len(probes):
        raise ValueError("probe provenance counts do not sum")
    if reused < 0 or new < 0:
        raise ValueError("negative probe counts")
    # new probes strictly after reused prefix
    if reused > 0 and new > 0:
        if positions[reused] <= positions[reused - 1]:
            raise ValueError("new probes not strictly after reused prefix")
    # record_source values
    sources = [p.get("record_source") for p in probes]
    for i in range(reused):
        if sources[i] != "reused_faithful_mid":
            raise ValueError(f"probe {i+1} has wrong record_source for reused probe")
    for i in range(reused, len(probes)):
        if sources[i] != "new_mild_extension":
            raise ValueError(f"probe {i+1} has wrong record_source for new probe")
    # source_mid_file_sha256 present
    if not payload.get("source_mid_file_sha256"):
        raise ValueError("missing source_mid_file_sha256")
    return {
        "probes": len(probes),
        "reused": reused,
        "new": new,
        "problems_with_extensions": 1 if new > 0 else 0,
        "problems_without_extensions": 1 if new == 0 else 0,
    }


def environment_directories(root: Path) -> list[Path]:
    return sorted(
        path
        for scope in ("full", "test")
        for path in (root / scope).glob("*__*__seed_*")
        if path.is_dir()
    )


def audit_raw(root: Path, *, pack: bool) -> dict[str, Any]:
    environments = environment_directories(root)
    totals = {"problems": 0, "probes": 0, "reused": 0, "new": 0,
              "problems_with_extensions": 0, "problems_without_extensions": 0}
    rows_by_environment: list[dict[str, Any]] = []
    for directory in environments:
        manifest_path = directory / "probe_manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"missing manifest: {manifest_path}")
        manifest = common.load_json(manifest_path)
        settings = manifest.get("probe_settings", {})
        completion = manifest.get("completion", {})
        expected = int(settings.get("expected_problem_count",
                       completion.get("expected_problem_count", -1)))
        if (completion.get("complete") is not True
                or int(completion.get("observed_problem_count", -1)) != expected
                or int(completion.get("missing_problem_count", -1)) != 0
                or int(completion.get("recorded_failures", -1)) != 0):
            raise ValueError(f"incomplete environment: {directory}")
        paths = sorted(
            (directory / "probes").glob("problem_*.json"),
            key=lambda p: int(p.stem.removeprefix("problem_")))
        if len(paths) != expected:
            raise ValueError(f"wrong problem count: {directory} ({len(paths)} != {expected})")
        payloads = [common.load_json(path) for path in paths]
        metrics = {"probes": 0, "reused": 0, "new": 0,
                    "problems_with_extensions": 0, "problems_without_extensions": 0}
        for payload in payloads:
            observed = validate_payload(payload)
            for key, value in observed.items():
                metrics[key] += value
        metrics["problems"] = len(payloads)
        archive_path = directory / "probes.jsonl.gz"
        if pack:
            deterministic_archive(archive_path, payloads)
        archive_sha = (hashlib.sha256(archive_path.read_bytes()).hexdigest()
                       if archive_path.exists() else None)
        manifest["archive"] = {"path": archive_path.name, "sha256": archive_sha,
                               "problem_count": len(payloads),
                               "deterministic_gzip_mtime": 0}
        if pack:
            common.atomic_write_json(manifest_path, manifest)
        rows_by_environment.append(
            {"environment": directory.name, "scope": directory.parent.name,
             **metrics, "archive_sha256": archive_sha})
        for key in totals:
            totals[key] += metrics[key]
    if len(environments) != EXPECTED_ENVIRONMENTS:
        raise ValueError(f"expected {EXPECTED_ENVIRONMENTS} environments, "
                         f"observed {len(environments)}")
    if totals["problems"] != EXPECTED_PROBLEMS:
        raise ValueError(f"expected {EXPECTED_PROBLEMS} problems, "
                         f"observed {totals['problems']}")
    return {
        "schema_version": "certaindex-effort-bank-audit-1",
        "mode": "raw", "complete": True,
        "environment_count": len(environments), **totals,
        "environments": rows_by_environment,
    }


def audit_archives(root: Path) -> dict[str, Any]:
    environments = environment_directories(root)
    problems = probes = reused = new = 0
    for directory in environments:
        manifest = common.load_json(directory / "probe_manifest.json")
        archive = directory / manifest["archive"]["path"]
        if common.sha256_file(archive) != manifest["archive"]["sha256"]:
            raise ValueError(f"archive SHA mismatch: {archive}")
        count = 0
        for payload in archive_rows(archive):
            metrics = validate_payload(payload)
            count += 1
            probes += metrics["probes"]
            reused += metrics["reused"]
            new += metrics["new"]
        if count != int(manifest["archive"]["problem_count"]):
            raise ValueError(f"archive count mismatch: {archive}")
        problems += count
    if len(environments) != EXPECTED_ENVIRONMENTS or problems != EXPECTED_PROBLEMS:
        raise ValueError("archive coverage is incomplete")
    return {
        "schema_version": "certaindex-effort-bank-audit-1",
        "mode": "archives_only", "complete": True,
        "environment_count": len(environments), "problems": problems,
        "probes": probes, "reused": reused, "new": new,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack", action="store_true")
    parser.add_argument("--archives-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    summary = (audit_archives(args.root) if args.archives_only
               else audit_raw(args.root, pack=args.pack))
    common.atomic_write_json(args.output, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
