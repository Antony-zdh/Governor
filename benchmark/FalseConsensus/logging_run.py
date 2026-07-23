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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "TokenDeprivation"))
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


class Runner:
    def __init__(self, args):
        self.args = args
        self.client = openai.OpenAI(api_key=args.api_key, base_url=args.url, timeout=600)
        self.probe_suffix = PROBE_SUFFIXES[args.probe_suffix_style]
        self.lock = threading.Lock()
        os.makedirs(args.output, exist_ok=True)
        os.makedirs(os.path.join(args.output, "traj"), exist_ok=True)
        self.csv_path = os.path.join(args.output, "probes.csv")
        new_file = not os.path.exists(self.csv_path)
        self.csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.csv_file, fieldnames=CSV_FIELDS)
        if new_file:
            self.writer.writeheader()
            self.csv_file.flush()

    def complete(self, prompt, max_tokens, seed):
        last_err = None
        for attempt in range(4):
            try:
                return self.client.completions.create(
                    model=self.args.model,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=self.args.temperature,
                    top_p=self.args.top_p,
                    seed=seed,
                    stream=False,
                )
            except Exception as e:  # transient server hiccups
                last_err = e
                time.sleep(5 * (attempt + 1))
        raise last_err

    def run_problem(self, problem_id, problem, target):
        args = self.args
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
            "probes": [],
        }

        n_probes = args.budget // args.probe_interval
        for probe_id in range(1, n_probes + 1):
            resp = self.complete(prompt + text, args.probe_interval, seed=args.seed + problem_id)
            chunk = resp.choices[0].text
            finish_reason = resp.choices[0].finish_reason
            text += chunk
            tokens_used += resp.usage.completion_tokens
            finished = finish_reason != "length"

            if finished:
                break

            probe_resp = self.complete(prompt + text + self.probe_suffix, args.probe_tokens, seed=args.seed)
            probe_text = probe_resp.choices[0].text
            answer = strip_string(obtain_answer(probe_text))
            is_certain = not any(w in probe_text.lower() for w in UNCERTAIN_WORDS)
            probe_answers.append(answer)

            counts, dominant = group_answers(probe_answers)
            share = max(counts) / sum(counts)
            rows.append(
                {
                    "problem_id": problem_id,
                    "dataset": args.dataset,
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
                }
            )
            traj["probes"].append(
                {
                    "probe_id": probe_id,
                    "token_position": tokens_used,
                    "probe_text": probe_text,
                    "answer": answer,
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
            }
        )

        with self.lock:
            for row in rows:
                self.writer.writerow(row)
            self.csv_file.flush()
        traj_path = os.path.join(args.output, "traj", f"problem_{problem_id}.json")
        with open(traj_path, "w", encoding="utf-8") as f:
            json.dump(traj, f, ensure_ascii=False, indent=2)
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
        todo.append((problem_id, item["problem"], strip_string(item["answer"])))

    runner = Runner(args)
    print(f"Logging {len(todo)} problems -> {args.output}")
    done = 0
    t0 = time.time()
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
    runner.csv_file.close()
    print("Done. CSV at", runner.csv_path)


if __name__ == "__main__":
    main()
