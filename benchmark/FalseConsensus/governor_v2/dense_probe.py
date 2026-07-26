#!/usr/bin/env python3
"""Attach a dense simple@32 probe bank to frozen Governor v2 trajectories."""

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
from typing import Any, Dict, Iterable, List

import openai


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))
sys.path.insert(0, str(REPO_ROOT))


SIMPLE_SUFFIX = "**Final Answer**\n\n\\[ \\boxed{"
UNCERTAIN_WORDS = ("wait", "hold", "but", "okay", "no", "hmm")
CSV_FIELDS = (
    "problem_id",
    "dataset",
    "model",
    "base_seed",
    "token_position",
    "probe_id",
    "probe_answer",
    "is_certain",
    "probe_out_tokens",
    "probe_prompt_tokens",
    "probe_latency_seconds",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://localhost:8000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", default=None)
    parser.add_argument("--interval", type=int, default=64)
    parser.add_argument("--start-token", type=int, default=64)
    parser.add_argument("--probe-tokens", type=int, default=32)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--flatten-only", action="store_true")
    return parser.parse_args()


def checkpoint_positions(
    token_count: int,
    *,
    start_token: int,
    interval: int,
    finished_naturally: bool,
) -> List[int]:
    if token_count <= 0:
        return []
    inclusive_stop = token_count + (0 if finished_naturally else 1)
    return list(range(start_token, inclusive_stop, interval))


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def flatten(probe_dir: Path, output_csv: Path) -> int:
    rows = []
    for path in sorted(probe_dir.glob("problem_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("probes", []):
            rows.append(
                {
                    "problem_id": payload["problem_id"],
                    "dataset": payload["dataset"],
                    "model": payload["model"],
                    "base_seed": payload["base_seed"],
                    **record,
                }
            )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_csv.with_suffix(output_csv.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=CSV_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, output_csv)
    return len(rows)


class DenseProbeCollector:
    def __init__(self, args: argparse.Namespace, main_manifest: Dict[str, Any]):
        from clients import apply_chat_template
        from dynasor.core.entropy import obtain_answer
        from dynasor.core.evaluator import strip_string
        self.args = args
        self.apply_chat_template = apply_chat_template
        self.obtain_answer = obtain_answer
        self.strip_string = strip_string
        self.main_settings = dict(main_manifest["run_settings"])
        self.model = args.model or str(self.main_settings["model"])
        if self.model != self.main_settings["model"]:
            raise ValueError("--model disagrees with main trajectory manifest")
        self.dataset = str(self.main_settings["dataset"])
        self.base_seed = int(self.main_settings["base_seed"])
        self.client = openai.OpenAI(
            api_key=args.api_key,
            base_url=args.url,
            timeout=600,
        )
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(self.model)
        self.output = args.output
        self.probe_dir = self.output / "probes"
        self.probe_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.settings = {
            "collection_schema": "governor-v2-dense-probe-1",
            "main_run": str(args.main_run),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "probe_style": "simple",
            "probe_tokens": args.probe_tokens,
            "dense_interval": args.interval,
            "start_token": args.start_token,
        }
        self._initialize_manifest()

    def _initialize_manifest(self) -> None:
        path = self.output / "probe_manifest.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("probe_settings") != self.settings:
                raise ValueError(
                    "existing probe output has different settings"
                )
            return
        atomic_write_json(
            path,
            {
                "schema_version": "governor-v2-probe-run-1",
                "probe_settings": self.settings,
                "api_key_recorded": False,
            },
        )

    def complete(self, prompt: str):
        last_error = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                response = self.client.completions.create(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=self.args.probe_tokens,
                    temperature=float(self.main_settings["temperature"]),
                    top_p=float(self.main_settings["top_p"]),
                    seed=self.base_seed,
                    stop=["\\]"],
                    stream=False,
                )
                return response, time.perf_counter() - started
            except Exception as error:
                last_error = error
                time.sleep(5 * (attempt + 1))
        raise last_error

    def collect(self, trajectory_path: Path) -> int:
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        output_path = self.probe_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            return problem_id
        token_ids = self.tokenizer.encode(
            trajectory["full_text"], add_special_tokens=False
        )
        positions = checkpoint_positions(
            min(len(token_ids), int(self.main_settings["budget"])),
            start_token=self.args.start_token,
            interval=self.args.interval,
            finished_naturally=bool(trajectory["finished_naturally"]),
        )
        chat = self.apply_chat_template(
            str(trajectory["problem"]).strip(), self.model
        )
        records = []
        for probe_id, position in enumerate(positions, start=1):
            prefix = self.tokenizer.decode(token_ids[:position])
            response, latency = self.complete(chat + prefix + SIMPLE_SUFFIX)
            probe_text = str(response.choices[0].text)
            answer = self.obtain_answer(probe_text)
            answer = self.strip_string(answer) if answer else ""
            records.append(
                {
                    "token_position": position,
                    "probe_id": probe_id,
                    "probe_answer": answer,
                    "is_certain": not any(
                        word in probe_text.lower()
                        for word in UNCERTAIN_WORDS
                    ),
                    "probe_out_tokens": int(
                        response.usage.completion_tokens
                    ),
                    "probe_prompt_tokens": int(
                        response.usage.prompt_tokens
                    ),
                    "probe_latency_seconds": latency,
                }
            )
        payload = {
            "schema_version": "governor-v2-probe-trajectory-1",
            "problem_id": problem_id,
            "dataset": self.dataset,
            "model": self.model,
            "base_seed": self.base_seed,
            "main_token_count_recorded": trajectory["tokens_used"],
            "main_token_count_reencoded": len(token_ids),
            "probes": records,
        }
        with self.lock:
            atomic_write_json(output_path, payload)
        return problem_id


def trajectory_paths(main_run: Path) -> Iterable[Path]:
    return sorted((main_run / "traj").glob("problem_*.json"))


def main() -> None:
    args = parse_args()
    probe_dir = args.output / "probes"
    if args.flatten_only:
        count = flatten(probe_dir, args.output / "probes.csv")
        print(f"flattened {count} probes")
        return
    manifest = json.loads(
        (args.main_run / "run_manifest.json").read_text(encoding="utf-8")
    )
    collector = DenseProbeCollector(args, manifest)
    paths = list(trajectory_paths(args.main_run))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collector.collect, path) for path in paths]
        for index, future in enumerate(as_completed(futures), start=1):
            problem_id = future.result()
            print(f"[{index}/{len(paths)}] problem {problem_id}", flush=True)
    count = flatten(probe_dir, args.output / "probes.csv")
    print(f"flattened {count} probes")


if __name__ == "__main__":
    main()
