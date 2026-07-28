"""Manifest completion verification (shared by the launcher and progress reporter).

A collector can exit 0 while its finalized manifest reports incomplete coverage or
recorded failures. This module enforces the completion invariants:

* a ``completion`` block exists;
* ``complete`` is true;
* ``expected_problem_count`` and ``observed_problem_count`` equal the benchmark's
  expected count (400/32/24);
* ``missing_problem_count`` is 0;
* ``recorded_failures`` is 0.

CLI: ``python -m ...manifest_check <manifest_path> <expected_count>``
exits 0 (valid) or 1 (invalid, with a reason on stderr).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Tuple

EXPECTED = {"math500": 400, "amc23": 32, "aime24": 24}


def check_manifest(path: Path, expected_count: int) -> Tuple[bool, str]:
    """Verify a collector manifest's completion block. Returns (ok, reason)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"unreadable/invalid JSON: {exc}"
    comp = d.get("completion")
    if not isinstance(comp, dict):
        return False, "no completion block"
    if not comp.get("complete"):
        return False, f"complete={comp.get('complete')}"
    if int(comp.get("expected_problem_count", -1)) != expected_count:
        return False, f"expected={comp.get('expected_problem_count')} != {expected_count}"
    if int(comp.get("observed_problem_count", -1)) != expected_count:
        return False, f"observed={comp.get('observed_problem_count')} != {expected_count}"
    if int(comp.get("missing_problem_count", -1)) != 0:
        return False, f"missing={comp.get('missing_problem_count')}"
    if int(comp.get("recorded_failures", -1)) != 0:
        return False, f"recorded_failures={comp.get('recorded_failures')}"
    # Both invalid_readouts and truncated_readouts are DIAGNOSTIC method-level
    # outcomes (not infrastructure failures): a capped readout at the
    # preregistered readout_cap=8192 with no completed boxed is a complete
    # per-problem record (the row is delivered as invalid/empty/incorrect in
    # replay). Only actual request errors (recorded_failures), corrupt/missing
    # rows (coverage), and context overflow/budget errors are hard failures.
    return True, "ok"


def manifest_path_for(out_dir: Path, method: str) -> Path:
    return Path(out_dir) / {
        "certaindex_mid": "probe_manifest.json",
        "tje": "trigger_manifest.json",
        "deer": "trial_manifest.json",
    }[method]


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        print("usage: manifest_check <manifest_path> <expected_count>", file=sys.stderr)
        return 2
    path, exp = Path(argv[0]), int(argv[1])
    ok, reason = check_manifest(path, exp)
    if ok:
        print(f"manifest OK: {path}")
        return 0
    print(f"manifest INVALID: {path}: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
