#!/usr/bin/env python3
"""Held-out Llama-8B confirmation analysis.

Llama is held-out architecture evidence: NO policy search is performed on it.
This script only:
  * reports vanilla accuracy / cap rate / empty-answer rate by benchmark x seed;
  * replays the already-frozen Governor v1 policies (naive_agreement,
    conservative, balanced_task_aware_secondary) on dense and adaptive probe
    banks, reusing the authoritative rule interpreter
    (evaluate_existing_methods.replay_one / decide_stop);
  * reports accuracy drop, gross saving, actual net saving, probe tax, PSF,
    stop rate by benchmark x seed and as an environment macro;
  * compares dense vs adaptive probing without tuning.

Reuses related_work.metrics for standard aggregation; adds PSF/probe-tax.
"""
from __future__ import annotations
import argparse, json, math, sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from benchmark.FalseConsensus.governor_v2 import evaluate_existing_methods as eem
from benchmark.FalseConsensus.governor_v2 import replay_rules
from benchmark.FalseConsensus.related_work import metrics

MODEL = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"
SLUG = "deepseek-ai-deepseek-r1-distill-llama-8b"
BENCHMARKS = ["math500", "amc23", "aime24"]
SEEDS = [42, 43, 44]
POLICIES = [eem.METHOD_NAIVE, eem.METHOD_CONSERVATIVE, eem.METHOD_BALANCED]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--bank", type=Path,
        default=REPO/"benchmark/FalseConsensus/results/governor_v2_scale_dev_llama_corrected")
    p.add_argument("--v1-protocol", type=Path,
        default=REPO/"benchmark/FalseConsensus/final_eval/protocol.json")
    p.add_argument("--output", type=Path,
        default=REPO/"benchmark/FalseConsensus/results/governor_v2_scale_dev_llama_corrected/analysis")
    p.add_argument("--probe-mode", default="dense", choices=["dense","adaptive"])
    return p.parse_args()


def _mean(xs): return math.fsum(xs)/len(xs) if xs else 0.0


def vanilla_metrics(trajs):
    n = len(trajs)
    if not n: return {"n": 0}
    acc = _mean([1.0 if t.get("final_correct") else 0.0 for t in trajs])
    budget = int(trajs[0]["run_settings"].get("budget", 0))
    cap = _mean([1.0 if (not t.get("finished_naturally") or
                        int(t["tokens_used"]) > budget) else 0.0 for t in trajs])
    empty = _mean([1.0 if not t.get("final_answer","").strip() else 0.0 for t in trajs])
    trunc = _mean([1.0 if t.get("finish_reason")=="length" else 0.0 for t in trajs])
    toks = _mean([int(t["tokens_used"]) for t in trajs])
    return {"n": n, "vanilla_accuracy": acc, "cap_rate": cap,
            "empty_answer_rate": empty, "truncation_rate": trunc,
            "avg_tokens": toks}


def policy_aggregate(rows):
    """rows: per-problem replay rows from eem.replay_one (enriched)."""
    n = len(rows)
    if not n: return {"n": 0}
    acc = _mean([1.0 if r["correct"] else 0.0 for r in rows])
    base = _mean([1.0 if r["baseline_correct"] else 0.0 for r in rows])
    gross = _mean([float(r["main_only_token_saving_fraction"]) for r in rows])
    net = _mean([float(r["all_generated_saving_fraction"]) for r in rows])
    stop = _mean([1.0 if r["stopped"] else 0.0 for r in rows])
    psf = _mean([1.0 if float(r["all_generated_saving_fraction"]) > 0 else 0.0 for r in rows])
    pout = _mean([float(r["probe_out_tokens"]) for r in rows])
    pprompt = _mean([float(r["probe_prompt_tokens"]) for r in rows])
    return {"n": n, "accuracy": acc, "baseline_accuracy": base,
            "accuracy_drop_pp": 100.0*(base-acc), "gross_saving": gross,
            "actual_net_saving": net, "probe_tax": gross-net, "psf": psf,
            "stop_rate": stop, "avg_probe_out_tokens": pout,
            "avg_probe_prompt_tokens": pprompt}


def load_env_probes(env_dir, mode):
    """Return {problem_id: probes_list} using eem.scheduled_dense_probes
    (start=128, interval=128) over dense, and merged dense+adaptive for adaptive."""
    out = {}
    dense_dir = env_dir / "dense_simple32" / "probes"
    if not dense_dir.exists():
        return out
    adap_dir = env_dir / "adaptive_simple32" / "probes"
    for pf in sorted(dense_dir.glob("problem_*.json")):
        pid = int(pf.stem.split("_")[1])
        payload = json.loads(pf.read_text(encoding="utf-8"))
        probes = payload.get("probes", [])
        if mode == "adaptive" and adap_dir.exists():
            ap = adap_dir / f"problem_{pid}.json"
            if ap.exists():
                apayload = json.loads(ap.read_text(encoding="utf-8"))
                # merge by token_position (adaptive may add candidates)
                pos2p = {int(p["token_position"]): p for p in probes}
                for p in apayload.get("probes", []):
                    pos2p.setdefault(int(p["token_position"]), p)
                probes = sorted(pos2p.values(), key=lambda x: int(x["token_position"]))
        full = int(payload.get("main_token_count_recorded", 0))
        out[pid] = eem.scheduled_dense_probes({"probes": probes}, full)
    return out


def main():
    args = parse_args()
    protocol = json.loads(args.v1_protocol.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    per_problem_rows = []
    vanilla_by_env = {}
    env_policy_summaries = []
    for bench in BENCHMARKS:
        configs = eem._configs(protocol, bench)
        for seed in SEEDS:
            env = f"development__{SLUG}__{bench}__seed_{seed}"
            env_dir = args.bank / env
            main_dir = env_dir / "main" / "traj"
            if not main_dir.exists():
                print(f"[skip] {env}", flush=True); continue
            trajs = {}
            for tp in sorted(main_dir.glob("problem_*.json")):
                t = json.loads(tp.read_text(encoding="utf-8"))
                trajs[int(t["problem_id"])] = t
            vanilla_by_env[f"{bench}__seed_{seed}"] = vanilla_metrics(list(trajs.values()))
            probes_by_pid = load_env_probes(env_dir, args.probe_mode)
            for pid, traj in trajs.items():
                probes = probes_by_pid.get(pid, [])
                split = "heldout"
                for method, config in configs:
                    row = eem.replay_one(traj, probes, method=method,
                                         config=config, split=split)
                    row["benchmark"] = bench
                    row["seed"] = seed
                    row["probe_mode"] = args.probe_mode
                    per_problem_rows.append(row)
            # env-level policy summaries
            for method, _ in configs:
                rows = [r for r in per_problem_rows
                        if r["benchmark"]==bench and r["seed"]==seed
                        and r["method"]==method and r["probe_mode"]==args.probe_mode]
                s = policy_aggregate(rows)
                s.update({"benchmark": bench, "seed": seed, "policy": method})
                env_policy_summaries.append(s)

    # write outputs
    import os
    def wj(name, obj):
        p = args.output / name
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    def wjl(name, rows):
        p = args.output / (name+".tmp")
        with p.open("w", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False)+"\n")
        os.replace(p, args.output / name)
    wjl("llama_replay_rows.jsonl", per_problem_rows)
    wj("llama_vanilla_by_env.json", vanilla_by_env)
    wj("llama_policy_by_env.json", env_policy_summaries)

    # macro across envs per policy
    macro = []
    for method in POLICIES:
        cells = [s for s in env_policy_summaries if s["policy"]==method]
        m = {"policy": method, "n_envs": len(cells)}
        for k in ["accuracy","baseline_accuracy","accuracy_drop_pp","gross_saving",
                  "actual_net_saving","probe_tax","psf","stop_rate",
                  "avg_probe_out_tokens","avg_probe_prompt_tokens"]:
            m[k] = _mean([float(c[k]) for c in cells if k in c])
        macro.append(m)
    wj("llama_macro.json", macro)
    # vanilla macro
    vmacro = {}
    for bench in BENCHMARKS:
        cells = [v for k,v in vanilla_by_env.items() if k.startswith(bench+"__")]
        vmacro[bench] = {k: _mean([c[k] for c in cells if k in c]) for k in
                          ["vanilla_accuracy","cap_rate","empty_answer_rate",
                           "truncation_rate","avg_tokens"]}
        vmacro[bench]["n_envs"] = len(cells)
    wj("llama_vanilla_macro.json", vmacro)
    print(f"rows={len(per_problem_rows)} envs={len(vanilla_by_env)} policies={len(POLICIES)} mode={args.probe_mode}", flush=True)
    print(json.dumps(macro, indent=2)[:800], flush=True)


if __name__ == "__main__":
    main()
