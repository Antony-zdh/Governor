#!/usr/bin/env python3
"""Multi-seed aggregate for the DEER online experiment (seeds 42/43/44).

Replicates aggregate.py's metric definitions (fair_token_saving, accuracy_delta)
and the 6-cell macro convention, but across seeds. Seed 42 = formal online_dev/;
seeds 43/44 = non-formal online_dev_nonformal/. Baseline (full generation) for
seed S is governor_v2 development__<model>__<bench>__seed_S/main/traj.
"""
import json, glob, statistics
from pathlib import Path
from collections import defaultdict

ROOT = "benchmark/FalseConsensus/results"
METHODS = ["deer_inspired_online_v1", "deer_online_reference"]
MODELS = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek", "Qwen/Qwen3-8B": "qwen3"}
BENCHES = ["math500", "amc23", "aime24"]

def longname(m): return m.replace("/", "-").lower()

def baseline_lookup(model, benchmark, seed):
    d = f"{ROOT}/governor_v2/development__{longname(model)}__{benchmark}__seed_{seed}/main/traj"
    cache = {}
    for p in glob.glob(f"{d}/problem_*.json"):
        pid = int(Path(p).stem.split("_")[1])
        b = json.load(open(p))
        cache[pid] = (int(bool(b["final_correct"])), int(b["tokens_used"]))
    return cache

def collect(seed, online_root):
    rows = []
    for method in METHODS:
        for model, mk in MODELS.items():
            base_by_bench = {b: baseline_lookup(model, b, seed) for b in BENCHES}
            for bench in BENCHES:
                d = f"{ROOT}/deer_inspired/{online_root}/{method}/{mk}__{bench}__seed_{seed}/problems"
                files = glob.glob(f"{d}/problem_*.json")
                base = base_by_bench[bench]
                for p in files:
                    pl = json.load(open(p))
                    pid = int(pl["problem_id"])
                    if pid not in base:
                        continue
                    correct = int(bool(pl["correct"]))
                    agt = int(pl["accounting"]["all_generated_tokens"])
                    bc, bt = base[pid]
                    fair = (bt - agt) / bt if bt else 0.0
                    rows.append(dict(method=method, model=mk, benchmark=bench, seed=seed,
                                     correct=correct, acc_delta=correct - bc, fair=fair))
    return rows

SEEDS = {42: "online_dev", 43: "online_dev_nonformal", 44: "online_dev_nonformal"}
allrows = []
for s, root in SEEDS.items():
    r = collect(s, root)
    allrows += r
    print(f"seed {s}: {len(r)} problem-rows from {root}")

def macro(rows, method, model=None):
    sel = [r for r in rows if r["method"] == method and (model is None or r["model"] == model)]
    by = defaultdict(list)
    for r in sel:
        by[(r["model"], r["benchmark"])].append(r)
    env_d = [statistics.fmean(x["acc_delta"] for x in v) for v in by.values()]
    env_f = [statistics.fmean(x["fair"] for x in v) for v in by.values()]
    env_a = [statistics.fmean(x["correct"] for x in v) for v in by.values()]
    return (100 * statistics.fmean(env_a), 100 * statistics.fmean(env_d),
            100 * statistics.fmean(env_f), len(by))

print("\n=== PER-SEED macro (inspired) ===")
for s in (42, 43, 44):
    rows = [r for r in allrows if r["seed"] == s]
    a, d, f, n = macro(rows, "deer_inspired_online_v1")
    ad, dd, fd, _ = macro(rows, "deer_inspired_online_v1", "deepseek")
    aq, dq, fq, _ = macro(rows, "deer_inspired_online_v1", "qwen3")
    print(f"  seed {s}: macro dAcc={d:+.2f}pp save={f:.1f}%  | Qwen3 dAcc={dq:+.2f} save={fq:.1f}  DeepSeek dAcc={dd:+.2f} save={fd:.1f}")

print("\n=== ACROSS 3 SEEDS (42/43/44 pooled as env replicates) ===")
for meth, lbl in [("deer_inspired_online_v1", "Inspired"), ("deer_online_reference", "DEER-ref")]:
    a, d, f, n = macro(allrows, meth)
    ad, dd, fd, _ = macro(allrows, meth, "deepseek")
    aq, dq, fq, _ = macro(allrows, meth, "qwen3")
    print(f"  {lbl:9}: macro dAcc={d:+.2f}pp save={f:.1f}% (n_env={n})  | "
          f"Qwen3 dAcc={dq:+.2f} save={fq:.1f}  DeepSeek dAcc={dd:+.2f} save={fd:.1f}")

# per-seed macro spread for inspired (robustness of the single-seed claim)
ins = [macro([r for r in allrows if r["seed"] == s], "deer_inspired_online_v1") for s in (42, 43, 44)]
dvals = [x[1] for x in ins]; fvals = [x[2] for x in ins]
print(f"\n  inspired macro dAcc across seeds: {[f'{v:+.2f}' for v in dvals]}  "
      f"(mean {statistics.fmean(dvals):+.2f}, range [{min(dvals):+.2f},{max(dvals):+.2f}])")
print(f"  inspired macro save across seeds: {[f'{v:.1f}' for v in fvals]}  "
      f"(mean {statistics.fmean(fvals):.1f})")

# ---- paired inspired-vs-DEER-ref, stratified env-level bootstrap over 18 envs ----
import random
def env_means(method):
    by = defaultdict(list)
    for r in allrows:
        if r["method"] == method:
            by[(r["model"], r["benchmark"], r["seed"])].append(r)
    return {k: (statistics.fmean(x["acc_delta"] for x in v),
                statistics.fmean(x["fair"] for x in v)) for k, v in by.items()}
ins = env_means("deer_inspired_online_v1"); ref = env_means("deer_online_reference")
keys = sorted(set(ins) & set(ref))
diff_acc = [ (ins[k][0] - ref[k][0]) for k in keys]   # inspired - ref, acc_delta (fraction)
diff_sav = [ (ins[k][1] - ref[k][1]) for k in keys]   # inspired - ref, fair saving (fraction)
rng = random.Random(20260729); B = 10000
def boot_ci(vals):
    n = len(vals); s = []
    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        s.append(statistics.fmean(vals[i] for i in idx))
    s.sort()
    return s[int(0.025*B)], s[int(0.975*B)]
la, ha = boot_ci(diff_acc); ls, hs = boot_ci(diff_sav)
print(f"\n=== paired Inspired - DEER-ref (18 envs, 10k env-bootstrap) ===")
print(f"  dAcc advantage = {100*statistics.fmean(diff_acc):+.2f}pp  95% CI [{100*la:+.2f}, {100*ha:+.2f}]")
print(f"  token-saving advantage = {100*statistics.fmean(diff_sav):+.2f}%  95% CI [{100*ls:+.2f}, {100*hs:+.2f}]")
