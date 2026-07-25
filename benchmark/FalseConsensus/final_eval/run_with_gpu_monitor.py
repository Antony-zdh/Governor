#!/usr/bin/env python3
"""Run a command while sampling NVIDIA utilization, memory, and power."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path


QUERY = (
    "timestamp,index,utilization.gpu,memory.used,power.draw"
)
FIELDS = [
    "sample_wall_seconds",
    "timestamp",
    "gpu_index",
    "utilization_percent",
    "memory_used_mib",
    "power_watts",
]
SENSITIVE_ARGUMENTS = {"--api-key"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("provide a command after --")
    return args


def sample_gpus(elapsed: float) -> list[dict]:
    result = subprocess.run(
        [
            "nvidia-smi",
            f"--query-gpu={QUERY}",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        timestamp, index, utilization, memory, power = [
            value.strip() for value in line.split(",")
        ]
        rows.append(
            {
                "sample_wall_seconds": elapsed,
                "timestamp": timestamp,
                "gpu_index": int(index),
                "utilization_percent": float(utilization),
                "memory_used_mib": float(memory),
                "power_watts": float(power),
            }
        )
    return rows


def summarize(rows: list[dict], wall_seconds: float, interval: float) -> dict:
    gpu_ids = sorted({row["gpu_index"] for row in rows})
    result = {
        "wall_clock_seconds": wall_seconds,
        "gpu_count": len(gpu_ids),
        "allocated_gpu_seconds": wall_seconds * len(gpu_ids),
        "sample_interval_seconds": interval,
        "samples": len(rows),
        "per_gpu": {},
    }
    for gpu_id in gpu_ids:
        values = [row for row in rows if row["gpu_index"] == gpu_id]
        utilization = [row["utilization_percent"] for row in values]
        memory = [row["memory_used_mib"] for row in values]
        power = [row["power_watts"] for row in values]
        result["per_gpu"][str(gpu_id)] = {
            "samples": len(values),
            "mean_utilization_percent": sum(utilization) / len(utilization),
            "active_gpu_seconds_utilization_integral": (
                sum(utilization) / 100 * interval
            ),
            "peak_memory_used_mib": max(memory),
            "mean_power_watts": sum(power) / len(power),
            "energy_watt_hours_estimate": (
                sum(power) * interval / 3600
            ),
        }
    return result


def redact_command(command: list[str]) -> list[str]:
    redacted = []
    hide_next = False
    for value in command:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        if value in SENSITIVE_ARGUMENTS:
            redacted.append(value)
            hide_next = True
            continue
        if any(value.startswith(f"{flag}=") for flag in SENSITIVE_ARGUMENTS):
            redacted.append(value.split("=", 1)[0] + "=<redacted>")
            continue
        redacted.append(value)
    return redacted


def next_segment(output: Path) -> int:
    existing = sorted(output.glob("gpu_summary.segment_*.json"))
    if (output / "gpu_summary.json").exists() and not existing:
        raise ValueError(
            f"{output} contains legacy GPU accounting without segment files; "
            "preserve it and use a new monitor output directory"
        )
    return len(existing) + 1


def write_samples(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def aggregate_segments(output: Path) -> dict:
    summaries = []
    combined_rows = []
    elapsed_offset = 0.0
    for summary_path in sorted(output.glob("gpu_summary.segment_*.json")):
        suffix = summary_path.stem.removeprefix("gpu_summary.")
        sample_path = output / f"gpu_samples.{suffix}.csv"
        summary = json.loads(summary_path.read_text())
        summaries.append(summary)
        if sample_path.exists():
            with sample_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    parsed = {
                        "sample_wall_seconds": (
                            float(row["sample_wall_seconds"]) + elapsed_offset
                        ),
                        "timestamp": row["timestamp"],
                        "gpu_index": int(row["gpu_index"]),
                        "utilization_percent": float(
                            row["utilization_percent"]
                        ),
                        "memory_used_mib": float(row["memory_used_mib"]),
                        "power_watts": float(row["power_watts"]),
                    }
                    combined_rows.append(parsed)
        elapsed_offset += float(summary["wall_clock_seconds"])
    write_samples(output / "gpu_samples.csv", combined_rows)

    gpu_ids = sorted(
        {
            gpu_id
            for summary in summaries
            for gpu_id in summary.get("per_gpu", {})
        },
        key=int,
    )
    per_gpu = {}
    for gpu_id in gpu_ids:
        values = [
            summary["per_gpu"][gpu_id]
            for summary in summaries
            if gpu_id in summary.get("per_gpu", {})
        ]
        sample_count = sum(int(value.get("samples", 0)) for value in values)
        per_gpu[gpu_id] = {
            "samples": sample_count,
            "mean_utilization_percent": (
                sum(
                    value["mean_utilization_percent"]
                    * int(value.get("samples", 0))
                    for value in values
                )
                / sample_count
                if sample_count
                else 0.0
            ),
            "active_gpu_seconds_utilization_integral": sum(
                value["active_gpu_seconds_utilization_integral"]
                for value in values
            ),
            "peak_memory_used_mib": max(
                value["peak_memory_used_mib"] for value in values
            ),
            "mean_power_watts": (
                sum(
                    value["mean_power_watts"]
                    * int(value.get("samples", 0))
                    for value in values
                )
                / sample_count
                if sample_count
                else 0.0
            ),
            "energy_watt_hours_estimate": sum(
                value["energy_watt_hours_estimate"] for value in values
            ),
        }
    aggregate = {
        "wall_clock_seconds": sum(
            float(summary["wall_clock_seconds"]) for summary in summaries
        ),
        "gpu_count": len(gpu_ids),
        "allocated_gpu_seconds": sum(
            float(summary.get("allocated_gpu_seconds", 0))
            for summary in summaries
        ),
        "samples": sum(int(summary.get("samples", 0)) for summary in summaries),
        "segments": len(summaries),
        "segment_return_codes": [
            int(summary["return_code"]) for summary in summaries
        ],
        "return_code": int(summaries[-1]["return_code"]),
        "commands": [summary["command"] for summary in summaries],
        "sample_errors": [
            {"segment": index + 1, **error}
            for index, summary in enumerate(summaries)
            for error in summary.get("sample_errors", [])
        ],
        "per_gpu": per_gpu,
    }
    (output / "gpu_summary.json").write_text(
        json.dumps(aggregate, indent=2) + "\n"
    )
    return aggregate


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    segment = next_segment(args.output)
    segment_name = f"segment_{segment:04d}"
    started = time.perf_counter()
    process = subprocess.Popen(args.command)
    rows = []
    sample_errors = []
    while process.poll() is None:
        elapsed = time.perf_counter() - started
        try:
            rows.extend(sample_gpus(elapsed))
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            sample_errors.append({"elapsed": elapsed, "error": str(error)})
        time.sleep(args.interval)
    wall_seconds = time.perf_counter() - started
    write_samples(args.output / f"gpu_samples.{segment_name}.csv", rows)
    summary = summarize(rows, wall_seconds, args.interval) if rows else {
        "wall_clock_seconds": wall_seconds,
        "gpu_count": 0,
        "allocated_gpu_seconds": 0,
        "samples": 0,
    }
    summary.update(
        {
            "command": redact_command(args.command),
            "return_code": process.returncode,
            "sample_errors": sample_errors,
        }
    )
    (args.output / f"gpu_summary.{segment_name}.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    aggregate_segments(args.output)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
