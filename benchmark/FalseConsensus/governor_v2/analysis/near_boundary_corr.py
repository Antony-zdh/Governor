#!/usr/bin/env python3
"""Near-boundary dev->test frontier correlation.

The global Pearson r=0.96 between dev and test worst-case per-model accuracy
drop (over all 17,712 rules) is dominated by dynamic range (dev drops span
0-60pp). This script reports the correlation restricted toward the decision
boundary (dev drop <= {10,5,3,2} pp), showing it decays to ~0: the safe end of
the frontier is measurement-noise-limited on both splits, so the split-invariant
claim is the empty joint gate, not a clean rank reproduction at the boundary.

Usage: python near_boundary_corr.py <confirmation_metrics.jsonl>
  dev metrics: generated/sweep_*.jsonl.gz (dev split)
  test metrics: confirmation sweep rows restricted to the 2 dev models, cap budget
"""
import json, gzip, glob, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
GEN = HERE.parents[1] / "generated"
OP = {"math500": 16384, "amc23": 16384, "aime24": 32768}
DEVMODELS = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}

def worst_model(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["model"]].append(float(r["accuracy_drop_pp"]))
    return max(statistics.fmean(v) for v in g.values())

def pearson(xs, ys):
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = sum((x-mx)**2 for x in xs); sy = sum((y-my)**2 for y in ys)
    sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    return sxy/(sx*sy)**0.5 if sx > 0 and sy > 0 else float("nan")

def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i]); rk = [0]*len(v)
        for pos, i in enumerate(order): rk[i] = pos
        return rk
    return pearson(rank(xs), rank(ys))

def main():
    test_fn = sys.argv[1]
    dev = defaultdict(list)
    for fn in sorted(glob.glob(str(GEN/"sweep_*.jsonl.gz"))):
        with gzip.open(fn, "rt") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    if r["split"] == "dev":
                        dev[r["rule_id"]].append(r)
    dev_mm = {k: worst_model(v) for k, v in dev.items()}
    test = defaultdict(list)
    for line in open(test_fn):
        if line.strip():
            r = json.loads(line)
            if r["model"] in DEVMODELS and r["budget"] == OP[r["benchmark"]]:
                test[r["rule_id"]].append(r)
    test_mm = {k: worst_model(v) for k, v in test.items()}
    rules = sorted(set(dev_mm) & set(test_mm))
    xs = [dev_mm[r] for r in rules]; ys = [test_mm[r] for r in rules]
    print(f"all rules n={len(rules)}: Pearson={pearson(xs,ys):.3f} Spearman={spearman(xs,ys):.3f}")
    for thr in (10, 5, 3, 2):
        sub = [r for r in rules if dev_mm[r] <= thr]
        a = [dev_mm[r] for r in sub]; b = [test_mm[r] for r in sub]
        p = pearson(a, b) if len(set(b)) > 1 else float("nan")
        print(f"dev_mm<={thr:2d}pp  n={len(sub):5d}  Pearson={p:+.3f}  "
              f"test_mm range[{min(b):+.2f},{max(b):+.2f}]")

if __name__ == "__main__":
    main()
