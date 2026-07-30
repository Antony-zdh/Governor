#!/usr/bin/env python3
"""Probe-cost v2: collect REAL cap-specific probe banks.

For every frozen DEV main trajectory, at every interval-64 eligible position
(start=64), generate a genuine probe with max_tokens in {8, 16, 32}. Mirrors
the authoritative ``dense_simple32`` probe semantics exactly (chat template +
decoded prefix + SIMPLE_SUFFIX, stop=["]"], same temp/top_p/seed) so that the
cap-32 bank is directly comparable to the existing dense bank. Unlike the old
placeholder, NO character slicing is performed: each cap is a real capped
generation, and the model's own tokenizer enforces/counts the cap.

Stores raw audit evidence per probe (text, finish_reason, actual completion
tokens, re-encoded token ids + provenance flag, prompt tokens, parsed answer,
certainty). Interval 128/256/512 are derived later by strict position
downsampling during replay (no repeated probe calls).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import openai

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]  # .../Governor
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))
sys.path.insert(0, str(REPO_ROOT))

from clients import apply_chat_template  # noqa: E402
from dynasor.core.entropy import obtain_answer  # noqa: E402
from dynasor.core.evaluator import strip_string  # noqa: E402

SIMPLE_SUFFIX = "**Final Answer**\n\n\\[ \\boxed{"
UNCERTAIN_WORDS = ("wait", "hold", "but", "okay", "no", "hmm")
SCHEMA = "probe-cost-v2-cap-bank-1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--main-run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--url", default="http://localhost:8000/v1")
    p.add_argument("--api-key", default="token-abc123")
    p.add_argument("--model", default=None)
    p.add_argument("--caps", default="8,16,32")
    p.add_argument("--start-token", type=int, default=64)
    p.add_argument("--interval", type=int, default=64)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--problem-ids-file", type=Path, default=None,
                   help="restrict to these dataset indices (dev split)")
    p.add_argument("--timeout", type=float, default=600.0)
    return p.parse_args()


def read_problem_ids(path: Path) -> set:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return set()
    if raw.lstrip().startswith("["):
        return set(int(x) for x in json.loads(raw))
    out = set()
    for line in raw.splitlines():
        line = line.strip()
        if line:
            out.add(int(line))
    return out


def checkpoint_positions(token_count: int, *, start_token: int,
                          interval: int, finished_naturally: bool) -> List[int]:
    if token_count <= 0:
        return []
    inclusive_stop = token_count + (0 if finished_naturally else 1)
    return list(range(start_token, inclusive_stop, interval))


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


class CapProbeCollector:
    def __init__(self, args: argparse.Namespace, main_manifest: Dict[str, Any]):
        self.args = args
        self.main_settings = dict(main_manifest["run_settings"])
        self.model = args.model or str(self.main_settings["model"])
        if self.model != self.main_settings["model"]:
            raise ValueError("--model disagrees with main trajectory manifest")
        self.dataset = str(self.main_settings["dataset"])
        self.base_seed = int(self.main_settings["base_seed"])
        self.caps: List[int] = [int(c) for c in args.caps.split(",") if c.strip()]
        self.client = openai.OpenAI(api_key=args.api_key, base_url=args.url,
                                    timeout=args.timeout)
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model)
        self.bos_token_id = self.tokenizer.bos_token_id
        self.obtain_answer = obtain_answer
        self.strip_string = strip_string
        self.output = args.output
        self.probe_dir = self.output / "probes"
        self.probe_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.settings = {
            "collection_schema": "probe-cost-v2-cap-probe-1",
            "main_run": str(Path(args.main_run).resolve()),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "probe_style": "simple",
            "caps": self.caps,
            "start_token": args.start_token,
            "interval": args.interval,
            "simple_suffix": SIMPLE_SUFFIX,
            "stop_token": "\\]",
            "temperature": float(self.main_settings["temperature"]),
            "top_p": float(self.main_settings["top_p"]),
            "seed_per_probe": self.base_seed,
            "prompt_semantics": "apply_chat_template(problem)+decode(token_ids[:pos])+SIMPLE_SUFFIX; identical to dense_simple32 for cap=32",
        }
        self._initialize_manifest()

    def _initialize_manifest(self) -> None:
        path = self.output / "probe_manifest.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("probe_settings") != self.settings:
                raise ValueError("existing cap-probe output has different settings")
            return
        atomic_write_json(path, {
            "schema_version": "probe-cost-v2-cap-run-1",
            "probe_settings": self.settings,
            "bos_token_id": self.bos_token_id,
            "api_key_recorded": False,
        })

    def complete(self, prompt: str, cap: int):
        last_error = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                response = self.client.completions.create(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=cap,
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
        token_ids = self.tokenizer.encode(trajectory["full_text"],
                                          add_special_tokens=False)
        positions = checkpoint_positions(
            min(len(token_ids), int(self.main_settings["budget"])),
            start_token=self.args.start_token,
            interval=self.args.interval,
            finished_naturally=bool(trajectory["finished_naturally"]),
        )
        chat = apply_chat_template(str(trajectory["problem"]).strip(), self.model)
        by_cap: Dict[str, List[Dict[str, Any]]] = {str(c): [] for c in self.caps}
        for probe_id, position in enumerate(positions, start=1):
            prefix = self.tokenizer.decode(token_ids[:position])
            base_prompt = chat + prefix + SIMPLE_SUFFIX
            for cap in self.caps:
                response, latency = self.complete(base_prompt, cap)
                choice = response.choices[0]
                probe_text = str(choice.text)
                answer = self.obtain_answer(probe_text)
                answer = self.strip_string(answer) if answer else ""
                finish_reason = str(choice.finish_reason)
                actual_out = int(response.usage.completion_tokens)
                prompt_tokens = int(response.usage.prompt_tokens)
                reencoded_ids = self.tokenizer.encode(probe_text,
                                                       add_special_tokens=False)
                cap_ok = actual_out <= cap
                by_cap[str(cap)].append({
                    "token_position": position,
                    "probe_id": probe_id,
                    "cap": cap,
                    "probe_text": probe_text,
                    "probe_answer": answer,
                    "is_certain": not any(w in probe_text.lower()
                                          for w in UNCERTAIN_WORDS),
                    "probe_out_tokens": actual_out,
                    "probe_out_tokens_reencoded": len(reencoded_ids),
                    "probe_token_ids_provenance": "tokenizer_reencode",
                    "probe_token_ids": reencoded_ids,
                    "probe_prompt_tokens": prompt_tokens,
                    "finish_reason": finish_reason,
                    "cap_enforced_ok": cap_ok,
                    "probe_latency_seconds": latency,
                })
        payload = {
            "schema_version": SCHEMA,
            "problem_id": problem_id,
            "dataset": self.dataset,
            "model": self.model,
            "base_seed": self.base_seed,
            "main_token_count_recorded": trajectory["tokens_used"],
            "main_token_count_reencoded": len(token_ids),
            "finished_naturally": bool(trajectory["finished_naturally"]),
            "caps": self.caps,
            "positions": positions,
            "probes_by_cap": by_cap,
        }
        with self.lock:
            atomic_write_json(output_path, payload)
        return problem_id


def trajectory_paths(main_run: Path, allowed: set | None) -> Iterable[Path]:
    for path in sorted((main_run / "traj").glob("problem_*.json")):
        if allowed is None:
            yield path
            continue
        try:
            pid = int(path.stem.split("_")[1])
        except (ValueError, IndexError):
            continue
        if pid in allowed:
            yield path


def main() -> None:
    args = parse_args()
    manifest = json.loads((args.main_run / "run_manifest.json")
                          .read_text(encoding="utf-8"))
    collector = CapProbeCollector(args, manifest)
    allowed = (read_problem_ids(args.problem_ids_file)
               if args.problem_ids_file else None)
    paths = list(trajectory_paths(args.main_run, allowed))
    if not paths:
        print(f"[warn] no trajectories to process in {args.main_run}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collector.collect, p) for p in paths]
        for i, fut in enumerate(as_completed(futures), start=1):
            pid = fut.result()
            print(f"[{i}/{len(paths)}] problem {pid}", flush=True)
    print(f"done: {len(paths)} trajectories, caps={collector.caps}", flush=True)


if __name__ == "__main__":
    main()
