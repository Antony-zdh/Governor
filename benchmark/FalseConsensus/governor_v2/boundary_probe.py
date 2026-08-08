#!/usr/bin/env python3
"""G2 collector: simple@32 probes at DEER's own boundary positions.

G1 (``dense_probe.py``) reads a probe on a fixed 64-token grid. G2 holds
*when* fixed to DEER's own reading positions and varies only *what* is read
(the simple suffix). Boundary positions come from the committed DEER
confidence bank:

    results/related_work/deer_confidence_bank_cap30/full/<env>/trials.jsonl.gz

where each trial records the ``token_position`` at which DEER generated a
trial answer. We probe exactly those positions on the same frozen prefixes
with the Arm-A (simple) suffix, so the resulting stream is comparable to the
fixed-grid consensus stream except that the schedule is DEER's boundary
schedule instead of 64 tokens.

Output (sibling of dense_simple32):

    results/governor_v2/development__<env>/boundary_simple32/
        probe_manifest.json   (probe_style "simple", probe_schedule "deer_boundary")
        probes/problem_<id>.json
        probes.csv

The per-problem JSON schema is identical to dense_simple32 so the existing
replay machinery reads it unchanged; the manifest carries the extra
``probe_schedule`` and ``deer_bank`` fields.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import openai

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))
sys.path.insert(0, str(REPO_ROOT))

# Reuse the G1 collector's shared definitions so the two arms stay byte-for-
# byte consistent (suffix, CSV schema, atomic writes).
try:
    from dense_probe import (  # noqa: E402
        PROBE_SUFFIXES,
        SIMPLE_SUFFIX,
        CSV_FIELDS,
        UNCERTAIN_WORDS,
        atomic_write_json,
        flatten,
    )
except ModuleNotFoundError:
    from benchmark.FalseConsensus.governor_v2.dense_probe import (
        PROBE_SUFFIXES,
        SIMPLE_SUFFIX,
        CSV_FIELDS,
        UNCERTAIN_WORDS,
        atomic_write_json,
        flatten,
    )
from clients import apply_chat_template  # noqa: E402
from dynasor.core.entropy import obtain_answer  # noqa: E402
from dynasor.core.evaluator import strip_string  # noqa: E402

_TEMPLATE_SENTINEL = "What is 1+1?"

# Map a governor_v2 environment directory name to the DEER bank's model slug
# (the bank uses "deepseek" / "qwen3", not the full HF id).
DEER_MODEL_SLUG = {
    "deepseek-ai-deepseek-r1-distill-qwen-7b": "deepseek",
    "qwen-qwen3-8b": "qwen3",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--main-run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--deer-bank", type=Path, required=True,
                   help="trials.jsonl.gz directory for this env")
    p.add_argument("--url", default="http://localhost:8000/v1")
    p.add_argument("--api-key", default="token-abc123")
    p.add_argument("--model", default=None)
    p.add_argument("--probe-tokens", type=int, default=32)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--problem-ids", type=Path, default=None,
                   help="restrict to these problem ids (dev split)")
    p.add_argument("--flatten-only", action="store_true")
    return p.parse_args()


def load_boundary_positions(deer_dir: Path) -> dict[int, list[int]]:
    """problem_id -> sorted unique boundary token_positions (capped at 30)."""
    trials_path = deer_dir / "trials.jsonl.gz"
    out: dict[int, list[int]] = {}
    generated_counts: dict[int, int] = {}
    with gzip.open(trials_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            pid = int(rec["problem_id"])
            positions = sorted({
                int(t["token_position"])
                for t in rec.get("trials", [])
                if t.get("token_position") is not None
            })
            # The DEER bank caps trials at 30 per problem.
            positions = positions[:30]
            out[pid] = positions
            generated_counts[pid] = int(rec.get("generated_trial_count", 0))
    # Sanity: report agreement with generated_trial_count (validation the GOAL
    # asks for). Distinct positions should match the number of trials DEER
    # generated, modulo the 30-cap and reused trials.
    return out


class BoundaryProbeCollector:
    def __init__(self, args: argparse.Namespace, main_manifest: dict[str, Any]):
        self.args = args
        self.main_settings = dict(main_manifest["run_settings"])
        self.model = args.model or str(self.main_settings["model"])
        if self.model != self.main_settings["model"]:
            raise ValueError("--model disagrees with main trajectory manifest")
        self.dataset = str(self.main_settings["dataset"])
        self.base_seed = int(self.main_settings["base_seed"])
        self.suffix = PROBE_SUFFIXES["simple"]
        self.allowed_ids = self._load_problem_ids(args.problem_ids)
        self.client = openai.OpenAI(
            api_key=args.api_key, base_url=args.url, timeout=600)
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model)
        self.output = args.output
        self.probe_dir = self.output / "probes"
        self.probe_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        template_fp = hashlib.sha256(
            apply_chat_template(_TEMPLATE_SENTINEL, self.model).encode("utf-8")
        ).hexdigest()
        suffix_fp = hashlib.sha256(
            self.suffix.encode("utf-8")).hexdigest()
        self.settings = {
            "collection_schema": "governor-v2-dense-probe-1",
            "main_run": str(args.main_run),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "probe_style": "simple",
            "probe_schedule": "deer_boundary",
            "probe_suffix_sha256": suffix_fp,
            "chat_template_sha256": template_fp,
            "tokenizer_model": self.model,
            "probe_tokens": args.probe_tokens,
            "deer_bank": str(args.deer_bank),
        }
        self._initialize_manifest()

    @staticmethod
    def _load_problem_ids(path):
        if path is None:
            return None
        ids = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                ids.add(int(line))
        return ids

    def _initialize_manifest(self):
        path = self.output / "probe_manifest.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("probe_settings") != self.settings:
                raise ValueError(
                    "existing probe output has different settings")
            return
        atomic_write_json(path, {
            "schema_version": "governor-v2-probe-run-1",
            "probe_settings": self.settings,
            "api_key_recorded": False,
        })

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

    def collect(self, trajectory_path: Path, positions_for_problem):
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        if self.allowed_ids is not None and problem_id not in self.allowed_ids:
            return problem_id
        output_path = self.probe_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            return problem_id
        token_ids = self.tokenizer.encode(
            trajectory["full_text"], add_special_tokens=False)
        n_tokens = len(token_ids)
        positions = positions_for_problem(problem_id)
        # Clamp to the trajectory's own length: a boundary beyond the frozen
        # prefix has no defined state to read.
        positions = [p for p in positions if 0 < p <= n_tokens]
        chat = self.apply_chat_template_str(trajectory)
        records = []
        for probe_id, position in enumerate(positions, start=1):
            prefix = self.tokenizer.decode(token_ids[:position])
            response, latency = self.complete(chat + prefix + self.suffix)
            probe_text = str(response.choices[0].text)
            answer = obtain_answer(probe_text)
            answer = strip_string(answer) if answer else ""
            records.append({
                "token_position": position,
                "probe_id": probe_id,
                "probe_answer": answer,
                "is_certain": not any(
                    word in probe_text.lower() for word in UNCERTAIN_WORDS),
                "probe_out_tokens": int(response.usage.completion_tokens),
                "probe_prompt_tokens": int(response.usage.prompt_tokens),
                "probe_latency_seconds": latency,
            })
        payload = {
            "schema_version": "governor-v2-probe-trajectory-1",
            "problem_id": problem_id,
            "dataset": self.dataset,
            "model": self.model,
            "base_seed": self.base_seed,
            "main_token_count_recorded": trajectory["tokens_used"],
            "main_token_count_reencoded": n_tokens,
            "probe_schedule": "deer_boundary",
            "probes": records,
        }
        with self.lock:
            atomic_write_json(output_path, payload)
        return problem_id

    def apply_chat_template_str(self, trajectory):
        return apply_chat_template(str(trajectory["problem"]).strip(), self.model)


def main() -> None:
    args = parse_args()
    probe_dir = args.output / "probes"
    if args.flatten_only:
        count = flatten(probe_dir, args.output / "probes.csv")
        print(f"flattened {count} probes")
        return
    manifest = json.loads(
        (args.main_run / "run_manifest.json").read_text(encoding="utf-8"))
    collector = BoundaryProbeCollector(args, manifest)
    boundaries = load_boundary_positions(args.deer_bank)

    def positions_for_problem(pid):
        return boundaries.get(pid, [])

    paths = sorted((args.main_run / "traj").glob("problem_*.json"))
    if collector.allowed_ids is not None:
        paths = [p for p in paths
                 if int(p.stem.split("_")[-1]) in collector.allowed_ids]
    # Only keep problems that actually have boundary positions.
    paths = [p for p in paths
             if positions_for_problem(int(p.stem.split("_")[-1]))]
    total_pos = sum(len(positions_for_problem(int(p.stem.split("_")[-1])))
                    for p in paths)
    print(f"probe_schedule=deer_boundary suffix_sha256="
          f"{collector.settings['probe_suffix_sha256'][:12]}... "
          f"chat_template_sha256={collector.settings['chat_template_sha256'][:12]}... "
          f"{len(paths)} problems, {total_pos} boundary probes to collect",
          flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collector.collect, p, positions_for_problem)
                   for p in paths]
        for index, future in enumerate(as_completed(futures), start=1):
            pid = future.result()
            print(f"[{index}/{len(paths)}] problem {pid}", flush=True)
    count = flatten(probe_dir, args.output / "probes.csv")
    print(f"flattened {count} probes")


if __name__ == "__main__":
    main()
