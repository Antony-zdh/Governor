#!/usr/bin/env python3
"""Run a portable experiment matrix sequentially with optional filters."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--benchmark", default=None)
    parser.add_argument(
        "--stage",
        action="append",
        choices=("main_generation", "dense_probe", "dense_probe_32_offset"),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="without this flag, print the selected commands only",
    )
    return parser.parse_args()


def selected(job: dict[str, Any], args: argparse.Namespace) -> bool:
    return (
        (args.model is None or job["model"] == args.model)
        and (args.benchmark is None or job["benchmark"] == args.benchmark)
        and (not args.stage or job["stage"] in set(args.stage))
    )


def main() -> None:
    args = parse_args()
    jobs = [
        json.loads(line)
        for line in args.matrix.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    jobs = [job for job in jobs if selected(job, args)]
    if not jobs:
        raise ValueError("filters selected no jobs")
    completed = set()
    for index, job in enumerate(jobs, start=1):
        dependency = job.get("depends_on")
        if dependency and dependency not in completed:
            # The dependency may have been completed in an earlier invocation.
            output = Path(job["output"])
            parent = output.parent / "main" / "run_manifest.json"
            if not parent.exists():
                raise RuntimeError(
                    f"{job['job_id']} dependency is neither selected nor present: "
                    f"{dependency}"
                )
        print(
            f"[{index}/{len(jobs)}] {job['job_id']}\n{job['command_shell']}",
            flush=True,
        )
        if args.execute:
            subprocess.run(job["command"], check=True)
        completed.add(job["job_id"])


if __name__ == "__main__":
    main()
