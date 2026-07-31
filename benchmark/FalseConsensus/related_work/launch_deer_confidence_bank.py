"""Durable sharded launcher for the DEER cap-30 confidence bank.

The launcher never starts or stops model servers.  It sends work only to the
explicit OpenAI-compatible endpoint supplied by the caller, making it safe to
run four independent shards per model on an eight-GPU host.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from . import common, model_map
from .deer_confidence_bank import DEFAULT_MAX_ATTEMPTS


REPO_ROOT = Path(__file__).resolve().parents[3]
SCOPES = {
    "full": {"prefix": "development", "seeds": (42, 43, 44)},
    "test": {"prefix": "confirmation", "seeds": (45, 46, 47)},
}


@dataclass(frozen=True)
class Job:
    scope: str
    model_key: str
    benchmark: str
    seed: int
    main_run: Path
    reuse_dir: Path
    output: Path
    problem_count: int

    @property
    def label(self) -> str:
        return (
            f"{self.scope}__{self.model_key}__{self.benchmark}"
            f"__seed_{self.seed}"
        )


def discover_jobs(
    repo: Path,
    *,
    model_key: str,
    scopes: Sequence[str],
    output_root: Path,
) -> list[Job]:
    info = model_map.model_info(model_key)
    bank_root = repo / "benchmark/FalseConsensus/results/governor_v2"
    related_root = repo / "benchmark/FalseConsensus/results/related_work"
    jobs: list[Job] = []
    for scope in scopes:
        specification = SCOPES[scope]
        for benchmark in model_map.BENCHMARKS:
            for seed in specification["seeds"]:
                environment = (
                    f"{specification['prefix']}__{info['slug']}__"
                    f"{benchmark}__seed_{seed}"
                )
                main_run = bank_root / environment / "main"
                reuse_dir = (
                    related_root
                    / scope
                    / f"{model_key}__{benchmark}__seed_{seed}"
                    / "deer"
                )
                output = (
                    output_root
                    / scope
                    / f"{model_key}__{benchmark}__seed_{seed}"
                )
                if not (main_run / "run_manifest.json").exists():
                    raise FileNotFoundError(main_run / "run_manifest.json")
                if not (reuse_dir / "trial_manifest.json").exists():
                    raise FileNotFoundError(reuse_dir / "trial_manifest.json")
                problem_count = len(common.trajectory_paths(main_run))
                if problem_count <= 0:
                    raise ValueError(f"no trajectories in {main_run}")
                jobs.append(
                    Job(
                        scope=scope,
                        model_key=model_key,
                        benchmark=benchmark,
                        seed=int(seed),
                        main_run=main_run,
                        reuse_dir=reuse_dir,
                        output=output,
                        problem_count=problem_count,
                    )
                )
    return jobs


def balanced_shards(jobs: Sequence[Job], count: int) -> list[list[Job]]:
    if count <= 0:
        raise ValueError("shard count must be positive")
    shards: list[list[Job]] = [[] for _ in range(count)]
    loads = [0 for _ in range(count)]
    for job in sorted(
        jobs,
        key=lambda item: (
            -item.problem_count,
            item.scope,
            item.benchmark,
            item.seed,
        ),
    ):
        index = min(range(count), key=lambda i: (loads[i], i))
        shards[index].append(job)
        loads[index] += job.problem_count
    return shards


def collector_command(
    args: argparse.Namespace, job: Job, split_manifest: Path
) -> list[str]:
    info = model_map.model_info(job.model_key)
    return [
        str(args.python),
        "-m",
        "benchmark.FalseConsensus.related_work.deer_confidence_bank",
        "--main-run",
        str(job.main_run),
        "--output",
        str(job.output),
        "--reuse-dir",
        str(job.reuse_dir),
        "--url",
        args.endpoint,
        "--model",
        str(info["model_id"]),
        "--model-revision",
        str(info["revision"]),
        "--split-manifest",
        str(split_manifest),
        "--workers",
        str(args.workers),
        "--max-attempts",
        str(DEFAULT_MAX_ATTEMPTS),
    ]


def verify_job(job: Job) -> dict:
    path = job.output / "bank_manifest.json"
    if not path.exists():
        raise ValueError(f"missing bank manifest: {path}")
    manifest = common.load_json(path)
    settings = manifest.get("bank_settings", {})
    completion = manifest.get("completion", {})
    expected = job.problem_count
    if int(settings.get("max_attempts", -1)) != DEFAULT_MAX_ATTEMPTS:
        raise ValueError(f"{job.label}: wrong cap")
    if int(settings.get("expected_problem_count", -1)) != expected:
        raise ValueError(f"{job.label}: wrong settings expected count")
    if (
        completion.get("complete") is not True
        or int(completion.get("expected_problem_count", -1)) != expected
        or int(completion.get("observed_problem_count", -1)) != expected
        or int(completion.get("missing_problem_count", -1)) != 0
        or int(completion.get("recorded_failures", -1)) != 0
    ):
        raise ValueError(f"{job.label}: incomplete manifest {completion}")
    return completion


def atomic_status(path: Path, payload: dict) -> None:
    common.atomic_write_json(path, payload)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one deterministic shard of the DEER cap-30 bank"
    )
    parser.add_argument("--model-key", choices=sorted(model_map.MODELS), required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument(
        "--scope", choices=("full", "test", "both"), default="both"
    )
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--num-shards", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    repo = args.repo.resolve()
    if args.shard_index < 0 or args.shard_index >= args.num_shards:
        raise ValueError("--shard-index must be in [0, --num-shards)")
    if args.workers <= 0:
        raise ValueError("--workers must be positive")
    output_root = (
        args.output_root.resolve()
        if args.output_root
        else repo
        / "benchmark/FalseConsensus/results/related_work"
        / "deer_confidence_bank_cap30"
    )
    scopes = ("full", "test") if args.scope == "both" else (args.scope,)
    split_manifest = (
        repo
        / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
    )
    if not split_manifest.exists():
        raise FileNotFoundError(split_manifest)
    jobs = discover_jobs(
        repo,
        model_key=args.model_key,
        scopes=scopes,
        output_root=output_root,
    )
    shards = balanced_shards(jobs, args.num_shards)
    selected = shards[args.shard_index]
    print(
        json.dumps(
            {
                "model_key": args.model_key,
                "endpoint": args.endpoint,
                "shard_index": args.shard_index,
                "num_shards": args.num_shards,
                "jobs": [
                    {"label": job.label, "n": job.problem_count}
                    for job in selected
                ],
                "total_problems": sum(job.problem_count for job in selected),
                "dry_run": args.dry_run,
            },
            indent=2,
        )
    )
    if args.dry_run:
        for job in selected:
            print(" ".join(collector_command(args, job, split_manifest)))
        return

    runtime = output_root / "_runtime" / (
        f"{args.model_key}_shard_{args.shard_index}"
    )
    runtime.mkdir(parents=True, exist_ok=True)
    status_path = runtime / "status.json"
    started = time.time()
    atomic_status(
        status_path,
        {
            "state": "running",
            "model_key": args.model_key,
            "endpoint": args.endpoint,
            "shard_index": args.shard_index,
            "job_count": len(selected),
            "completed_jobs": 0,
            "started_unix": started,
        },
    )
    completed: list[dict] = []
    for index, job in enumerate(selected, start=1):
        job.output.mkdir(parents=True, exist_ok=True)
        log_path = runtime / f"{job.label}.log"
        command = collector_command(args, job, split_manifest)
        print(f"[{index}/{len(selected)}] {job.label}", flush=True)
        with log_path.open("a", encoding="utf-8") as log:
            result = subprocess.run(
                command,
                cwd=repo,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                check=False,
            )
        if result.returncode != 0:
            atomic_status(
                status_path,
                {
                    "state": "failed",
                    "model_key": args.model_key,
                    "endpoint": args.endpoint,
                    "shard_index": args.shard_index,
                    "failed_job": job.label,
                    "returncode": result.returncode,
                    "log": str(log_path),
                    "completed": completed,
                },
            )
            raise RuntimeError(
                f"{job.label} failed with {result.returncode}; see {log_path}"
            )
        completion = verify_job(job)
        completed.append(
            {
                "label": job.label,
                "problems": job.problem_count,
                "trials": int(completion["total_aux_calls"]),
            }
        )
        atomic_status(
            status_path,
            {
                "state": "running",
                "model_key": args.model_key,
                "endpoint": args.endpoint,
                "shard_index": args.shard_index,
                "job_count": len(selected),
                "completed_jobs": len(completed),
                "completed": completed,
                "updated_unix": time.time(),
            },
        )

    atomic_status(
        status_path,
        {
            "state": "complete",
            "model_key": args.model_key,
            "endpoint": args.endpoint,
            "shard_index": args.shard_index,
            "job_count": len(selected),
            "completed_jobs": len(completed),
            "completed": completed,
            "elapsed_seconds": time.time() - started,
        },
    )
    print(f"shard complete: {status_path}")


if __name__ == "__main__":
    main()
