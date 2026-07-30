#!/usr/bin/env python3
"""Restartable launcher for the matched CertaIndex@32 probe arm.

This script does not start or stop model servers.  It talks only to the
configured endpoints and writes to the prompt-ablation namespace.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[3]
GOV_RESULTS = REPO / "benchmark/FalseConsensus/results/governor_v2"
DEFAULT_OUTPUT = (
    REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/certaindex32"
)
SPLIT_MANIFEST = (
    REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
)
PROTOCOL = Path(__file__).with_name("protocol.json")

MODEL_INFO = {
    "deepseek": {
        "id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "slug": "deepseek-ai-deepseek-r1-distill-qwen-7b",
        "revision": "916b56a44061fd5cd7d6a8fb632557ed4f724f60",
        "url": "http://127.0.0.1:18000/v1",
    },
    "qwen3": {
        "id": "Qwen/Qwen3-8B",
        "slug": "qwen-qwen3-8b",
        "revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "url": "http://127.0.0.1:18001/v1",
    },
}
BENCHMARKS = ("math500", "amc23", "aime24")
PHASES = (("development", (42, 43, 44)), ("confirmation", (45, 46, 47)))


def environments(model_key: str) -> list[dict[str, Any]]:
    info = MODEL_INFO[model_key]
    rows: list[dict[str, Any]] = []
    for phase, seeds in PHASES:
        for benchmark in BENCHMARKS:
            for seed in seeds:
                env_name = (
                    f"{phase}__{info['slug']}__{benchmark}__seed_{seed}"
                )
                rows.append(
                    {
                        "phase": phase,
                        "benchmark": benchmark,
                        "seed": seed,
                        "env_name": env_name,
                        "main_run": GOV_RESULTS / env_name / "main",
                    }
                )
    return rows


def expected_count(main_run: Path) -> int:
    return len(list((main_run / "traj").glob("problem_*.json")))


def validate_existing_inputs(model_key: str) -> list[dict[str, Any]]:
    failures = []
    for env in environments(model_key):
        main_run = env["main_run"]
        simple = main_run.parent / "dense_simple32" / "probes"
        main_count = expected_count(main_run)
        simple_count = len(list(simple.glob("problem_*.json")))
        if main_count <= 0 or simple_count != main_count:
            failures.append(
                {
                    "env": env["env_name"],
                    "main": main_count,
                    "simple": simple_count,
                }
            )
    return failures


def collector_command(
    model_key: str,
    env: dict[str, Any],
    output_root: Path,
    workers: int,
) -> list[str]:
    info = MODEL_INFO[model_key]
    return [
        sys.executable,
        "-m",
        "benchmark.FalseConsensus.related_work.certaindex_mid",
        "--main-run",
        str(env["main_run"]),
        "--output",
        str(output_root / env["env_name"]),
        "--url",
        str(info["url"]),
        "--model",
        str(info["id"]),
        "--model-revision",
        str(info["revision"]),
        "--split-manifest",
        str(SPLIT_MANIFEST),
        "--interval",
        "64",
        "--start-token",
        "64",
        "--probe-tokens",
        "32",
        "--patience",
        "3",
        "--workers",
        str(workers),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(MODEL_INFO), required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-inputs", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    failures = validate_existing_inputs(args.model)
    if failures:
        print(json.dumps({"input_failures": failures}, indent=2))
        return 1
    envs = environments(args.model)
    commands = [
        collector_command(args.model, env, args.output_root, args.workers)
        for env in envs
    ]
    if args.check_inputs:
        print(
            json.dumps(
                {
                    "model": args.model,
                    "environments": len(envs),
                    "main_and_simple_inputs": "complete",
                    "trajectories": sum(expected_count(env["main_run"]) for env in envs),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.dry_run:
        print(f"protocol={PROTOCOL}")
        for command in commands:
            print(" ".join(command))
        return 0
    for index, command in enumerate(commands, start=1):
        print(f"[{index}/{len(commands)}] {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=REPO, check=True)
    print(f"completed model={args.model} output={args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
