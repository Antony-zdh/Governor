#!/usr/bin/env python3
"""Materialize a protocol dataset so splitting and collection use identical rows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", required=True)
    parser.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="override the source path declared in the protocol",
    )
    return parser.parse_args()


def benchmark_config(
    protocol: Dict[str, Any], benchmark_name: str
) -> Dict[str, Any]:
    matches = [
        item
        for item in protocol["environments"]["benchmarks"]
        if item["name"] == benchmark_name
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one protocol entry for {benchmark_name}, got {len(matches)}"
        )
    return matches[0]


def load_and_normalize(benchmark_name: str) -> list[Dict[str, Any]]:
    if benchmark_name != "gsm8k":
        raise ValueError(
            "only gsm8k needs remote materialization in the current protocol"
        )
    try:
        from datasets import load_dataset
    except ImportError as error:
        raise RuntimeError(
            "materializing gsm8k requires the Hugging Face 'datasets' package"
        ) from error
    rows = [
        dict(row)
        for row in load_dataset("openai/gsm8k", "main", split="test")
    ]
    for index, row in enumerate(rows):
        raw_answer = str(row["answer"])
        final_answer = raw_answer.rsplit("####", 1)[-1].strip()
        row["problem"] = (
            "Solve the problem and put only the final numeric answer inside "
            "\\boxed{}. "
            + str(row["question"])
        )
        row["answer"] = final_answer.replace(",", "")
        row["subject"] = "GSM8K arithmetic"
        row["level"] = 0
        row["unique_id"] = f"gsm8k/test/{index}"
    return rows


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    benchmark = benchmark_config(protocol, args.benchmark)
    declared = benchmark.get("source", {}).get("path")
    if args.output is None and not declared:
        raise ValueError("protocol source.path is empty; pass --output")
    output = args.output or Path(str(declared))
    if not output.is_absolute():
        output = REPO_ROOT / output
    rows = load_and_normalize(args.benchmark)
    required = {
        str(benchmark.get("text_field", "problem")),
        "answer",
    }
    for index, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            raise ValueError(f"row {index} is missing fields {sorted(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                "benchmark": args.benchmark,
                "rows": len(rows),
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
