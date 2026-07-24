"""Stage 9 §7 -- within-problem K-rollout (same problem repeated K times at a
long budget) to disentangle "late consensus is unreliable" from difficulty /
budget truncation confounds.

Adapted from logging_run.py (Run logic verbatim where it matters), with:
  - K rollouts per problem, each a distinct main-reasoning trajectory via
    distinct base seed (1000,2000,...,8000); main gen seed = base + problem_id
    (so rollouts stay pairwise distinct even after the problem_id offset).
  - probe seed FIXED at 42 (Stage-1/Stage-4-comparable readout); variation is
    isolated to the main trajectory, exactly what K-rollout must measure.
  - budget 12288 (needs vLLM --max-model-len >= ~13k), probe interval 128,
    probe simple@10 -- same probe design as Stage 1/4/9.
  - every probe row and traj carries (problem_id, rollout_id).
  - resumable per (problem_id, rollout_id): traj written first; existing traj
    -> skipped. probes.csv is rebuilt (flattened) from all traj files so it is
    always consistent with the on-disk trajectories.

No changes to logging_run.py / analyze.py / dynasor eval logic.
"""

import argparse
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "TokenDeprivation"))  # benchmark/TokenDeprivation
sys.path.insert(0, os.path.join(_HERE, ".."))  # FalseConsensus
from clients import apply_chat_template  # noqa: E402
from utils import load_dataset  # noqa: E402
from dynasor.core.evaluator import extract_answer, math_equal, strip_string  # noqa: E402
from dynasor.core.entropy import obtain_answer  # noqa: E402

# Verbatim from logging_run.py
PROBE_SUFFIXES = {
    "simple": "**Final Answer**\n\n\\[ \\boxed{",
    "certaindex": "... Oh, I suddenly got the answer to the whole problem, **Final Answer**\n\n\\[ \\boxed{",
}
UNCERTAIN_WORDS = ["wait", "hold", "but", "okay", "no", "hmm"]
PROBE_SEED = 42  # fixed, Stage-1-comparable readout

CSV_FIELDS = [
    "problem_id", "rollout_id", "dataset", "token_position", "probe_id",
    "probe_answer", "share", "entropy", "unique_answers", "dominant_answer",
    "is_certain", "reasoning", "finished", "final_answer", "final_correct",
    "base_seed", "main_seed", "tokens_used",
]


def group_answers(answers):
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
        self.client = openai.OpenAI(api_key=args.api_key, base_url=args.url, timeout=900)
        self.suffix = PROBE_SUFFIXES[args.probe_suffix_style]

    def complete(self, prompt, max_tokens, seed):
        last_err = None
        for attempt in range(4):
            try:
                return self.client.completions.create(
                    model=self.args.model, prompt=prompt, max_tokens=max_tokens,
                    temperature=self.args.temperature, top_p=self.args.top_p,
                    seed=seed, stream=False,
                )
            except Exception as e:
                last_err = e
                time.sleep(5 * (attempt + 1))
        raise last_err


def run_rollout(pid, rollout_id, problem, target, base_seed, runner, args):
    """One (problem, rollout) trajectory. main seed = base+pid; probe seed = 42."""
    prompt = apply_chat_template(problem.strip(), args.model)
    main_seed = base_seed + pid
    text = ""
    tokens_used = 0
    finished = False
    probe_answers = []
    traj = {
        "problem_id": pid, "rollout_id": rollout_id, "dataset": args.dataset,
        "problem": problem, "target": target, "base_seed": base_seed,
        "main_seed": main_seed, "probe_seed": PROBE_SEED, "probes": [],
    }
    n_probes = args.budget // args.probe_interval
    for probe_id in range(1, n_probes + 1):
        resp = runner.complete(prompt + text, args.probe_interval, seed=main_seed)
        chunk = resp.choices[0].text
        finish_reason = resp.choices[0].finish_reason
        text += chunk
        tokens_used += resp.usage.completion_tokens
        finished = finish_reason != "length"
        if finished:
            break
        probe_resp = runner.complete(prompt + text + runner.suffix, args.probe_tokens, seed=PROBE_SEED)
        probe_text = probe_resp.choices[0].text
        answer = strip_string(obtain_answer(probe_text))
        is_certain = not any(w in probe_text.lower() for w in UNCERTAIN_WORDS)
        probe_answers.append(answer)
        traj["probes"].append({
            "probe_id": probe_id, "token_position": tokens_used,
            "probe_text": probe_text, "answer": answer,
        })
    if finished:
        final_answer = extract_answer(text, args.dataset)
    else:
        final_answer = probe_answers[-1] if probe_answers else ""
    final_answer = strip_string(final_answer) if final_answer else ""
    final_correct = bool(math_equal(final_answer, target))
    traj.update({
        "full_text": text, "tokens_used": tokens_used,
        "finished_naturally": finished, "final_answer": final_answer,
        "final_correct": final_correct,
    })
    return traj


def flatten(traj_dir, out_csv):
    """Rebuild probes.csv from all traj files. Incremental grouping per traj
    (O(n*unique), not O(n^3)) -- share/entropy/dominant match logging_run."""
    rows = []
    for fn in sorted(os.listdir(traj_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(traj_dir, fn), encoding="utf-8") as f:
            t = json.load(f)
        probes = t["probes"]
        reps, counts = [], []  # incremental answer-equivalence classes
        for k, p in enumerate(probes):
            ans = p["answer"]
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
            share = max(counts) / sum(counts) if counts else 0.0
            rows.append({
                "problem_id": t["problem_id"], "rollout_id": t["rollout_id"],
                "dataset": t["dataset"], "token_position": p["token_position"],
                "probe_id": p["probe_id"], "probe_answer": ans,
                "share": round(share, 4), "entropy": round(normalized_entropy(counts), 4),
                "unique_answers": len(counts), "dominant_answer": dominant,
                "is_certain": not any(w in str(p.get("probe_text", "")).lower() for w in UNCERTAIN_WORDS),
                "reasoning": p.get("probe_text", ""),
                "finished": k == len(probes) - 1 and t["finished_naturally"],
                "final_answer": t["final_answer"], "final_correct": t["final_correct"],
                "base_seed": t["base_seed"], "main_seed": t["main_seed"],
                "tokens_used": t["tokens_used"],
            })
    df = pd.DataFrame(rows, columns=CSV_FIELDS)
    df.to_csv(out_csv, index=False)
    return df


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", choices=["math500", "aime24"], required=True)
    p.add_argument("--model", default="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
    p.add_argument("--url", default="http://localhost:18000/v1")
    p.add_argument("--api-key", default="token-abc123")
    p.add_argument("--budget", type=int, default=12288)
    p.add_argument("--probe-interval", type=int, default=128)
    p.add_argument("--probe-tokens", type=int, default=10)
    p.add_argument("--probe-suffix-style", choices=list(PROBE_SUFFIXES.keys()), default="simple")
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--rollouts", type=int, default=8)
    p.add_argument("--seeds", default="1000,2000,3000,4000,5000,6000,7000,8000")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--output", default=os.path.join(_HERE, "..", "results", "stage9_krollout"))
    p.add_argument("--problems", default=None, help="comma-sep problem_ids; else all of dataset")
    p.add_argument("--flatten-only", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    traj_dir = os.path.join(args.output, "traj")
    os.makedirs(traj_dir, exist_ok=True)
    csv_path = os.path.join(args.output, "probes.csv")

    if args.flatten_only:
        df = flatten(traj_dir, csv_path)
        print(f"Flattened {len(df)} rows -> {csv_path}")
        return

    seeds = [int(s) for s in args.seeds.split(",")]
    assert len(seeds) == args.rollouts, f"--seeds has {len(seeds)} but --rollouts {args.rollouts}"
    data = load_dataset(args.dataset)
    if args.problems:
        pids = [int(x) for x in args.problems.split(",")]
    else:
        pids = list(range(len(data)))

    runner = Runner(args)
    lock = threading.Lock()
    # build todo: (pid, rollout_id, problem, target, base_seed) where traj missing
    todo = []
    for pid in pids:
        item = data[pid]
        problem = item["problem"]
        target = strip_string(item["answer"])
        for r, base in enumerate(seeds):
            tp = os.path.join(traj_dir, f"problem_{pid}__rollout_{r}__{args.dataset}.json")
            if os.path.exists(tp):
                continue
            todo.append((pid, r, problem, target, base, tp))
    print(f"K-rollout {args.dataset}: {len(pids)} problems x {args.rollouts} rollouts; "
          f"{len(todo)} to run (skip {len(pids)*args.rollouts - len(todo)} existing)")

    def work(pid, r, problem, target, base, tp):
        t = run_rollout(pid, r, problem, target, base, runner, args)
        with lock:
            with open(tp, "w", encoding="utf-8") as f:
                json.dump(t, f, ensure_ascii=False, indent=2)
        return pid, r, t["finished_naturally"], t["tokens_used"], t["final_correct"]

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, *t) for t in todo]
        for fut in as_completed(futs):
            pid, r, fin, tok, cor = fut.result()
            done += 1
            print(f"[{done}/{len(todo)}] p{pid} r{r}: finished={fin} tokens={tok} correct={cor} "
                  f"({time.time()-t0:.0f}s)", flush=True)

    df = flatten(traj_dir, csv_path)
    print(f"Done. {len(df)} probe rows -> {csv_path}")


if __name__ == "__main__":
    main()
