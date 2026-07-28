#!/usr/bin/env python3
"""Lightweight full-bank progress/ETA reporter.

Counts only identity-valid, schema-valid, error-free per-problem records against
the expected 400/32/24. Malformed/error/wrong-identity files are reported as
invalid (NOT counted as valid). Parses the method-specific manifest and requires
the same completion invariants (complete=true, observed=expected, missing=0,
failures=0). Adds a rough wall-clock ETA based on the observed valid-file rate
since the earliest output timestamp. Does NOT scan or mutate GPUs.

Usage: python progress.py [--results-root <full-results-root>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path("/localdata/dzhaoah/Governor")
DEFAULT_ROOT = REPO / "benchmark/FalseConsensus/results/related_work/full"

sys.path.insert(0, str(REPO))
from benchmark.FalseConsensus.related_work import model_map, manifest_check  # noqa

RECORD_KEYS = {"certaindex_mid": "probes", "tje": "triggers", "deer": "trials"}
MANIFEST_NAMES = {
    "certaindex_mid": "probe_manifest.json",
    "tje": "trigger_manifest.json",
    "deer": "trial_manifest.json",
}
SCHEMA_VERSIONS = {
    "certaindex_mid": "related-work-certaindex-probe-1",
    "tje": "related-work-tje-trigger-1",
    "deer": "related-work-deer-trial-1",
}


def _validate_problem_file(path: Path, method: str, model_id: str,
                           bench: str, seed: int) -> bool:
    """True iff the file is identity-valid, schema-valid, error-free, and has no
    corrupt readout. A present readout with finish_reason stop/length, no error,
    no context overflow/budget -- is a COMPLETE method outcome even when
    readout_valid is False (capped/natural invalid). Only null finish_reason,
    request errors, context overflow/budget, corrupt identity, and malformed
    rows make the file invalid. A missing readout is valid (no-stop/no-exit)."""
    # verify problem_id matches the filename
    fname = path.stem  # e.g. "problem_430"
    try:
        fname_pid = int(fname.split("_")[1])
    except (IndexError, ValueError):
        return False
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    # problem_id matches filename
    if d.get("problem_id") != fname_pid:
        return False
    # schema
    if d.get("schema_version") != SCHEMA_VERSIONS[method]:
        return False
    # identity
    if d.get("model") != model_id:
        return False
    if d.get("dataset") != bench:
        return False
    if d.get("base_seed") != seed:
        return False
    # error-free records: reject non-dict rows and any row with "error" key
    sub = RECORD_KEYS[method]
    rows = d.get(sub) or []
    if not isinstance(rows, list):
        return False
    for r in rows:
        if not isinstance(r, dict):
            return False
        if "error" in r:
            return False
    # readout: reject present non-dict; a fully recorded readout with
    # finish_reason stop/length, no error, no overflow/budget is a complete
    # method outcome even if readout_valid is False. Missing readout is valid.
    ro = d.get("readout")
    if ro is not None:
        if not isinstance(ro, dict):
            return False  # present non-dict = malformed
        if "error" in ro:
            return False
        if ro.get("readout_context_overflow"):
            return False
        if ro.get("readout_context_budget_exceeded"):
            return False
        fr = ro.get("readout_finish_reason")
        if fr not in ("stop", "length"):
            return False  # finish must be exactly stop or length
    return True


def _earliest_mtime(files: list) -> float:
    """Earliest mtime among valid files (or 0 if none)."""
    mtimes = [f.stat().st_mtime for f in files if f.exists()]
    return min(mtimes) if mtimes else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", type=Path, default=DEFAULT_ROOT)
    args = ap.parse_args()
    root = args.results_root
    now = time.time()

    total_expected = 0
    total_valid = 0
    total_invalid = 0
    all_valid_files: list = []

    print(f"# full-bank progress  root={root}  scanned={time.strftime('%Y-%m-%dT%H:%M:%S')}")
    for key in ("deepseek", "qwen3"):
        info = model_map.model_info(key)
        mid = info["model_id"]
        m_valid = m_total = m_invalid = 0
        print(f"\n## {key}  (model={mid}  rev={info['revision'][:12]}  endpoint={info['endpoint']})")
        for method in model_map.METHODS:
            for bench, seed, _env in model_map.authorized_envs(key):
                exp = model_map.EXPECTED_PROBLEM_COUNTS[bench]
                total_expected += exp
                out_dir = root / f"{key}__{bench}__seed_{seed}" / method
                sub = RECORD_KEYS[method]
                pdir = out_dir / sub
                all_files = sorted(pdir.glob("problem_*.json")) if pdir.is_dir() else []
                valid_files = []
                invalid = 0
                for f in all_files:
                    if _validate_problem_file(f, method, mid, bench, seed):
                        valid_files.append(f)
                    else:
                        invalid += 1
                # manifest verification
                manifest = out_dir / MANIFEST_NAMES[method]
                manifest_ok, manifest_reason = (manifest_check.check_manifest(manifest, exp)
                                                if manifest.exists() else (False, "manifest missing"))
                valid_count = len(valid_files)
                total_valid += valid_count
                total_invalid += invalid
                m_valid += valid_count
                m_total += exp
                m_invalid += invalid
                all_valid_files.extend(valid_files)
                status = "OK" if (valid_count == exp and invalid == 0 and manifest_ok) else "INCOMPLETE"
                print(f"  {method:16s} {bench:8s} seed_{seed}  valid={valid_count:4d}/{exp:<4d}  invalid={invalid}  manifest={'OK' if manifest_ok else manifest_reason}  [{status}]")
        print(f"  -- {key} subtotal: valid={m_valid}/{m_total}  invalid={m_invalid}")

    # ETA from observed valid-file rate
    earliest = _earliest_mtime(all_valid_files)
    elapsed = max(0.0, now - earliest) if earliest > 0 else 0.0
    rate = (total_valid / elapsed) if (elapsed > 60 and total_valid >= 5) else 0.0
    remaining = max(0, total_expected - total_valid)
    eta_seconds = int(remaining / rate) if rate > 0 else None
    eta_label = (f"{eta_seconds // 3600}h{(eta_seconds % 3600) // 60}m"
                if eta_seconds is not None else "unknown (insufficient progress)")
    print(f"\n## GRAND: valid={total_valid}/{total_expected}  invalid={total_invalid}  "
          f"rate={'%.2f files/s' % rate if rate else 'unknown'}  "
          f"ETA~{eta_label}  (approximate; heterogeneous methods)")
    print(f"# elapsed={int(elapsed)}s  earliest_output={time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(earliest)) if earliest else 'n/a'}")

    # machine-readable snapshot
    snap = root / "_runtime" / "progress_snapshot.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "completed_valid": total_valid,
        "total_expected": total_expected,
        "invalid": total_invalid,
        "rate_files_per_s": round(rate, 4) if rate else 0,
        "eta_seconds": eta_seconds,
        "elapsed_seconds": int(elapsed),
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    tmp = snap.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, snap)
    print(f"# snapshot: {snap}")
    return 0 if (total_valid == total_expected and total_invalid == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
