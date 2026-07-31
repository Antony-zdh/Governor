"""Durable sharded launcher for the TJE top-1..top-6 readout bank."""

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
    source_tje_dir: Path
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
    main_root = repo / "benchmark/FalseConsensus/results/governor_v2"
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
                main_run = main_root / environment / "main"
                source_tje_dir = (
                    related_root
                    / scope
                    / f"{model_key}__{benchmark}__seed_{seed}"
                    / "tje"
                )
                output = (
                    output_root
                    / scope
                    / f"{model_key}__{benchmark}__seed_{seed}"
                )
                if not (main_run / "run_manifest.json").exists():
                    raise FileNotFoundError(main_run / "run_manifest.json")
                if not (
                    source_tje_dir / "trigger_manifest.json"
                ).exists():
                    raise FileNotFoundError(
                        source_tje_dir / "trigger_manifest.json"
                    )
                problem_count = len(common.trajectory_paths(main_run))
                jobs.append(
                    Job(
                        scope=scope,
                        model_key=model_key,
                        benchmark=benchmark,
                        seed=int(seed),
                        main_run=main_run,
                        source_tje_dir=source_tje_dir,
                        output=output,
                        problem_count=problem_count,
                    )
                )
    return jobs


def balanced_shards(
    jobs: Sequence[Job], count: int
) -> list[list[Job]]:
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
        (
            "benchmark.FalseConsensus.related_work."
            "tje_threshold_readout_bank"
        ),
        "--main-run",
        str(job.main_run),
        "--output",
        str(job.output),
        "--source-tje-dir",
        str(job.source_tje_dir),
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
        "--max-model-len",
        str(args.max_model_len),
        "--readout-cap",
        str(args.readout_cap),
    ]


def verify_job(job: Job) -> dict:
    path = job.output / "bank_manifest.json"
    if not path.exists():
        raise ValueError(f"missing bank manifest: {path}")
    manifest = common.load_json(path)
    settings = manifest.get("bank_settings", {})
    completion = manifest.get("completion", {})
    expected = job.problem_count
    if settings.get("confidence_collection") != (
        "reuse faithful TJE labels only"
    ):
        raise ValueError(f"{job.label}: confidence reuse invariant failed")
    if (
        completion.get("complete") is not True
        or int(completion.get("expected_problem_count", -1)) != expected
        or int(completion.get("observed_problem_count", -1)) != expected
        or int(completion.get("missing_problem_count", -1)) != 0
        or int(completion.get("recorded_failures", -1)) != 0
    ):
        raise ValueError(f"{job.label}: incomplete manifest {completion}")
    return completion


def parse_args(
    argv: Optional[Sequence[str]] = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one shard of the TJE threshold readout bank"
    )
    parser.add_argument(
        "--model-key",
        choices=sorted(model_map.MODELS),
        required=True,
    )
    parser.add_argument("--endpoint", required=True)
    parser.add_argument(
        "--scope", choices=("full", "test", "both"), default="both"
    )
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--num-shards", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-model-len", type=int, required=True)
    parser.add_argument("--readout-cap", type=int, default=8192)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--python", type=Path, default=Path(sys.executable)
    )
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    repo = args.repo.resolve()
    if args.shard_index < 0 or args.shard_index >= args.num_shards:
        raise ValueError("--shard-index must be in [0, --num-shards)")
    output_root = (
        args.output_root.resolve()
        if args.output_root
        else (
            repo
            / "benchmark/FalseConsensus/results/related_work/"
            "tje_threshold_readout_bank_top1_6"
        )
    )
    scopes = (
        ("full", "test")
        if args.scope == "both"
        else (args.scope,)
    )
    split_manifest = (
        repo
        / "benchmark/FalseConsensus/governor_v2/generated/"
        "split_manifest.json"
    )
    jobs = discover_jobs(
        repo,
        model_key=args.model_key,
        scopes=scopes,
        output_root=output_root,
    )
    selected = balanced_shards(jobs, args.num_shards)[
        args.shard_index
    ]
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
                "total_problems": sum(
                    job.problem_count for job in selected
                ),
                "dry_run": args.dry_run,
            },
            indent=2,
        )
    )
    if args.dry_run:
        for job in selected:
            print(" ".join(collector_command(args, job, split_manifest)))
        return

    runtime = (
        output_root
        / "_runtime"
        / f"{args.model_key}_shard_{args.shard_index}"
    )
    runtime.mkdir(parents=True, exist_ok=True)
    status_path = runtime / "status.json"
    started = time.time()
    common.atomic_write_json(
        status_path,
        {
            "state": "running",
            "model_key": args.model_key,
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
        print(f"[{index}/{len(selected)}] {job.label}", flush=True)
        with log_path.open("a", encoding="utf-8") as log:
            result = subprocess.run(
                collector_command(args, job, split_manifest),
                cwd=repo,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                check=False,
            )
        if result.returncode != 0:
            common.atomic_write_json(
                status_path,
                {
                    "state": "failed",
                    "failed_job": job.label,
                    "returncode": result.returncode,
                    "log": str(log_path),
                    "completed": completed,
                },
            )
            raise RuntimeError(
                f"{job.label} failed; see {log_path}"
            )
        completion = verify_job(job)
        completed.append(
            {
                "label": job.label,
                "problems": job.problem_count,
                "readouts": int(completion["total_aux_calls"]),
            }
        )
        common.atomic_write_json(
            status_path,
            {
                "state": "running",
                "model_key": args.model_key,
                "shard_index": args.shard_index,
                "job_count": len(selected),
                "completed_jobs": len(completed),
                "completed": completed,
                "updated_unix": time.time(),
            },
        )
    common.atomic_write_json(
        status_path,
        {
            "state": "complete",
            "model_key": args.model_key,
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
