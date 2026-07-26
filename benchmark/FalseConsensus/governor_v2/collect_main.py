#!/usr/bin/env python3
"""Collect probe-independent main reasoning trajectories for Governor v2.

Unlike the legacy interleaved logger, this runner makes one main-generation
request per problem.  Dense simple@32 probes are added later from frozen text
prefixes, so changing a probe schedule cannot change the main trajectory.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

import openai


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))
sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=None,
        help=(
            "optional materialized JSONL/JSON/CSV dataset; use this for "
            "split-manifest/collection identity"
        ),
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", default="http://localhost:8000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument(
        "--problem-ids-file",
        type=Path,
        default=None,
        help="optional JSON list or newline-delimited problem indices",
    )
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument(
        "--phase", choices=("development", "confirmation"), required=True
    )
    parser.add_argument("--model-role", required=True)
    parser.add_argument(
        "--split-labels",
        required=True,
        help="comma-separated split labels visible to this collection run",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_problem_ids(path: Optional[Path]) -> Optional[Set[int]]:
    if path is None:
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return set()
    if text.startswith("["):
        return {int(value) for value in json.loads(text)}
    return {int(line) for line in text.splitlines() if line.strip()}


def load_materialized_dataset(path: Path) -> list[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON list")
        return [dict(row) for row in payload]
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ValueError(f"unsupported materialized dataset suffix: {suffix}")


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class MainCollector:
    def __init__(self, args: argparse.Namespace):
        from clients import apply_chat_template
        from dynasor.core.evaluator import extract_answer, strip_string
        from grading import robust_answers_equal

        self.args = args
        self.apply_chat_template = apply_chat_template
        self.extract_answer = extract_answer
        self.answers_equal = robust_answers_equal
        self.strip_string = strip_string
        self.client = openai.OpenAI(
            api_key=args.api_key,
            base_url=args.url,
            timeout=600,
        )
        self.output = args.output
        self.traj_dir = self.output / "traj"
        self.traj_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.settings = {
            "collection_schema": "governor-v2-main-1",
            "model": args.model,
            "dataset": args.dataset,
            "dataset_path": (
                str(args.dataset_path.resolve()) if args.dataset_path else None
            ),
            "budget": args.budget,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "base_seed": args.seed,
            "protocol_version": args.protocol_version,
            "phase": args.phase,
            "model_role": args.model_role,
            "split_labels": [
                value for value in args.split_labels.split(",") if value
            ],
            "problem_ids_file": (
                str(args.problem_ids_file.resolve())
                if args.problem_ids_file
                else None
            ),
            "main_request_mode": "single_request",
        }
        self._initialize_manifest()

    def _initialize_manifest(self) -> None:
        path = self.output / "run_manifest.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("run_settings") != self.settings:
                raise ValueError(
                    "existing output has different run settings: "
                    f"{existing.get('run_settings')}"
                )
            return
        atomic_write_json(
            path,
            {
                "schema_version": "governor-v2-main-run-1",
                "run_settings": self.settings,
                "api_key_recorded": False,
            },
        )

    def complete(self, prompt: str, seed: int):
        last_error = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                response = self.client.completions.create(
                    model=self.args.model,
                    prompt=prompt,
                    max_tokens=self.args.budget,
                    temperature=self.args.temperature,
                    top_p=self.args.top_p,
                    seed=seed,
                    stream=False,
                )
                return response, time.perf_counter() - started
            except Exception as error:  # transient service failure
                last_error = error
                time.sleep(5 * (attempt + 1))
        raise last_error

    def collect(
        self,
        problem_id: int,
        problem: str,
        target: Any,
        metadata: Dict[str, Any],
    ) -> int:
        output_path = self.traj_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            existing_settings = dict(existing.get("run_settings") or {})
            # per-problem derived seed; not part of the shared run settings
            existing_settings.pop("main_seed", None)
            if existing_settings != self.settings:
                raise ValueError(
                    f"{output_path} has incompatible run settings"
                )
            return problem_id
        prompt = self.apply_chat_template(problem.strip(), self.args.model)
        response, latency = self.complete(
            prompt, seed=self.args.seed + problem_id
        )
        text = str(response.choices[0].text)
        finish_reason = str(response.choices[0].finish_reason)
        completion_tokens = int(response.usage.completion_tokens)
        prompt_tokens = int(response.usage.prompt_tokens)
        final_answer = self.extract_answer(text, self.args.dataset)
        final_answer = self.strip_string(final_answer) if final_answer else ""
        payload = {
            "schema_version": "governor-v2-main-trajectory-1",
            "problem_id": problem_id,
            "dataset": self.args.dataset,
            "problem": problem,
            "target": target,
            "level": metadata.get("level", 0),
            "subject": metadata.get("subject", self.args.dataset),
            "unique_id": metadata.get("unique_id"),
            "full_text": text,
            "tokens_used": completion_tokens,
            "finished_naturally": finish_reason != "length",
            "finish_reason": finish_reason,
            "final_answer": final_answer,
            "final_correct": bool(self.answers_equal(final_answer, target)),
            "accounting": {
                "main_decode_tokens": completion_tokens,
                "main_prompt_tokens": prompt_tokens,
                "main_calls": 1,
                "main_wall_clock_seconds": latency,
            },
            "run_settings": {
                **self.settings,
                "main_seed": self.args.seed + problem_id,
            },
        }
        with self.lock:
            atomic_write_json(output_path, payload)
        return problem_id


def selected_indices(
    total: int,
    start: int,
    end: Optional[int],
    explicit_ids: Optional[Set[int]],
) -> Iterable[int]:
    stop = total if end is None else min(total, end)
    for index in range(max(0, start), stop):
        if explicit_ids is None or index in explicit_ids:
            yield index


def main() -> None:
    args = parse_args()
    if args.dataset_path:
        dataset = load_materialized_dataset(args.dataset_path)
    else:
        from utils import load_dataset

        dataset = load_dataset(args.dataset)
    ids = list(
        selected_indices(
            len(dataset),
            args.start,
            args.end,
            load_problem_ids(args.problem_ids_file),
        )
    )
    collector = MainCollector(args)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for problem_id in ids:
            row = dataset[problem_id]
            problem = str(row.get("problem", row.get("question", "")))
            target = row["answer"]
            futures.append(
                pool.submit(
                    collector.collect,
                    problem_id,
                    problem,
                    target,
                    dict(row),
                )
            )
        completed = 0
        for future in as_completed(futures):
            problem_id = future.result()
            completed += 1
            print(
                f"[{completed}/{len(futures)}] problem {problem_id}",
                flush=True,
            )


if __name__ == "__main__":
    main()
