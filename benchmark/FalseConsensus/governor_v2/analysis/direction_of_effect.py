#!/usr/bin/env python3
"""(3) Direction-of-effect + bootstrap CIs on the dev negative result.

Loads the frozen sweep replay rows (generated/sweep_*.jsonl.gz), reproduces the
per-rule worst-case per-model accuracy drop exactly as replay_rules.py does
(max over (split,model) group means), validates against the paper's reported
percentiles, then computes:
  (A) direction-of-effect: fraction of rules / cells that LOSE accuracy;
  (B) bootstrap CIs (resampling the 9 benchmark x seed environments within
      each (split,model) group) on the frontier (least-bad) rule and on the
      distribution of per-rule worst-case drops.
No GPU, no test-split read. Deterministic bootstrap (fixed integer seed).
"""
import gzip, json, glob, statistics, random
from collections import defaultdict

SHARDS = sorted(glob.glob(
    "benchmark/FalseConsensus/governor_v2/generated/sweep_*.jsonl.gz"))

def load_rows():
    for fn in SHARDS:
        with gzip.open(fn, "rt") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

# by_rule[rule_id] -> list of rows
by_rule = defaultdict(list)
for r in load_rows():
    by_rule[r["rule_id"]].append(r)
print(f"rules={len(by_rule)}  rows={sum(len(v) for v in by_rule.values())}")

def percentile(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx); hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

# ---- exact reproduction of max_model_accuracy_drop_pp ----
def max_model_drop(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["split"], row["model"])].append(float(row["accuracy_drop_pp"]))
    return max(statistics.fmean(v) for v in groups.values())

per_rule_maxmodel = {rid: max_model_drop(rows) for rid, rows in by_rule.items()}
vals = sorted(per_rule_maxmodel.values())
print("\n=== VALIDATION: percentiles of per-rule max_model_accuracy_drop_pp ===")
for q in (0.0, 0.01, 0.05, 0.25, 0.5):
    print(f"  p{int(q*100):>3} = {percentile(vals, q):.3f} pp")
print(f"  min  = {vals[0]:.3f} pp   (paper: 1.85)")
print(f"  paper targets: p1=3.37 p5=4.26 p25=10.7 median=20.1")

# ---- (A) direction-of-effect ----
n_rules = len(per_rule_maxmodel)
rules_lose = sum(1 for v in per_rule_maxmodel.values() if v > 0)
# cell-level: every (rule,model,benchmark,seed,split) row
cell_drops = [float(r["accuracy_drop_pp"]) for rows in by_rule.values() for r in rows]
cells_lose = sum(1 for d in cell_drops if d > 0)
cells_gain = sum(1 for d in cell_drops if d < 0)
cells_zero = sum(1 for d in cell_drops if d == 0)
# dev-split cells only
dev_cells = [float(r["accuracy_drop_pp"]) for rows in by_rule.values()
             for r in rows if r["split"] == "dev"]
dev_lose = sum(1 for d in dev_cells if d > 0)
print("\n=== (A) DIRECTION OF EFFECT ===")
print(f"  rules with worst-case per-model drop > 0 : {rules_lose}/{n_rules} "
      f"= {100*rules_lose/n_rules:.2f}%")
print(f"  all cells: n={len(cell_drops)}  lose>0={100*cells_lose/len(cell_drops):.2f}%  "
      f"gain<0={100*cells_gain/len(cell_drops):.2f}%  zero={100*cells_zero/len(cell_drops):.2f}%")
print(f"  dev-split cells: lose>0 = {100*dev_lose/len(dev_cells):.2f}%  "
      f"median cell drop = {statistics.median(dev_cells):.2f} pp")
print(f"  median over ALL cells = {statistics.median(cell_drops):.2f} pp  "
      f"mean = {statistics.fmean(cell_drops):.2f} pp")

# ---- (B) bootstrap CIs ----
# Resampling unit: the 9 (benchmark,seed) environments *within* each (split,model)
# group. For a given rule we recompute max-over-4-group-means on a resample.
def group_env_lists(rows):
    """(split,model) -> list of (benchmark,seed)->drop dicts collapsed to a
    list of per-env drops, plus the env key list for resampling."""
    g = defaultdict(dict)
    for row in rows:
        g[(row["split"], row["model"])][(row["benchmark"], row["seed"])] = float(row["accuracy_drop_pp"])
    return g

def boot_maxmodel(rows, rng, B=10000):
    g = group_env_lists(rows)
    # env keys are the same 9 across groups; resample env keys jointly (paired)
    env_keys = sorted({k for d in g.values() for k in d})
    stats = []
    ng = len(env_keys)
    for _ in range(B):
        idx = [rng.randrange(ng) for _ in range(ng)]
        keys = [env_keys[i] for i in idx]
        gm = []
        for grp, d in g.items():
            vals_ = [d[k] for k in keys if k in d]
            if vals_:
                gm.append(statistics.fmean(vals_))
        stats.append(max(gm))
    stats.sort()
    return percentile(stats, 0.025), percentile(stats, 0.975)

rng = random.Random(20260728)
# frontier / least-bad rule: the 5 least-bad rules and their env-bootstrap CIs
print("\n=== (B) BOOTSTRAP CIs (10k resamples over 9 benchmark x seed envs) ===")
ranked = sorted(per_rule_maxmodel.items(), key=lambda kv: kv[1])
for rid, val in ranked[:5]:
    lo, hi = boot_maxmodel(by_rule[rid], rng)
    fam = rid.split("__")[0]
    print(f"  {val:5.2f} pp  95% CI [{lo:5.2f}, {hi:5.2f}]  ({fam})  {rid}")

# per-model, per-benchmark breakdown for the single least-bad rule
best_rid = ranked[0][0]
print(f"\n  least-bad rule breakdown ({best_rid}):")
grp = defaultdict(list)
for row in by_rule[best_rid]:
    grp[(row["split"], row["model"].split('/')[-1])].append(
        (row["benchmark"], row["seed"], float(row["accuracy_drop_pp"]),
         float(row["saving_fraction"])))
for key in sorted(grp):
    ds = [d for *_x, d, _s in [(b,s,d,sv) for (b,s,d,sv) in grp[key]]]
    drops = [d for (_b,_s,d,_sv) in grp[key]]
    savs = [sv for (_b,_s,_d,sv) in grp[key]]
    print(f"    {key[0]:5} {key[1]:22}  mean drop {statistics.fmean(drops):6.2f}pp  "
          f"mean saving {100*statistics.fmean(savs):5.1f}%")

print("\n=== conservative-gate reference: per-model <=1.5pp; is ANY rule <=1.5? ===")
n_under = sum(1 for v in per_rule_maxmodel.values() if v <= 1.5)
print(f"  rules with worst-case per-model drop <= 1.5pp : {n_under}")
n_under2 = sum(1 for v in per_rule_maxmodel.values() if v <= 0)
print(f"  rules with worst-case per-model drop <= 0 (break-even+) : {n_under2}")
