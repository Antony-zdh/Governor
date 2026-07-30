#!/usr/bin/env python3
"""Drive the probe-cost v2 cap-specific probe collection across all 18
frozen DEV environments (DS-Qwen-7B + Qwen3-8B x {math500,amc23,aime24} x
seeds 42/43/44). Routes DS envs to the DS server, Qwen3 envs to the Qwen3
server. Resumable (collect_capped_probes skips existing per-problem files).
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BANK = REPO / "benchmark/FalseConsensus/results/governor_v2"
CAPB = REPO / "benchmark/FalseConsensus/probe_cost_ablation/cap_banks"
PIDS = REPO / "benchmark/FalseConsensus/governor_v2/generated/problem_ids"

MODELS = [
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai-deepseek-r1-distill-qwen-7b",
     "http://127.0.0.1:18001/v1"),
    ("Qwen/Qwen3-8B", "qwen-qwen3-8b", "http://127.0.0.1:18002/v1"),
]
BENCHMARKS = ["math500", "amc23", "aime24"]
SEEDS = [42, 43, 44]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default="/localdata/dzhaoah/gov-venv/bin/python")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--caps", default="8,16,32")
    ap.add_argument("--only", default=None, choices=["ds", "qwen3"],
                   help="restrict to one model family for parallel sharding")
    a = ap.parse_args()
    for model, slug, url in MODELS:
        if a.only == "ds" and "Qwen3" in model: continue
        if a.only == "qwen3" and "Qwen3" not in model: continue
        for bench in BENCHMARKS:
            pidf = PIDS / f"{bench}__dev.txt"
            for seed in SEEDS:
                env = f"development__{slug}__{bench}__seed_{seed}"
                main_run = BANK / env / "main"
                out = CAPB / env
                if not main_run.exists():
                    print(f"[skip] no main {main_run}", flush=True); continue
                cmd = [a.python,
                       str(REPO / "benchmark/FalseConsensus/probe_cost_ablation/collect_capped_probes.py"),
                       "--main-run", str(main_run), "--output", str(out),
                       "--url", url, "--caps", a.caps,
                       "--problem-ids-file", str(pidf),
                       "--workers", str(a.workers)]
                print(f"\n=== {env} -> {url} ===", flush=True)
                r = subprocess.run(cmd, cwd=str(REPO))
                if r.returncode != 0:
                    print(f"[ERROR] {env} exited {r.returncode}", flush=True)
                    sys.exit(r.returncode)
    print("\n=== cap-bank collection complete ===", flush=True)


if __name__ == "__main__":
    main()
