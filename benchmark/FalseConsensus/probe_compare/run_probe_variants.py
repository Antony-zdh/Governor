"""Stage 8 -- Improved Probe Comparison, GPU-dependent data collection
(plan.md SS6).

Requires a LIVE vLLM OpenAI-compatible server serving the same model used
for Stage 1 logging (default deepseek-ai/DeepSeek-R1-Distill-Qwen-7B) --
this script has NOT been run against a real server in this environment
(no GPU here). It has only been exercised with --dry-run, which stubs out
the network call so the rest of the pipeline (subset loading, tokenizer-
based prefix reconstruction, prompt building, parsing, resumability, CSV
flattening) is verified end-to-end.

Consumes:
  - probe_compare/subset.json          (100 problems, from select_subset.py)
  - results/stage1_logging/probes.csv  (existing P0 checkpoints/positions)
  - results/stage1_logging/traj/*.json (full_text to reconstruct prefixes)

Does NOT re-run the main reasoning trajectory -- only the probe call is
reissued at each existing checkpoint, per plan.md SS6.3 ("这样只需重跑
probe，不需重跑主reasoning"). P0 (current 10-token design) is not
regenerated either; join back to probes.csv by (problem_id, probe_id)
when comparing.

New probe designs implemented (plan.md SS6.2), one completion call each
per checkpoint:
  P1_32 / P1_64  -- same "**Final Answer**\\n\\n\\[ \\boxed{" suffix as P0,
                    just a longer token budget (32 / 64 instead of 10)
  P2             -- Answer-or-Unfinished: model must emit <status>
                    unfinished</status> or <status>answer</status> +
                    <answer>...</answer>
  P3             -- Structured Confidence: same shape as P2 but with an
                    extra tentative/confident split instead of one answer
                    state
  P4             -- Prefix-based External Extraction: a *separate*
                    instruction-style query (not a continuation of the
                    reasoning) asking the model to extract the latest
                    explicitly-supported answer from the prefix text, or
                    say UNFINISHED

The exact wording of the P2/P3/P4 prompts is my own concrete instantiation
of plan.md's templates (the plan gives the tag shapes, not literal final
prompt strings) -- documented here, not silently invented elsewhere.

Output: one JSON per problem under <output>/variant_traj/ (skipped if it
already exists, so an interrupted run can resume), then a flattened
<output>/probe_variants.csv covering all problems that have been run.
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dynasor.core.entropy import obtain_answer  # noqa: E402
from dynasor.core.evaluator import strip_string  # noqa: E402

PROBE_SUFFIX = "**Final Answer**\n\n\\[ \\boxed{"

P2_INSTRUCTION = (
    "\n\nGiven the reasoning so far, output exactly one of:\n\n"
    "<status>unfinished</status>\n\nor\n\n"
    "<status>answer</status>\n<answer>...</answer>\n\nOutput:\n"
)

P3_INSTRUCTION = (
    "\n\nGiven the reasoning so far, output exactly one of:\n\n"
    "<status>unfinished</status>\n\nor\n\n"
    "<status>tentative</status>\n<answer>...</answer>\n\nor\n\n"
    "<status>confident</status>\n<answer>...</answer>\n\nOutput:\n"
)

DESIGNS = ["P1_32", "P1_64", "P2", "P3", "P4"]


def build_prompt(design, problem, prefix):
    if design == "P1_32":
        return prefix + PROBE_SUFFIX, 32
    if design == "P1_64":
        return prefix + PROBE_SUFFIX, 64
    if design == "P2":
        return prefix + P2_INSTRUCTION, 40
    if design == "P3":
        return prefix + P3_INSTRUCTION, 50
    if design == "P4":
        prompt = (
            "<｜User｜>Here is a partial solution to a math problem:\n\n"
            f"Problem: {problem}\n\n"
            f"Partial reasoning so far:\n{prefix}\n\n"
            "Extract the latest explicitly supported answer from the reasoning "
            "prefix above. If no explicit answer is supported yet, respond with "
            "exactly: UNFINISHED. Otherwise respond with exactly: "
            "\\boxed{ANSWER}<｜Assistant｜>"
        )
        return prompt, 40
    raise ValueError(design)


def parse_tagged(text, allowed_statuses):
    m_status = re.search(r"<status>\s*(.*?)\s*</status>", text, re.S | re.I)
    m_answer = re.search(r"<answer>\s*(.*?)\s*</answer>", text, re.S | re.I)
    status = ""
    if m_status:
        raw = m_status.group(1).strip().lower()
        for s in allowed_statuses:
            if s in raw:
                status = s
                break
    answer = strip_string(m_answer.group(1).strip()) if (m_answer and m_answer.group(1).strip()) else ""
    parse_ok = bool(status) and (status == "unfinished" or bool(answer))
    return status, answer, parse_ok


def parse_response(design, raw_text):
    if design in ("P1_32", "P1_64"):
        answer = strip_string(obtain_answer(raw_text)) if obtain_answer(raw_text) else ""
        parse_ok = bool(answer)
        status = "answer" if parse_ok else "unfinished"
        return status, answer, parse_ok
    if design == "P2":
        return parse_tagged(raw_text, ["unfinished", "answer"])
    if design == "P3":
        return parse_tagged(raw_text, ["unfinished", "tentative", "confident"])
    if design == "P4":
        if re.search(r"unfinished", raw_text, re.I) and "boxed" not in raw_text.lower():
            return "unfinished", "", True
        if "boxed" in raw_text.lower():
            tail = raw_text.split("boxed", 1)[-1]
            tail = tail[1:] if tail[:1] == "{" else tail
            answer = strip_string(obtain_answer(tail)) if obtain_answer(tail) else ""
            return ("answer", answer, True) if answer else ("", "", False)
        return "", "", False
    raise ValueError(design)


class Runner:
    def __init__(self, args):
        self.args = args
        self.dry_run = args.dry_run
        if not self.dry_run:
            self.client = openai.OpenAI(api_key=args.api_key, base_url=args.url, timeout=600)

    def complete(self, prompt, max_tokens, seed):
        if self.dry_run:
            return "<status>unfinished</status>"
        last_err = None
        for attempt in range(4):
            try:
                resp = self.client.completions.create(
                    model=self.args.model,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=self.args.temperature,
                    top_p=self.args.top_p,
                    seed=seed,
                    stream=False,
                )
                return resp.choices[0].text
            except Exception as e:  # transient server hiccups
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
        prefix_ids = ids[: min(tok_pos, len(ids))]
        prefix = tokenizer.decode(prefix_ids)
        out.append({"probe_id": int(r["probe_id"]), "token_position": tok_pos, "prefix": prefix})
    return out


def process_problem(pid, problem, checkpoints, runner, args):
    results = []
    for cp in checkpoints:
        for design in DESIGNS:
            prompt, max_tokens = build_prompt(design, problem, cp["prefix"])
            raw = runner.complete(prompt, max_tokens, seed=args.seed)
            status, answer, parse_ok = parse_response(design, raw)
            results.append(
                {
                    "probe_id": cp["probe_id"],
                    "token_position": cp["token_position"],
                    "design": design,
                    "raw_output": raw,
                    "status": status,
                    "answer": answer,
                    "parse_ok": parse_ok,
                }
            )
    return results


def flatten_to_csv(variant_dir, out_csv):
    rows = []
    for fn in sorted(os.listdir(variant_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(variant_dir, fn), encoding="utf-8") as f:
            data = json.load(f)
        pid = data["problem_id"]
        for r in data["results"]:
            rows.append({"problem_id": pid, **r})
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
    ap.add_argument("--url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="token-abc123")
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument(
        "--stage1-dir", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage1_logging")
    )
    ap.add_argument("--subset", default=os.path.join(os.path.dirname(__file__), "subset.json"))
    ap.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage8_probe_compare"))
    ap.add_argument("--limit", type=int, default=None, help="only process the first N subset problems (testing)")
    ap.add_argument("--dry-run", action="store_true", help="stub the network call; verify the rest of the pipeline")
    ap.add_argument("--flatten-only", action="store_true", help="skip collection, just flatten existing variant_traj/")
    args = ap.parse_args()

    variant_dir = os.path.join(args.output, "variant_traj")
    os.makedirs(variant_dir, exist_ok=True)

    if args.flatten_only:
        df = flatten_to_csv(variant_dir, os.path.join(args.output, "probe_variants.csv"))
        print(f"Flattened {len(df)} rows -> {os.path.join(args.output, 'probe_variants.csv')}")
        return

    with open(args.subset, encoding="utf-8") as f:
        subset = json.load(f)
    if args.limit:
        subset = subset[: args.limit]

    print(f"Loading tokenizer {args.model} ...")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model)

    probes_df = pd.read_csv(os.path.join(args.stage1_dir, "probes.csv"))
    runner = Runner(args)
    tok_cache = {}

    todo = []
    for item in subset:
        pid = item["problem_id"]
        out_path = os.path.join(variant_dir, f"problem_{pid}.json")
        if os.path.exists(out_path):
            print(f"[skip] problem {pid} already done")
            continue
        traj_path = os.path.join(args.stage1_dir, "traj", f"problem_{pid}.json")
        with open(traj_path, encoding="utf-8") as f:
            traj = json.load(f)
        checkpoints = get_checkpoints(pid, probes_df, traj, tokenizer, tok_cache)
        todo.append((pid, traj["problem"], checkpoints))

    print(f"Running {len(todo)} problems x {len(DESIGNS)} designs " f"(dry_run={args.dry_run}) -> {args.output}")

    lock = threading.Lock()
    t0 = time.time()

    def work(pid, problem, checkpoints):
        results = process_problem(pid, problem, checkpoints, runner, args)
        out_path = os.path.join(variant_dir, f"problem_{pid}.json")
        with lock:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"problem_id": pid, "results": results}, f, ensure_ascii=False, indent=2)
        return pid, len(results)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, *t) for t in todo]
        for fut in as_completed(futures):
            pid, n = fut.result()
            done += 1
            print(f"[{done}/{len(todo)}] problem {pid}: {n} rows ({time.time() - t0:.0f}s elapsed)", flush=True)

    df = flatten_to_csv(variant_dir, os.path.join(args.output, "probe_variants.csv"))
    print(f"Done. Flattened {len(df)} rows -> {os.path.join(args.output, 'probe_variants.csv')}")


if __name__ == "__main__":
    main()
