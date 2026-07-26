#!/usr/bin/env python3
"""Run a portable experiment matrix sequentially with optional filters."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--benchmark", default=None)
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument(
        "--url",
        default=None,
        help="override the matrix API URL for a particular vLLM replica",
    )
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument(
        "--stage",
        action="append",
        choices=(
            "main_generation",
            "dense_probe",
            "dense_probe_32_offset",
            "adaptive_probe",
        ),
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
        and (not args.seed or int(job["seed"]) in set(args.seed))
        and (not args.stage or job["stage"] in set(args.stage))
    )


def environment_key(job: dict[str, Any]) -> tuple[Any, ...]:
    return (
        job["phase"],
        job["model"],
        job["benchmark"],
        int(job["seed"]),
    )


def override_url(command: list[str], url: str | None) -> list[str]:
    command = list(command)
    if url is None:
        return command
    try:
        index = command.index("--url")
    except ValueError as error:
        raise ValueError("selected matrix command has no --url") from error
    command[index + 1] = url
    return command


def main() -> None:
    args = parse_args()
    if args.shard_count < 1:
        raise ValueError("--shard-count must be positive")
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("--shard-index must lie in [0, shard-count)")
    jobs = [
        json.loads(line)
        for line in args.matrix.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    jobs = [job for job in jobs if selected(job, args)]
    environments = sorted({environment_key(job) for job in jobs})
    assigned = {
        key
        for index, key in enumerate(environments)
        if index % args.shard_count == args.shard_index
    }
    jobs = [job for job in jobs if environment_key(job) in assigned]
    if not jobs:
        raise ValueError("filters selected no jobs")
    completed = set()
    for index, job in enumerate(jobs, start=1):
        dependency = job.get("depends_on")
        if dependency and dependency not in completed:
            # The dependency may have been completed in an earlier invocation.
            output = Path(job["output"])
            if job["stage"] == "adaptive_probe":
                prerequisite = (
                    output.parent
                    / "dense_simple32"
                    / "probe_manifest.json"
                )
            else:
                prerequisite = (
                    output.parent / "main" / "run_manifest.json"
                )
            if not prerequisite.exists():
                raise RuntimeError(
                    f"{job['job_id']} dependency is neither selected nor present: "
                    f"{dependency}"
                )
        print(
            f"[{index}/{len(jobs)}] {job['job_id']}\n"
            f"{shlex.join(override_url(job['command'], args.url))}",
            flush=True,
        )
        if args.execute:
            subprocess.run(
                override_url(job["command"], args.url),
                check=True,
            )
        completed.add(job["job_id"])


if __name__ == "__main__":
    main()
