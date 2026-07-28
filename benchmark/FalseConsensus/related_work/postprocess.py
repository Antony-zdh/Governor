#!/usr/bin/env python3
"""Restartable CPU-only postprocess orchestrator.

Only after ALL 54 collector manifests pass the strict completion checker
(manifest_check: complete=true, observed=expected, missing=0, failures=0,
invalid_readouts=0), runs replay for every method × model × benchmark × seed,
validates exactly 8,208 replay rows (2,736 per method), runs the preregistered
10,000-sample paired hierarchical bootstrap (on dev-pooled + train+dev only --
NOT per-environment, to avoid redundant work), and writes aggregate artifacts.

Does NOT touch, restart, interrupt, or write into any active collector output
file. Does NOT read test/confirmation data. Does NOT modify frozen trajectories,
collector semantics, GPU processes, or active full output files.

Usage:
    python -m benchmark.FalseConsensus.related_work.postprocess [--dry-run]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

from . import common, manifest_check, model_map
from . import aggregate_all, metrics

REPO = Path("/localdata/dzhaoah/Governor")
PY = "/localdata/dzhaoah/miniforge3/envs/gov/bin/python"
FULL_ROOT = REPO / "benchmark/FalseConsensus/results/related_work/full"
REPLAY_ROOT = FULL_ROOT / "_replay"
AGGREGATE_DIR = REPO / "benchmark/FalseConsensus/results/related_work/aggregate"
SPLIT_MANIFEST = REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"

MANIFEST_NAMES = {
    "certaindex_mid": "probe_manifest.json",
    "tje": "trigger_manifest.json",
    "deer": "trial_manifest.json",
}
METHOD_MODULE = {
    "certaindex_mid": "certaindex_mid",
    "tje": "tje",
    "deer": "deer",
}
COLLECTED_SUBDIR = {
    "certaindex_mid": "probes",
    "tje": "triggers",
    "deer": "trials",
}


def all_envs() -> List[Tuple[str, str, int, str]]:
    """All 54 (method, model_key, bench, seed) tuples."""
    out = []
    for method in model_map.METHODS:
        for key in ("deepseek", "qwen3"):
            for bench, seed, env_name in model_map.authorized_envs(key):
                out.append((method, key, bench, seed, env_name))
    return out


def manifest_path(full_root: Path, method: str, key: str, bench: str, seed: int) -> Path:
    return full_root / f"{key}__{bench}__seed_{seed}" / method / MANIFEST_NAMES[method]


def collected_path(full_root: Path, method: str, key: str, bench: str, seed: int) -> Path:
    return full_root / f"{key}__{bench}__seed_{seed}" / method


def main_run_path(env_name: str) -> Path:
    return REPO / "benchmark/FalseConsensus/results/governor_v2" / env_name / "main"


def check_all_manifests(full_root: Path) -> Tuple[bool, list]:
    """Check all 54 collector manifests. Returns (all_ok, failures)."""
    failures = []
    for method, key, bench, seed, _env in all_envs():
        mp = manifest_path(full_root, method, key, bench, seed)
        exp = model_map.EXPECTED_PROBLEM_COUNTS[bench]
        ok, reason = manifest_check.check_manifest(mp, exp) if mp.exists() else (False, "manifest missing")
        if not ok:
            failures.append({"method": method, "model": key, "bench": bench, "seed": seed, "reason": reason})
    return len(failures) == 0, failures


def replay_command(method: str, key: str, bench: str, seed: int, env_name: str,
                   full_root: Path, replay_root: Path) -> List[str]:
    main_run = main_run_path(env_name)
    collected = collected_path(full_root, method, key, bench, seed)
    out_dir = replay_root / f"{key}__{bench}__seed_{seed}__{method}"
    return [
        PY, "-m", "benchmark.FalseConsensus.related_work.replay",
        "--method", method,
        "--main-run", str(main_run),
        "--collected", str(collected),
        "--split-manifest", str(SPLIT_MANIFEST),
        "--output", str(out_dir),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Restartable CPU-only postprocess orchestrator")
    ap.add_argument("--full-root", type=Path, default=FULL_ROOT)
    ap.add_argument("--replay-root", type=Path, default=REPLAY_ROOT)
    ap.add_argument("--aggregate-dir", type=Path, default=AGGREGATE_DIR)
    ap.add_argument("--split-manifest", type=Path, default=SPLIT_MANIFEST)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--jobs", type=int, default=8,
        help="number of independent replay subprocesses (default 8; each writes a distinct environment)",
    )
    ap.add_argument("--allow-partial", action="store_true",
                   help="proceed even if some manifests are incomplete (incremental)")
    args = ap.parse_args(argv)
    if args.jobs < 1:
        ap.error("--jobs must be >= 1")

    full_root = args.full_root
    replay_root = args.replay_root
    aggregate_dir = args.aggregate_dir

    # Step 1: check all 54 manifests
    all_ok, failures = check_all_manifests(full_root)
    if not all_ok:
        print(f"Manifest check: {len(failures)} failures (of 54)", file=sys.stderr)
        for f in failures[:10]:
            print(f"  {f['method']}/{f['model']}/{f['bench']}/seed{f['seed']}: {f['reason']}", file=sys.stderr)
        if not args.dry_run and not args.allow_partial:
            print("Aborting (use --allow-partial for incremental).", file=sys.stderr)
            return 1

    if args.dry_run:
        print("=== DRY RUN: postprocess ===")
        print(f"full_root={full_root}")
        print(f"replay_root={replay_root}")
        print(f"aggregate_dir={aggregate_dir}")
        print(f"manifests_ok={all_ok}  failures={len(failures)}")
        print(f"replay_commands={len(all_envs())}")
        print(f"expected_rows=8208 (2736 per method × 3 methods)")
        print(f"bootstrap={metrics.BOOTSTRAP_SAMPLES} samples, seed={metrics.BOOTSTRAP_SEED}")
        print(f"bootstrap_scope=dev_pooled + train_dev_diagnostic only (NOT per-environment)")
        print(f"replay_jobs={args.jobs}")
        print("=== plan ===")
        for method, key, bench, seed, env_name in all_envs():
            cmd = replay_command(method, key, bench, seed, env_name, full_root, replay_root)
            print(f"[replay] {method}/{key}/{bench}/seed{seed}")
            print(f"  {' '.join(cmd)}")
        print(f"[aggregate] {PY} -m ...aggregate_all --inputs <54 replay_rows.jsonl> --output-dir {aggregate_dir}")
        print(f"[report] {PY} -m ...report_gen --aggregate {aggregate_dir}/aggregate.json --output {aggregate_dir}/report.md")
        print("=== DRY RUN complete: no outputs written ===")
        return 0

    # Step 2: run replay for each env (restartable: skip if replay_rows.jsonl exists)
    replay_root.mkdir(parents=True, exist_ok=True)
    replay_paths = []
    t0 = time.time()
    pending = []
    for i, (method, key, bench, seed, env_name) in enumerate(all_envs(), 1):
        out_dir = replay_root / f"{key}__{bench}__seed_{seed}__{method}"
        rows_file = out_dir / "replay_rows.jsonl"
        if rows_file.exists():
            replay_paths.append(rows_file)
            print(f"[{i}/54] replay {method}/{key}/{bench}/seed{seed} (cached)", flush=True)
            continue
        cmd = replay_command(method, key, bench, seed, env_name, full_root, replay_root)
        pending.append((i, method, key, bench, seed, cmd, rows_file))

    def run_replay(item):
        i, method, key, bench, seed, cmd, rows_file = item
        r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                           timeout=3600,
                           env={**os.environ,
                                "LD_PRELOAD": "/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6",
                                "LD_LIBRARY_PATH": "/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64",
                                "HF_HOME": "/localdata/dzhaoah/hf-cache"})
        return i, method, key, bench, seed, rows_file, r

    failures_replay = []
    if pending:
        print(
            f"launching {len(pending)} uncached replays with jobs={args.jobs}",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(pending))) as pool:
            futures = {pool.submit(run_replay, item): item for item in pending}
            for future in as_completed(futures):
                i, method, key, bench, seed, rows_file, r = future.result()
                if r.returncode != 0 or not rows_file.exists():
                    reason = r.stderr[-500:] if r.returncode else "replay_rows.jsonl missing"
                    failures_replay.append({
                        "index": i, "method": method, "model": key,
                        "bench": bench, "seed": seed, "reason": reason,
                    })
                    print(
                        f"FAIL [{i}/54] replay {method}/{key}/{bench}/seed{seed}: "
                        f"{reason[-200:]}",
                        file=sys.stderr,
                        flush=True,
                    )
                else:
                    replay_paths.append(rows_file)
                    print(
                        f"OK [{i}/54] replay {method}/{key}/{bench}/seed{seed}",
                        flush=True,
                    )
    if failures_replay and not args.allow_partial:
        print(
            f"Aborting after {len(failures_replay)} replay failure(s).",
            file=sys.stderr,
        )
        return 1

    print(f"replay done: {len(replay_paths)}/54 in {time.time()-t0:.0f}s", flush=True)

    # Step 3: validate + aggregate
    if not replay_paths:
        print("No replay rows to aggregate.", file=sys.stderr)
        return 1

    rows = aggregate_all.load_rows(replay_paths)
    coverage = aggregate_all.validate_coverage(
        rows, require_all_methods=not args.allow_partial,
        split_manifest=args.split_manifest)
    print(f"coverage: {coverage}", flush=True)

    views = aggregate_all.build_views(rows)
    views["coverage"] = coverage
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(aggregate_dir / "aggregate.json", views)
    for name in ("environment_split", "dev_pooled", "train_dev_diagnostic", "dev_macro"):
        aggregate_all.write_csv(aggregate_dir / f"{name}.csv", views[name])
    print(f"aggregate written to {aggregate_dir}", flush=True)

    # Step 4: generate Chinese report
    report_cmd = [
        PY, "-m", "benchmark.FalseConsensus.related_work.report_gen",
        "--aggregate", str(aggregate_dir / "aggregate.json"),
        "--output", str(aggregate_dir / "report.md"),
    ]
    r = subprocess.run(report_cmd, cwd=str(REPO), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"report_gen failed: {r.stderr[-200:]}", file=sys.stderr)
    else:
        print(f"report written to {aggregate_dir}/report.md", flush=True)

    print(json.dumps({
        "rows": len(rows),
        "expected_rows": common.EXPECTED_TOTAL_TRAJECTORIES * 3,
        "bootstrap_samples": metrics.BOOTSTRAP_SAMPLES,
        "bootstrap_seed": metrics.BOOTSTRAP_SEED,
        "elapsed_seconds": round(time.time() - t0, 1),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
