"""Audit and deterministically pack the TJE top-1..top-6 readout bank."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from . import common
from .tje_threshold_readout_bank import (
    METHOD,
    PROBE_SCHEMA,
    TOP_K_THRESHOLDS,
)


EXPECTED_ENVIRONMENTS = 36
EXPECTED_PROBLEMS = 3420


def deterministic_archive(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            mtime=0,
        ) as zipped:
            for row in rows:
                zipped.write(
                    (
                        json.dumps(
                            row,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                )
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
    if int(payload.get("confidence_queries_generated", -1)) != 0:
        raise ValueError("confidence queries were unexpectedly regenerated")
    triggers = payload.get("confidence_triggers")
    readouts = payload.get("readouts")
    decisions = payload.get("top_k_decisions")
    if not isinstance(triggers, list) or not isinstance(readouts, list):
        raise ValueError("malformed trigger/readout arrays")
    if not isinstance(decisions, Mapping):
        raise ValueError("malformed threshold decisions")
    if any("error" in row for row in triggers + readouts):
        raise ValueError("recorded request error")
    readout_ids = {
        int(row.get("at_trigger_id", -1)) for row in readouts
    }
    decision_ids: list[int] = []
    prior = None
    for top_k in range(1, 7):
        row = decisions.get(str(top_k))
        if not isinstance(row, Mapping):
            raise ValueError(f"missing top-{top_k} decision")
        if row.get("threshold_label") != TOP_K_THRESHOLDS[top_k]:
            raise ValueError(f"wrong top-{top_k} threshold label")
        trigger_id = row.get("stop_trigger_id")
        if trigger_id is None:
            continue
        trigger_id = int(trigger_id)
        decision_ids.append(trigger_id)
        # A more permissive top-k threshold cannot stop later.
        if prior is not None and trigger_id > prior:
            raise ValueError("non-monotone TJE threshold decisions")
        prior = trigger_id
    if readout_ids != set(decision_ids):
        raise ValueError("readouts do not cover every unique decision")
    if int(payload.get("expected_unique_readout_count", -1)) != len(
        readout_ids
    ):
        raise ValueError("wrong expected readout count")
    reused = int(payload.get("reused_readout_count", -1))
    generated = int(payload.get("generated_readout_count", -1))
    if reused + generated != len(readouts):
        raise ValueError("readout provenance counts do not sum")
    return {
        "triggers": len(triggers),
        "readouts": len(readouts),
        "reused": reused,
        "generated": generated,
        "invalid": sum(
            not bool(row.get("readout_valid")) for row in readouts
        ),
        "context_budget_exceeded": sum(
            bool(row.get("readout_context_budget_exceeded"))
            for row in readouts
        ),
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
    totals = {
        "problems": 0,
        "triggers": 0,
        "readouts": 0,
        "reused": 0,
        "generated": 0,
        "invalid": 0,
        "context_budget_exceeded": 0,
    }
    rows_by_environment: list[dict[str, Any]] = []
    for directory in environments:
        manifest_path = directory / "bank_manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"missing manifest: {manifest_path}")
        manifest = common.load_json(manifest_path)
        settings = manifest.get("bank_settings", {})
        completion = manifest.get("completion", {})
        expected = int(settings.get("expected_problem_count", -1))
        if (
            completion.get("complete") is not True
            or int(completion.get("observed_problem_count", -1))
            != expected
            or int(completion.get("missing_problem_count", -1)) != 0
            or int(completion.get("recorded_failures", -1)) != 0
        ):
            raise ValueError(f"incomplete environment: {directory}")
        paths = sorted(
            (directory / "readouts").glob("problem_*.json"),
            key=lambda path: int(
                path.stem.removeprefix("problem_")
            ),
        )
        if len(paths) != expected:
            raise ValueError(f"wrong problem count: {directory}")
        payloads = [common.load_json(path) for path in paths]
        metrics = {
            "problems": len(payloads),
            "triggers": 0,
            "readouts": 0,
            "reused": 0,
            "generated": 0,
            "invalid": 0,
            "context_budget_exceeded": 0,
        }
        for payload in payloads:
            observed = validate_payload(payload)
            for key, value in observed.items():
                metrics[key] += value
        archive_path = directory / "readouts.jsonl.gz"
        if pack:
            deterministic_archive(archive_path, payloads)
        archive_sha = (
            hashlib.sha256(archive_path.read_bytes()).hexdigest()
            if archive_path.exists()
            else None
        )
        manifest["archive"] = {
            "path": archive_path.name,
            "sha256": archive_sha,
            "problem_count": len(payloads),
            "deterministic_gzip_mtime": 0,
        }
        if pack:
            common.atomic_write_json(manifest_path, manifest)
        rows_by_environment.append(
            {
                "environment": directory.name,
                "scope": directory.parent.name,
                **metrics,
                "archive_sha256": archive_sha,
            }
        )
        for key in totals:
            totals[key] += metrics[key]
    if len(environments) != EXPECTED_ENVIRONMENTS:
        raise ValueError(
            f"expected {EXPECTED_ENVIRONMENTS} environments, "
            f"observed {len(environments)}"
        )
    if totals["problems"] != EXPECTED_PROBLEMS:
        raise ValueError(
            f"expected {EXPECTED_PROBLEMS} problems, "
            f"observed {totals['problems']}"
        )
    return {
        "schema_version": "tje-threshold-readout-bank-audit-1",
        "mode": "raw",
        "complete": True,
        "environment_count": len(environments),
        **totals,
        "environments": rows_by_environment,
    }


def audit_archives(root: Path) -> dict[str, Any]:
    environments = environment_directories(root)
    problems = readouts = generated = reused = 0
    for directory in environments:
        manifest = common.load_json(directory / "bank_manifest.json")
        archive = directory / manifest["archive"]["path"]
        if common.sha256_file(archive) != manifest["archive"]["sha256"]:
            raise ValueError(f"archive SHA mismatch: {archive}")
        count = 0
        for payload in archive_rows(archive):
            metrics = validate_payload(payload)
            count += 1
            readouts += metrics["readouts"]
            generated += metrics["generated"]
            reused += metrics["reused"]
        if count != int(manifest["archive"]["problem_count"]):
            raise ValueError(f"archive count mismatch: {archive}")
        problems += count
    if (
        len(environments) != EXPECTED_ENVIRONMENTS
        or problems != EXPECTED_PROBLEMS
    ):
        raise ValueError("archive coverage is incomplete")
    return {
        "schema_version": "tje-threshold-readout-bank-audit-1",
        "mode": "archives_only",
        "complete": True,
        "environment_count": len(environments),
        "problems": problems,
        "readouts": readouts,
        "generated": generated,
        "reused": reused,
    }


def parse_args(
    argv: Optional[Sequence[str]] = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack", action="store_true")
    parser.add_argument("--archives-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    summary = (
        audit_archives(args.root)
        if args.archives_only
        else audit_raw(args.root, pack=args.pack)
    )
    common.atomic_write_json(args.output, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
