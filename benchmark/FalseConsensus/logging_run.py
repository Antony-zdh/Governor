"""Stage 1: Logging Mode for the False Consensus project.

Governor does NOT control the model here (no early stop, no upgrade, no
decisions). It only logs every probe along a single reasoning trajectory.

For each problem:
    generate 128 tokens -> probe -> generate 128 tokens -> probe -> ...
until the model finishes naturally or the token budget (3072) is exhausted.

Outputs:
    probes.csv   one row per probe (schema from plan.md)
    traj/problem_<id>.json   full trajectory (prompt, chunks, probe outputs)
"""

import argparse
import csv
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai

import sys

REPO_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
sys.path.insert(0, REPO_DIR)
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "TokenDeprivation")
)
from utils import load_dataset  # noqa: E402
from clients import apply_chat_template  # noqa: E402

from dynasor.core.evaluator import (  # noqa: E402
    extract_answer,
    math_equal,
    strip_string,
)
from dynasor.core.entropy import obtain_answer  # noqa: E402


PROBE_SUFFIXES = {
    "simple": "**Final Answer**\n\n\\[ \\boxed{",
    # original CertaIndex/Dynasor probe wording (dynasor/core/cot.py), kept
    # verbatim for the probe-suffix ablation -- not just the trailing
    # "**Final Answer**\n\n\\[ \\boxed{" part, which is what Stage 1-8 used.
    "certaindex": "... Oh, I suddenly got the answer to the whole problem, **Final Answer**\n\n\\[ \\boxed{",
}
UNCERTAIN_WORDS = ["wait", "hold", "but", "okay", "no", "hmm"]

CSV_FIELDS = [
    "problem_id",
    "dataset",
    "model",
    "base_seed",
    "token_position",
    "probe_id",
    "probe_answer",
    "share",
    "entropy",
    "unique_answers",
    "dominant_answer",
    "is_certain",
    "reasoning",
    "finished",
    "final_answer",
    "final_correct",
    "main_out_tokens",
    "probe_out_tokens",
    "main_prompt_tokens",
    "probe_prompt_tokens",
    "main_latency_seconds",
    "probe_latency_seconds",
]

RUN_SETTING_KEYS = [
    "model",
    "dataset",
    "budget",
    "probe_interval",
    "probe_tokens",
    "probe_suffix_style",
    "temperature",
    "top_p",
    "base_seed",
]


def parse_args():
    p = argparse.ArgumentParser(description="False Consensus Stage 1 logging")
    p.add_argument("--dataset", type=str, default="math500")
    p.add_argument("--model", type=str, default="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
    p.add_argument("--url", type=str, default="http://localhost:8000/v1")
    p.add_argument("--api-key", type=str, default="token-abc123")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=100)
    p.add_argument("--budget", type=int, default=3072, help="max reasoning tokens")
    p.add_argument("--probe-interval", type=int, default=128)
    p.add_argument("--probe-tokens", type=int, default=10)
    p.add_argument("--probe-suffix-style", type=str, default="simple",
                    choices=list(PROBE_SUFFIXES.keys()))
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--output", type=str, default="results/stage1_logging")
    return p.parse_args()


def apply_template(problem: str, model: str) -> str:
    return apply_chat_template(problem, model)


def group_answers(answers):
    """Group probe answers into math-equivalence classes.

    Returns (counts, dominant_answer). Empty answers form their own class.
    """
    reps, counts = [], []
    for ans in answers:
        placed = False
        for i, rep in enumerate(reps):
            same = (ans == rep) if (ans == "" or rep == "") else math_equal(ans, rep)
            if same:
                counts[i] += 1
                placed = True
                break
        if not placed:
            reps.append(ans)
            counts.append(1)
    dominant = reps[max(range(len(reps)), key=lambda i: counts[i])]
    return counts, dominant


def normalized_entropy(counts):
    n = sum(counts)
    if n <= 1 or len(counts) == 1:
        return 0.0
    probs = [c / n for c in counts]
    h = -sum(p * math.log(p, 2) for p in probs)
    return h / math.log(n, 2)


def expected_run_settings(args):
    return {
        "model": args.model,
        "dataset": args.dataset,
        "budget": args.budget,
        "probe_interval": args.probe_interval,
        "probe_tokens": args.probe_tokens,
        "probe_suffix_style": args.probe_suffix_style,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "base_seed": args.seed,
    }


def validate_run_settings(actual, expected, source):
    mismatches = {
        key: {"expected": expected[key], "actual": actual.get(key)}
        for key in RUN_SETTING_KEYS
        if actual.get(key) != expected[key]
    }
    if mismatches:
        raise ValueError(
            f"{source} does not match the requested run settings: "
            f"{json.dumps(mismatches, sort_keys=True)}"
        )


def csv_rows_from_trajectory(traj):
    answers = []
    rows = []
    settings = traj.get("run_settings", {})
    for record in sorted(traj.get("probes", []), key=lambda item: item["probe_id"]):
        answer = str(record.get("answer", ""))
        probe_text = str(record.get("probe_text", ""))
        answers.append(answer)
        counts, dominant = group_answers(answers)
        rows.append(
            {
                "problem_id": traj["problem_id"],
                "dataset": traj["dataset"],
                "model": settings.get("model", ""),
                "base_seed": settings.get("base_seed", ""),
                "token_position": record["token_position"],
                "probe_id": record["probe_id"],
                "probe_answer": answer,
                "share": round(max(counts) / sum(counts), 4),
                "entropy": round(normalized_entropy(counts), 4),
                "unique_answers": len(counts),
                "dominant_answer": dominant,
                "is_certain": not any(
                    word in probe_text.lower() for word in UNCERTAIN_WORDS
                ),
                "reasoning": probe_text,
                "finished": False,
                "final_answer": traj.get("final_answer", ""),
                "final_correct": bool(traj.get("final_correct", False)),
                "main_out_tokens": record.get("main_out_tokens", ""),
                "probe_out_tokens": record.get("probe_out_tokens", ""),
                "main_prompt_tokens": record.get("main_prompt_tokens", ""),
                "probe_prompt_tokens": record.get("probe_prompt_tokens", ""),
                "main_latency_seconds": record.get(
                    "main_latency_seconds", ""
                ),
                "probe_latency_seconds": record.get(
                    "probe_latency_seconds", ""
                ),
            }
        )
    return rows


class Runner:
    def __init__(self, args):
        self.args = args
        self.run_settings = expected_run_settings(args)
        self.client = openai.OpenAI(api_key=args.api_key, base_url=args.url, timeout=600)
        self.probe_suffix = PROBE_SUFFIXES[args.probe_suffix_style]
        self.lock = threading.Lock()
        os.makedirs(args.output, exist_ok=True)
        os.makedirs(os.path.join(args.output, "traj"), exist_ok=True)
        self.manifest_path = os.path.join(args.output, "run_manifest.json")
        self._initialize_manifest()
        self.csv_path = os.path.join(args.output, "probes.csv")
        self.rebuild_csv_from_trajectories()
        self.csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(
            self.csv_file, fieldnames=CSV_FIELDS, lineterminator="\n"
        )

    def _trajectory_paths(self):
        traj_dir = os.path.join(self.args.output, "traj")
        return sorted(
            (
                path
                for path in os.listdir(traj_dir)
                if path.startswith("problem_") and path.endswith(".json")
            ),
            key=lambda path: int(path.removeprefix("problem_").removesuffix(".json")),
        )

    def _load_and_validate_trajectory(self, filename):
        path = os.path.join(self.args.output, "traj", filename)
        with open(path, encoding="utf-8") as handle:
            traj = json.load(handle)
        expected_id = int(
            filename.removeprefix("problem_").removesuffix(".json")
        )
        if int(traj.get("problem_id", -1)) != expected_id:
            raise ValueError(
                f"{path} has problem_id={traj.get('problem_id')}, "
                f"expected {expected_id}"
            )
        if traj.get("dataset") != self.args.dataset:
            raise ValueError(
                f"{path} has dataset={traj.get('dataset')}, "
                f"expected {self.args.dataset}"
            )
        validate_run_settings(
            traj.get("run_settings", {}), self.run_settings, path
        )
        return traj

    def _initialize_manifest(self):
        manifest = {
            "format_version": 1,
            "run_settings": self.run_settings,
            "problem_id_range": {
                "start": self.args.start,
                "end_exclusive": self.args.end,
            },
        }
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, encoding="utf-8") as handle:
                existing = json.load(handle)
            validate_run_settings(
                existing.get("run_settings", {}),
                self.run_settings,
                self.manifest_path,
            )
            if existing.get("problem_id_range") != manifest["problem_id_range"]:
                raise ValueError(
                    f"{self.manifest_path} problem range does not match the "
                    "requested run"
                )
            return
        for filename in self._trajectory_paths():
            self._load_and_validate_trajectory(filename)
        temporary = self.manifest_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, self.manifest_path)

    def rebuild_csv_from_trajectories(self):
        trajectories = self._trajectory_paths()
        if os.path.exists(self.csv_path) and not trajectories:
            with open(self.csv_path, newline="", encoding="utf-8") as handle:
                if any(csv.DictReader(handle)):
                    raise ValueError(
                        f"{self.csv_path} contains rows but no completed "
                        "trajectory files; use a new output directory"
                    )
        if trajectories and self._csv_matches_trajectories(trajectories):
            return
        temporary = self.csv_path + ".tmp"
        with open(temporary, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=CSV_FIELDS, lineterminator="\n"
            )
            writer.writeheader()
            for filename in trajectories:
                writer.writerows(
                    csv_rows_from_trajectory(
                        self._load_and_validate_trajectory(filename)
                    )
                )
        os.replace(temporary, self.csv_path)

    def _csv_matches_trajectories(self, trajectories):
        if not os.path.exists(self.csv_path):
            return False
        with open(self.csv_path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != CSV_FIELDS:
                return False
            observed = []
            for row in reader:
                try:
                    observed.append(
                        (int(row["problem_id"]), int(row["probe_id"]))
                    )
                except (KeyError, TypeError, ValueError):
                    return False
        if len(observed) != len(set(observed)):
            return False
        expected = set()
        for filename in trajectories:
            traj = self._load_and_validate_trajectory(filename)
            expected.update(
                (int(traj["problem_id"]), int(record["probe_id"]))
                for record in traj.get("probes", [])
            )
        return set(observed) == expected

    def close(self):
        self.csv_file.close()

    def complete(self, prompt, max_tokens, seed):
        last_err = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                response = self.client.completions.create(
                    model=self.args.model,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=self.args.temperature,
                    top_p=self.args.top_p,
                    seed=seed,
                    stream=False,
                )
                return response, time.perf_counter() - started
            except Exception as e:  # transient server hiccups
                last_err = e
                time.sleep(5 * (attempt + 1))
        raise last_err

    def run_problem(self, problem_id, problem, target, metadata):
        args = self.args
        problem_started = time.perf_counter()
        prompt = apply_template(problem.strip(), args.model)
        text = ""
        tokens_used = 0
        finished = False
        probe_answers = []
        rows = []
        traj = {
            "problem_id": problem_id,
            "dataset": args.dataset,
            "problem": problem,
            "target": target,
            "level": metadata.get("level", 0),
            "subject": metadata.get("subject", args.dataset),
            "unique_id": metadata.get("unique_id"),
            "probes": [],
        }
        accounting = {
            "main_decode_tokens": 0,
            "probe_decode_tokens": 0,
            "main_prompt_tokens": 0,
            "probe_prompt_tokens": 0,
            "main_calls": 0,
            "probe_calls": 0,
            "main_wall_clock_seconds": 0.0,
            "probe_wall_clock_seconds": 0.0,
        }

        n_probes = args.budget // args.probe_interval
        for probe_id in range(1, n_probes + 1):
            resp, main_latency = self.complete(
                prompt + text, args.probe_interval, seed=args.seed + problem_id
            )
            chunk = resp.choices[0].text
            finish_reason = resp.choices[0].finish_reason
            main_out_tokens = int(resp.usage.completion_tokens)
            main_prompt_tokens = int(resp.usage.prompt_tokens)
            text += chunk
            tokens_used += main_out_tokens
            accounting["main_decode_tokens"] += main_out_tokens
            accounting["main_prompt_tokens"] += main_prompt_tokens
            accounting["main_calls"] += 1
            accounting["main_wall_clock_seconds"] += main_latency
            finished = finish_reason != "length"

            if finished:
                break

            probe_resp, probe_latency = self.complete(
                prompt + text + self.probe_suffix,
                args.probe_tokens,
                seed=args.seed,
            )
            probe_text = probe_resp.choices[0].text
            probe_out_tokens = int(probe_resp.usage.completion_tokens)
            probe_prompt_tokens = int(probe_resp.usage.prompt_tokens)
            accounting["probe_decode_tokens"] += probe_out_tokens
            accounting["probe_prompt_tokens"] += probe_prompt_tokens
            accounting["probe_calls"] += 1
            accounting["probe_wall_clock_seconds"] += probe_latency
            answer = strip_string(obtain_answer(probe_text))
            is_certain = not any(w in probe_text.lower() for w in UNCERTAIN_WORDS)
            probe_answers.append(answer)

            counts, dominant = group_answers(probe_answers)
            share = max(counts) / sum(counts)
            rows.append(
                {
                    "problem_id": problem_id,
                    "dataset": args.dataset,
                    "model": args.model,
                    "base_seed": args.seed,
                    "token_position": tokens_used,
                    "probe_id": probe_id,
                    "probe_answer": answer,
                    "share": round(share, 4),
                    "entropy": round(normalized_entropy(counts), 4),
                    "unique_answers": len(counts),
                    "dominant_answer": dominant,
                    "is_certain": is_certain,
                    "reasoning": probe_text,
                    "finished": False,
                    "main_out_tokens": main_out_tokens,
                    "probe_out_tokens": probe_out_tokens,
                    "main_prompt_tokens": main_prompt_tokens,
                    "probe_prompt_tokens": probe_prompt_tokens,
                    "main_latency_seconds": round(main_latency, 6),
                    "probe_latency_seconds": round(probe_latency, 6),
                }
            )
            traj["probes"].append(
                {
                    "probe_id": probe_id,
                    "token_position": tokens_used,
                    "probe_text": probe_text,
                    "answer": answer,
                    "main_out_tokens": main_out_tokens,
                    "probe_out_tokens": probe_out_tokens,
                    "main_prompt_tokens": main_prompt_tokens,
                    "probe_prompt_tokens": probe_prompt_tokens,
                    "main_latency_seconds": main_latency,
                    "probe_latency_seconds": probe_latency,
                }
            )

        # Final answer: extracted from the full text if the model finished
        # naturally, otherwise the answer of the last probe (budget boundary).
        if finished:
            final_answer = extract_answer(text, args.dataset)
        else:
            final_answer = probe_answers[-1] if probe_answers else ""
        final_answer = strip_string(final_answer) if final_answer else ""
        final_correct = bool(math_equal(final_answer, target))

        for row in rows:
            row["final_answer"] = final_answer
            row["final_correct"] = final_correct
        traj.update(
            {
                "full_text": text,
                "tokens_used": tokens_used,
                "finished_naturally": finished,
                "final_answer": final_answer,
                "final_correct": final_correct,
                "accounting": {
                    **accounting,
                    "trajectory_wall_clock_seconds": (
                        time.perf_counter() - problem_started
                    ),
                },
                "run_settings": {
                    **self.run_settings,
                    "main_seed": args.seed + problem_id,
                    "probe_seed": args.seed,
                },
            }
        )

        traj_path = os.path.join(args.output, "traj", f"problem_{problem_id}.json")
        temporary_path = traj_path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as f:
            json.dump(traj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporary_path, traj_path)
        with self.lock:
            for row in rows:
                self.writer.writerow(row)
            self.csv_file.flush()
        return problem_id, final_correct, tokens_used, len(rows)


def main():
    args = parse_args()
    data = load_dataset(args.dataset)
    todo = []
    for problem_id, item in enumerate(data):
        if problem_id < args.start or problem_id >= args.end:
            continue
        traj_path = os.path.join(args.output, "traj", f"problem_{problem_id}.json")
        if os.path.exists(traj_path):
            print(f"[skip] problem {problem_id} already logged")
            continue
        todo.append(
            (
                problem_id,
                item["problem"],
                strip_string(item["answer"]),
                {
                    "level": item.get("level", 0),
                    "subject": item.get("subject", args.dataset),
                    "unique_id": item.get("unique_id"),
                },
            )
        )

    runner = Runner(args)
    print(f"Logging {len(todo)} problems -> {args.output}")
    done = 0
    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(runner.run_problem, *t) for t in todo]
            for fut in as_completed(futures):
                problem_id, correct, tokens, n_probes = fut.result()
                done += 1
                print(
                    f"[{done}/{len(todo)}] problem {problem_id}: "
                    f"correct={correct} tokens={tokens} probes={n_probes} "
                    f"({time.time() - t0:.0f}s elapsed)",
                    flush=True,
                )
    finally:
        runner.close()
    print("Done. CSV at", runner.csv_path)


if __name__ == "__main__":
    main()
