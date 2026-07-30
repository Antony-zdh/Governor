#!/usr/bin/env python3
"""Strict coverage and protocol acceptance for the prompt-timing ablation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .run_certaindex32 import DEFAULT_OUTPUT, GOV_RESULTS, MODEL_INFO, environments


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected object")
    return payload


def audit(certa_root: Path) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    totals = {
        "environments": 0,
        "main_trajectories": 0,
        "simple_trajectories": 0,
        "certaindex_trajectories": 0,
        "certaindex_probes": 0,
        "request_or_record_errors": 0,
        "cap_violations": 0,
    }
    seen: set[tuple[Any, ...]] = set()
    for model_key in sorted(MODEL_INFO):
        for env in environments(model_key):
            totals["environments"] += 1
            env_name = env["env_name"]
            main_dir = GOV_RESULTS / env_name / "main" / "traj"
            simple_dir = GOV_RESULTS / env_name / "dense_simple32" / "probes"
            certa_dir = certa_root / env_name / "probes"
            manifest_path = certa_root / env_name / "probe_manifest.json"
            main_paths = sorted(main_dir.glob("problem_*.json"))
            simple_paths = sorted(simple_dir.glob("problem_*.json"))
            certa_paths = sorted(certa_dir.glob("problem_*.json"))
            counts = (len(main_paths), len(simple_paths), len(certa_paths))
            totals["main_trajectories"] += counts[0]
            totals["simple_trajectories"] += counts[1]
            totals["certaindex_trajectories"] += counts[2]
            if counts[0] <= 0 or len(set(counts)) != 1:
                failures.append(
                    {"env": env_name, "reason": "coverage_mismatch", "counts": counts}
                )
                continue
            if not manifest_path.exists():
                failures.append({"env": env_name, "reason": "manifest_missing"})
                continue
            manifest = load(manifest_path)
            settings = manifest.get("probe_settings", {})
            completion = manifest.get("completion", {})
            expected_settings = {
                "probe_tokens": 32,
                "probe_interval": 64,
                "start_token": 64,
                "patience": 3,
                "expected_problem_count": counts[0],
            }
            for field, expected in expected_settings.items():
                if settings.get(field) != expected:
                    failures.append(
                        {
                            "env": env_name,
                            "reason": "setting_mismatch",
                            "field": field,
                            "observed": settings.get(field),
                            "expected": expected,
                        }
                    )
            if not completion.get("complete", False):
                failures.append(
                    {
                        "env": env_name,
                        "reason": "manifest_incomplete",
                        "completion": completion,
                    }
                )
            for path in certa_paths:
                payload = load(path)
                key = (
                    payload.get("model"),
                    payload.get("dataset"),
                    payload.get("base_seed"),
                    payload.get("problem_id"),
                )
                if key in seen:
                    failures.append(
                        {"env": env_name, "reason": "duplicate_identity", "key": key}
                    )
                seen.add(key)
                for probe in payload.get("probes", []):
                    totals["certaindex_probes"] += 1
                    totals["request_or_record_errors"] += int("error" in probe)
                    totals["cap_violations"] += int(
                        int(probe.get("probe_out_tokens", 0)) > 32
                    )
    expected = {
        "environments": 36,
        "main_trajectories": 3420,
        "simple_trajectories": 3420,
        "certaindex_trajectories": 3420,
    }
    for field, value in expected.items():
        if totals[field] != value:
            failures.append(
                {
                    "reason": "total_mismatch",
                    "field": field,
                    "observed": totals[field],
                    "expected": value,
                }
            )
    if totals["request_or_record_errors"]:
        failures.append(
            {
                "reason": "request_or_record_errors",
                "count": totals["request_or_record_errors"],
            }
        )
    if totals["cap_violations"]:
        failures.append(
            {"reason": "cap_violations", "count": totals["cap_violations"]}
        )
    return {
        "schema_version": "probe-prompt-timing-acceptance-1",
        "accept": not failures,
        "totals": totals,
        "expected": expected,
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certa-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit(args.certa_root)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["accept"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
