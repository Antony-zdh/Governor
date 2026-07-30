#!/usr/bin/env python3
"""Matched Simple@32 vs CertaIndex@32 prompt-timing ablation launcher.

Drives ``related_work/certaindex_mid.py`` (the faithful frozen-trajectory
CertaIndex ``mid`` collector) over all 18 frozen environments for one model
(development seeds 42/43/44 + confirmation seeds 45/46/47 x 3 benchmarks),
with cap 32 / interval 64 / start 64 / patience 3 and the faithful
CERTAINDEX_SUFFIX. The Simple@32 arm is the *existing* ``dense_simple32`` bank
(not regenerated) and is replayed with the identical patience-3 stop rule in
``analyze_prompt_timing.py``.

Modes:
  --check-inputs   preflight: report 18 envs + 1710 main/Simple inputs
  --smoke           2-problem CertaIndex@32 smoke to a _smoke dir
  (default)         formal collection to results/probe_prompt_ablation/certaindex32/
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GOV = REPO / "benchmark/FalseConsensus/results/governor_v2"
OUT_ROOT = REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/certaindex32"
SPLIT = REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"

MODELS = {
    "deepseek": {
        "model_id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "slug": "deepseek-ai-deepseek-r1-distill-qwen-7b",
        "revision": "916b56a44061fd5cd7d6a8fb632557ed4f724f60",
        "url": "http://127.0.0.1:18000/v1",
    },
    "qwen3": {
        "model_id": "Qwen/Qwen3-8B",
        "slug": "qwen-qwen3-8b",
        "revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "url": "http://127.0.0.1:18001/v1",
    },
}
BENCHMARKS = ["math500", "amc23", "aime24"]
DEV_SEEDS = [42, 43, 44]
CONF_SEEDS = [45, 46, 47]


def envs_for(slug: str) -> list[str]:
    out = []
    for ph, seeds in (("development", DEV_SEEDS), ("confirmation", CONF_SEEDS)):
        for b in BENCHMARKS:
            for s in seeds:
                out.append(f"{ph}__{slug}__{b}__seed_{s}")
    return out


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, choices=list(MODELS))
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--url", default=None, help="override endpoint")
    p.add_argument("--check-inputs", action="store_true")
    p.add_argument("--smoke", action="store_true")
    return p.parse_args(argv)


def check_inputs(model_key: str) -> int:
    cfg = MODELS[model_key]
    envs = envs_for(cfg["slug"])
    n_envs = 0
    total_main = 0
    total_simple = 0
    complete_envs = 0
    for env in envs:
        main_dir = GOV / env / "main" / "traj"
        simp_dir = GOV / env / "dense_simple32" / "probes"
        if not main_dir.exists():
            print(f"[missing main] {env}")
            continue
        n_envs += 1
        n_main = len(list(main_dir.glob("problem_*.json")))
        n_simp = len(list(simp_dir.glob("problem_*.json"))) if simp_dir.exists() else 0
        total_main += n_main
        total_simple += n_simp
        if n_main and n_main == n_simp:
            complete_envs += 1
        else:
            print(f"[incomplete] {env}: main={n_main} simple={n_simp}")
    print(f"model={cfg['model_id']} environments={n_envs} (expected 18)")
    print(f"main trajectories={total_main} (expected 1710)")
    print(f"simple trajectories={total_simple} (expected 1710)")
    print(f"complete main/Simple envs={complete_envs}")
    ok = n_envs == 18 and total_main == 1710 and total_simple == 1710
    print("PREFLIGHT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def run_one_env(cfg, env: str, workers: int, url: str, output_root: Path,
                limit: int = 0, problem_ids=None) -> int:
    from benchmark.FalseConsensus.related_work import certaindex_mid
    main_run = GOV / env / "main"
    output = output_root / env
    output.mkdir(parents=True, exist_ok=True)
    argv = [
        "--main-run", str(main_run),
        "--output", str(output),
        "--url", url,
        "--model", cfg["model_id"],
        "--model-revision", cfg["revision"],
        "--interval", "64",
        "--start-token", "64",
        "--probe-tokens", "32",
        "--patience", "3",
        "--workers", str(workers),
        "--split-manifest", str(SPLIT),
    ]
    if limit:
        argv += ["--limit", str(limit)]
    if problem_ids:
        for pid in problem_ids:
            argv += ["--problem-id", str(pid)]
    print(f"\n=== {env} -> {url} ===", flush=True)
    t0 = time.perf_counter()
    certaindex_mid.main(argv)
    print(f"=== {env} done in {time.perf_counter()-t0:.0f}s ===", flush=True)
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = MODELS[args.model]
    url = args.url or cfg["url"]
    if args.check_inputs:
        return check_inputs(args.model)
    if args.smoke:
        envs = envs_for(cfg["slug"])
        smoke_env = next(e for e in envs if "math500__seed_42" in e)
        smoke_root = REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/_smoke" / args.model
        print(f"smoke: 2 problems from {smoke_env} -> {smoke_root}")
        return run_one_env(cfg, smoke_env, workers=2, url=url,
                           output_root=smoke_root, limit=2)
    # formal
    started = time.perf_counter()
    for env in envs_for(cfg["slug"]):
        run_one_env(cfg, env, workers=args.workers, url=url, output_root=OUT_ROOT)
    print(f"\n=== {args.model} formal collection complete in {time.perf_counter()-started:.0f}s ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
