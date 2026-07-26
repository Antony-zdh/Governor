#!/usr/bin/env python3
"""Collect a superset bank for event-adaptive Governor v2 probing.

The main trajectory is never resampled.  Candidate positions are found from
the frozen text and from teacher-forced token entropy, then simple@32 is run
only on the corresponding frozen prefixes.  Offline rules may select subsets
of this bank by marker profile, entropy threshold, event type, cooldown, and
periodic fallback (the fallback positions come from the dense-64 bank).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Mapping

import openai


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.governor_v2.dense_probe import (  # noqa: E402
    SIMPLE_SUFFIX,
    UNCERTAIN_WORDS,
    atomic_write_json,
)


CONCLUSION_STRICT = (
    r"\btherefore\b",
    r"\bthus\b",
    r"\bhence\b",
    r"\bconsequently\b",
    r"\bit follows(?: that)?\b",
    r"\bwe (?:can )?conclude(?: that)?\b",
)
REFLECTION_TRANSITIONS = (
    r"\bwait\b",
    r"\bhold on\b",
    r"\bhowever\b",
    r"\balternatively\b",
    r"\bon second thought\b",
    r"\blet me (?:check|verify|reconsider|double-check)\b",
)
ANSWER_CANDIDATES = (
    r"\\boxed\s*\{",
    r"\bfinal answer\b",
    r"\b(?:answer|result|value)\s*(?:is|=)\b",
)
STEP_BOUNDARY = re.compile(r"\n\s*\n|(?<=[.!?])(?:\s+|$)|</think>", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument(
        "--dense-probe-bank",
        type=Path,
        default=None,
        help=(
            "reuse matching simple@32 prefixes from this dense bank instead "
            "of issuing duplicate requests"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://localhost:8000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", default=None)
    parser.add_argument("--probe-tokens", type=int, default=32)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--start-token", type=int, default=256)
    parser.add_argument("--alignment-lookahead-tokens", type=int, default=32)
    parser.add_argument("--entropy-top-k", type=int, default=20)
    parser.add_argument("--entropy-smooth-window", type=int, default=16)
    parser.add_argument("--entropy-reference-window", type=int, default=64)
    parser.add_argument("--entropy-candidate-min-drop", type=float, default=0.10)
    parser.add_argument("--candidate-min-gap", type=int, default=32)
    parser.add_argument("--max-candidate-probes", type=int, default=128)
    return parser.parse_args()


def char_to_token_position(offsets: list[tuple[int, int]], char_offset: int) -> int:
    for index, (_, end) in enumerate(offsets, start=1):
        if end >= char_offset:
            return index
    return len(offsets)


def step_boundaries(text: str, offsets: list[tuple[int, int]]) -> list[int]:
    positions = {
        char_to_token_position(offsets, match.end())
        for match in STEP_BOUNDARY.finditer(text)
    }
    return sorted(position for position in positions if position > 0)


def align_position(
    position: int,
    boundaries: list[int],
    *,
    lookahead_tokens: int,
) -> int:
    for boundary in boundaries:
        if position <= boundary <= position + lookahead_tokens:
            return boundary
    return position


def add_marker_events(
    events: dict[int, dict[str, Any]],
    *,
    text: str,
    offsets: list[tuple[int, int]],
    boundaries: list[int],
    patterns: Iterable[str],
    trigger_type: str,
    marker_profiles: tuple[str, ...] = (),
    lookahead_tokens: int,
) -> None:
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            raw_position = char_to_token_position(offsets, match.end())
            position = align_position(
                raw_position,
                boundaries,
                lookahead_tokens=lookahead_tokens,
            )
            event = events.setdefault(
                position,
                {
                    "trigger_types": [],
                    "marker_profiles": [],
                    "matched_markers": [],
                },
            )
            if trigger_type not in event["trigger_types"]:
                event["trigger_types"].append(trigger_type)
            for profile in marker_profiles:
                if profile not in event["marker_profiles"]:
                    event["marker_profiles"].append(profile)
            marker = match.group(0).strip()
            if marker and marker not in event["matched_markers"]:
                event["matched_markers"].append(marker)


def normalized_topk_entropy(top_logprobs: Mapping[str, float] | None) -> float:
    if not top_logprobs:
        return 1.0
    probabilities = [
        math.exp(float(log_probability))
        for log_probability in top_logprobs.values()
        if log_probability is not None
    ]
    observed = min(1.0, sum(probabilities))
    residual = max(0.0, 1.0 - observed)
    masses = probabilities + ([residual] if residual > 1e-12 else [])
    entropy = -sum(mass * math.log(mass) for mass in masses if mass > 0)
    maximum = math.log(max(2, len(masses)))
    return min(1.0, entropy / maximum) if maximum else 0.0


def entropy_events(
    entropies: list[float],
    boundaries: list[int],
    *,
    smooth_window: int,
    reference_window: int,
    minimum_drop: float,
) -> dict[int, dict[str, float]]:
    events: dict[int, dict[str, float]] = {}
    for position in boundaries:
        end = min(position, len(entropies))
        current_start = end - smooth_window
        reference_start = current_start - reference_window
        if reference_start < 0:
            continue
        current = entropies[current_start:end]
        reference = entropies[reference_start:current_start]
        if not current or not reference:
            continue
        current_mean = statistics.fmean(current)
        reference_mean = statistics.fmean(reference)
        drop = reference_mean - current_mean
        reference_std = statistics.pstdev(reference)
        z_score = drop / max(reference_std, 1e-6)
        if drop >= minimum_drop:
            events[position] = {
                "entropy_value": current_mean,
                "entropy_reference": reference_mean,
                "entropy_drop": drop,
                "entropy_z": z_score,
            }
    return events


class AdaptiveProbeCollector:
    def __init__(self, args: argparse.Namespace, main_manifest: dict[str, Any]):
        from clients import apply_chat_template
        from dynasor.core.entropy import obtain_answer
        from dynasor.core.evaluator import strip_string
        from transformers import AutoTokenizer

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
            timeout=900,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model, use_fast=True
        )
        self.output = args.output
        self.probe_dir = self.output / "probes"
        self.probe_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.settings = {
            "collection_schema": "governor-v2-adaptive-probe-1",
            "main_run": str(args.main_run),
            "dense_probe_bank": (
                str(args.dense_probe_bank)
                if args.dense_probe_bank is not None
                else None
            ),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "probe_style": "simple",
            "probe_tokens": args.probe_tokens,
            "start_token": args.start_token,
            "alignment": "next_step_boundary",
            "alignment_lookahead_tokens": args.alignment_lookahead_tokens,
            "trigger_types": [
                "conclusion_marker",
                "entropy_drop",
                "reflection_transition",
                "answer_candidate",
            ],
            "entropy_metric": "teacher_forced_topk_entropy",
            "entropy_top_k": args.entropy_top_k,
            "entropy_smooth_window_tokens": args.entropy_smooth_window,
            "entropy_reference_window_tokens": args.entropy_reference_window,
            "entropy_candidate_min_drop": args.entropy_candidate_min_drop,
            "candidate_min_gap": args.candidate_min_gap,
            "max_candidate_probes": args.max_candidate_probes,
            "periodic_fallback_source": "dense_simple32",
        }
        self._initialize_manifest()

    def _initialize_manifest(self) -> None:
        path = self.output / "probe_manifest.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("probe_settings") != self.settings:
                raise ValueError("existing adaptive output has different settings")
            return
        atomic_write_json(
            path,
            {
                "schema_version": "governor-v2-adaptive-probe-run-1",
                "probe_settings": self.settings,
                "api_key_recorded": False,
            },
        )

    def request(self, **kwargs: Any):
        last_error = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                response = self.client.completions.create(**kwargs)
                return response, time.perf_counter() - started
            except Exception as error:
                last_error = error
                time.sleep(5 * (attempt + 1))
        raise last_error

    def score_entropy(
        self, chat: str, full_text: str, output_token_count: int
    ) -> tuple[list[float], float]:
        response, latency = self.request(
            model=self.model,
            prompt=chat + full_text,
            # vLLM's OpenAI-compatible endpoint requires at least one decode
            # token.  echo=True returns prompt logprobs; the extra token is
            # discarded and never enters the frozen trajectory.
            max_tokens=1,
            temperature=0.0,
            top_p=1.0,
            echo=True,
            logprobs=self.args.entropy_top_k,
            seed=self.base_seed,
            stream=False,
        )
        logprobs = response.choices[0].logprobs
        if logprobs is None:
            raise ValueError(
                "entropy scoring returned no logprobs; start vLLM with "
                "prompt logprobs enabled"
            )
        top_values = list(logprobs.top_logprobs or [])
        offsets = list(logprobs.text_offset or [])
        selected: list[Mapping[str, float] | None]
        if offsets and len(offsets) == len(top_values):
            selected = [
                value
                for offset, value in zip(offsets, top_values)
                if len(chat) <= int(offset) < len(chat) + len(full_text)
            ]
        else:
            # The final value belongs to the one throw-away decode token.
            selected = top_values[-(output_token_count + 1) : -1]
        entropies = [normalized_topk_entropy(value) for value in selected]
        if len(entropies) < output_token_count:
            entropies = [1.0] * (output_token_count - len(entropies)) + entropies
        return entropies[:output_token_count], latency

    def complete_probe(self, prompt: str):
        return self.request(
            model=self.model,
            prompt=prompt,
            max_tokens=self.args.probe_tokens,
            temperature=float(self.main_settings["temperature"]),
            top_p=float(self.main_settings["top_p"]),
            seed=self.base_seed,
            stop=["\\]"],
            stream=False,
        )

    def candidate_events(
        self, text: str, offsets: list[tuple[int, int]], entropies: list[float]
    ) -> dict[int, dict[str, Any]]:
        boundaries = step_boundaries(text, offsets)
        events: dict[int, dict[str, Any]] = {}
        add_marker_events(
            events,
            text=text,
            offsets=offsets,
            boundaries=boundaries,
            patterns=CONCLUSION_STRICT,
            trigger_type="conclusion_marker",
            marker_profiles=("conclusion_strict",),
            lookahead_tokens=self.args.alignment_lookahead_tokens,
        )
        add_marker_events(
            events,
            text=text,
            offsets=offsets,
            boundaries=boundaries,
            patterns=REFLECTION_TRANSITIONS,
            trigger_type="reflection_transition",
            lookahead_tokens=self.args.alignment_lookahead_tokens,
        )
        add_marker_events(
            events,
            text=text,
            offsets=offsets,
            boundaries=boundaries,
            patterns=ANSWER_CANDIDATES,
            trigger_type="answer_candidate",
            lookahead_tokens=self.args.alignment_lookahead_tokens,
        )
        for position, metrics in entropy_events(
            entropies,
            boundaries,
            smooth_window=self.args.entropy_smooth_window,
            reference_window=self.args.entropy_reference_window,
            minimum_drop=self.args.entropy_candidate_min_drop,
        ).items():
            event = events.setdefault(
                position,
                {
                    "trigger_types": [],
                    "marker_profiles": [],
                    "matched_markers": [],
                },
            )
            if "entropy_drop" not in event["trigger_types"]:
                event["trigger_types"].append("entropy_drop")
            event.update(metrics)
        return events

    def collect(self, trajectory_path: Path) -> int:
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        output_path = self.probe_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            return problem_id
        encoded = self.tokenizer(
            trajectory["full_text"],
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
        token_ids = list(encoded["input_ids"])
        offsets = [tuple(pair) for pair in encoded["offset_mapping"]]
        chat = self.apply_chat_template(
            str(trajectory["problem"]).strip(), self.model
        )
        entropies, entropy_latency = self.score_entropy(
            chat, trajectory["full_text"], len(token_ids)
        )
        events = self.candidate_events(
            trajectory["full_text"], offsets, entropies
        )
        inclusive_end = len(token_ids) + (
            0 if bool(trajectory["finished_naturally"]) else 1
        )
        positions = [
            position
            for position in sorted(events)
            if self.args.start_token <= position < inclusive_end
        ]
        thinned = []
        for position in positions:
            if (
                thinned
                and position - thinned[-1] < self.args.candidate_min_gap
            ):
                previous = events[thinned[-1]]
                current = events[position]
                for key in ("trigger_types", "marker_profiles", "matched_markers"):
                    previous[key] = list(
                        dict.fromkeys(previous.get(key, []) + current.get(key, []))
                    )
                if current.get("entropy_drop", 0.0) > previous.get(
                    "entropy_drop", 0.0
                ):
                    for key in (
                        "entropy_value",
                        "entropy_reference",
                        "entropy_drop",
                        "entropy_z",
                    ):
                        if key in current:
                            previous[key] = current[key]
                continue
            thinned.append(position)
        positions = thinned[: self.args.max_candidate_probes]
        dense_records: dict[int, dict[str, Any]] = {}
        if self.args.dense_probe_bank is not None:
            dense_path = (
                self.args.dense_probe_bank
                / "probes"
                / f"problem_{problem_id}.json"
            )
            if not dense_path.exists():
                raise FileNotFoundError(
                    f"dense probe bank is incomplete: {dense_path}"
                )
            dense_payload = json.loads(
                dense_path.read_text(encoding="utf-8")
            )
            dense_records = {
                int(record["token_position"]): dict(record)
                for record in dense_payload.get("probes", [])
            }
        records = []
        for probe_id, position in enumerate(positions, start=1):
            if position in dense_records:
                record = dict(dense_records[position])
                record.update(
                    {
                        "probe_id": probe_id,
                        "reused_from": "dense_simple32",
                        **events[position],
                    }
                )
            else:
                prefix = self.tokenizer.decode(token_ids[:position])
                response, latency = self.complete_probe(
                    chat + prefix + SIMPLE_SUFFIX
                )
                probe_text = str(response.choices[0].text)
                answer = self.obtain_answer(probe_text)
                answer = self.strip_string(answer) if answer else ""
                record = {
                    "token_position": position,
                    "probe_id": probe_id,
                    "probe_answer": answer,
                    "is_certain": not any(
                        word in probe_text.lower()
                        for word in UNCERTAIN_WORDS
                    ),
                    "probe_out_tokens": int(response.usage.completion_tokens),
                    "probe_prompt_tokens": int(response.usage.prompt_tokens),
                    "probe_latency_seconds": latency,
                    **events[position],
                }
            records.append(record)
        payload = {
            "schema_version": "governor-v2-adaptive-probe-trajectory-1",
            "problem_id": problem_id,
            "dataset": self.dataset,
            "model": self.model,
            "base_seed": self.base_seed,
            "main_token_count_recorded": trajectory["tokens_used"],
            "main_token_count_reencoded": len(token_ids),
            "entropy_scoring_latency_seconds": entropy_latency,
            "candidate_positions_before_thinning": len(events),
            "candidate_positions_probed": len(records),
            "probes": records,
        }
        with self.lock:
            atomic_write_json(output_path, payload)
        return problem_id


def trajectory_paths(main_run: Path) -> Iterable[Path]:
    return sorted((main_run / "traj").glob("problem_*.json"))


def main() -> None:
    args = parse_args()
    manifest = json.loads(
        (args.main_run / "run_manifest.json").read_text(encoding="utf-8")
    )
    collector = AdaptiveProbeCollector(args, manifest)
    paths = list(trajectory_paths(args.main_run))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collector.collect, path) for path in paths]
        for index, future in enumerate(as_completed(futures), start=1):
            problem_id = future.result()
            print(f"[{index}/{len(paths)}] problem {problem_id}", flush=True)


if __name__ == "__main__":
    main()
