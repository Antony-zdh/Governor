"""Stage 8 §6.6 -- paired re-probe 2×2 on the existing 500 simple trajectories.

Adapted from run_probe_variants.py with the three §6.6.4 fixes:
  1. probe input = apply_chat_template(problem) + prefix + suffix  (Stage 8's
     build_prompt dropped the chat prompt -> could not reproduce simple answers).
  2. suffix = PROBE_SUFFIXES[suffix] verbatim from logging_run.py; is_certain and
     answer parsed exactly like logging_run.py (§6.6.4-4); probe seed fixed 42.
  3. prefix reconstruction reuses run_probe_variants token slicing:
     ids = tokenizer.encode(full_text, add_special_tokens=False);
     prefix = tokenizer.decode(ids[:token_position]).

Grid: probe_suffix ∈ {simple, certaindex} × probe_tokens ∈ {10, 32}.
  - 10: verbatim Stage 1 (no stop sequence) -- the anchor.
  - 32: adds vLLM stop sequence "\]" so short answers self-terminate and long
    answers (vectors/intervals/equations) fit without ballooning cost.

No main reasoning is re-run -- only the short probe call at every existing
checkpoint of results/stage1_logging. Resumable per (problem, variant).

Output: results/probe_paired_2x2/
    traj/problem_<id>.json   one per problem, holds all requested variants
    reprobe_paired.csv        flat: problem_id, probe_id, token_position,
                              suffix, probe_tokens, probe_answer, is_certain,
                              probe_out_tokens, ...
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))  # .../FalseConsensus/probe_compare
sys.path.insert(0, os.path.join(_HERE, "..", "..", "TokenDeprivation"))  # benchmark/TokenDeprivation
sys.path.insert(0, os.path.join(_HERE, ".."))  # FalseConsensus (logging_run, analyze)
from clients import apply_chat_template  # noqa: E402
from dynasor.core.entropy import obtain_answer  # noqa: E402
from dynasor.core.evaluator import strip_string  # noqa: E402

# Verbatim from logging_run.py (kept in sync intentionally; do not diverge).
PROBE_SUFFIXES = {
    "simple": "**Final Answer**\n\n\\[ \\boxed{",
    "certaindex": "... Oh, I suddenly got the answer to the whole problem, **Final Answer**\n\n\\[ \\boxed{",
}
UNCERTAIN_WORDS = ["wait", "hold", "but", "okay", "no", "hmm"]
# display-math close that follows \boxed{...}; stop short answers at 32-token budget.
STOP_SEQ_32 = ["\\]"]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
    p.add_argument("--url", default="http://localhost:8000/v1")
    p.add_argument("--api-key", default="token-abc123")
    p.add_argument("--probe-suffix", choices=list(PROBE_SUFFIXES.keys()), required=True)
    p.add_argument("--probe-tokens", type=int, choices=[10, 32], required=True)
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--stage1-dir", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage1_logging"))
    p.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "..", "results", "probe_paired_2x2"))
    p.add_argument("--limit", type=int, default=None, help="only first N problems (validation)")
    p.add_argument("--flatten-only", action="store_true")
    return p.parse_args()


class Runner:
    def __init__(self, args):
        self.args = args
        self.suffix = PROBE_SUFFIXES[args.probe_suffix]
        self.stop = STOP_SEQ_32 if args.probe_tokens == 32 else None
        self.client = openai.OpenAI(api_key=args.api_key, base_url=args.url, timeout=600)

    def complete(self, prompt):
        """One probe completion; matches logging_run.probe call (temp/top_p/seed)."""
        last_err = None
        for attempt in range(4):
            try:
                resp = self.client.completions.create(
                    model=self.args.model,
                    prompt=prompt,
                    max_tokens=self.args.probe_tokens,
                    temperature=self.args.temperature,
                    top_p=self.args.top_p,
                    seed=self.args.seed,
                    stop=self.stop,
                    stream=False,
                )
                return resp.choices[0].text, int(resp.usage.completion_tokens)
            except Exception as e:
                last_err = e
                time.sleep(5 * (attempt + 1))
        raise last_err


def get_checkpoints(pid, probes_df, traj, tokenizer, tok_cache):
    rows = probes_df[probes_df["problem_id"] == pid].sort_values("probe_id")
    if pid not in tok_cache:
        tok_cache[pid] = tokenizer.encode(traj["full_text"], add_special_tokens=False)
    ids = tok_cache[pid]
    out = []
    for _, r in rows.iterrows():
        tok_pos = int(r["token_position"])
        prefix = tokenizer.decode(ids[: min(tok_pos, len(ids))])
        out.append({"probe_id": int(r["probe_id"]), "token_position": tok_pos, "prefix": prefix})
    return out


def run_variant_for_problem(pid, problem, checkpoints, runner, args):
    """Probe every checkpoint with this variant. Returns list of result rows."""
    chat = apply_chat_template(problem.strip(), args.model)
    rows = []
    for cp in checkpoints:
        prompt = chat + cp["prefix"] + runner.suffix
        probe_text, out_tokens = runner.complete(prompt)
        answer = strip_string(obtain_answer(probe_text))
        is_certain = not any(w in probe_text.lower() for w in UNCERTAIN_WORDS)
        rows.append({
            "probe_id": cp["probe_id"],
            "token_position": cp["token_position"],
            "suffix": args.probe_suffix,
            "probe_tokens": args.probe_tokens,
            "probe_answer": answer,
            "is_certain": is_certain,
            "probe_out_tokens": out_tokens,
            "raw_probe_text": probe_text,
        })
    return rows


def flatten(variant_dir, out_csv):
    rows = []
    for fn in sorted(os.listdir(variant_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(variant_dir, fn), encoding="utf-8") as f:
            data = json.load(f)
        pid = data["problem_id"]
        for vkey, results in data.get("by_variant", {}).items():
            for r in results:
                rows.append({"problem_id": pid, "variant": vkey, **{k: v for k, v in r.items() if k != "raw_probe_text"}})
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    return df


def main():
    args = parse_args()
    variant_dir = os.path.join(args.output, "traj")
    os.makedirs(variant_dir, exist_ok=True)
    vkey = f"{args.probe_suffix}__{args.probe_tokens}"

    if args.flatten_only:
        df = flatten(variant_dir, os.path.join(args.output, "reprobe_paired.csv"))
        print(f"Flattened {len(df)} rows -> reprobe_paired.csv")
        return

    print(f"Loading tokenizer {args.model} ...")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    probes_df = pd.read_csv(os.path.join(args.stage1_dir, "probes.csv"), keep_default_na=False)
    # problem_id order in stage1 probes.csv; subset by first N if --limit
    pids = sorted(int(x) for x in probes_df["problem_id"].unique())
    if args.limit:
        pids = pids[: args.limit]

    runner = Runner(args)
    tok_cache = {}
    lock = threading.Lock()

    # Build todo: problems whose json is missing this variant (or incomplete).
    todo = []
    for pid in pids:
        traj_path = os.path.join(args.stage1_dir, "traj", f"problem_{pid}.json")
        with open(traj_path, encoding="utf-8") as f:
            traj = json.load(f)
        out_path = os.path.join(variant_dir, f"problem_{pid}.json")
        existing = {}
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                existing = json.load(f)
        cps = get_checkpoints(pid, probes_df, traj, tokenizer, tok_cache)
        already = existing.get("by_variant", {}).get(vkey)
        if already and len(already) == len(cps):
            continue  # this variant fully done for this problem
        todo.append((pid, traj["problem"], cps, existing, out_path))

    print(f"Variant {vkey}: running {len(todo)} problems x {len(args.probe_suffix)} -> {args.output}")

    def work(pid, problem, cps, existing, out_path):
        rows = run_variant_for_problem(pid, problem, cps, runner, args)
        existing.setdefault("by_variant", {})[vkey] = rows
        existing["problem_id"] = int(pid)
        existing["problem"] = problem
        with lock:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        return pid, len(rows)

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, *t) for t in todo]
        for fut in as_completed(futures):
            pid, n = fut.result()
            done += 1
            print(f"[{done}/{len(todo)}] problem {pid}: {n} probes ({time.time() - t0:.0f}s)", flush=True)

    df = flatten(variant_dir, os.path.join(args.output, "reprobe_paired.csv"))
    print(f"Done. Flattened {len(df)} rows -> reprobe_paired.csv")


if __name__ == "__main__":
    main()
