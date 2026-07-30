#!/usr/bin/env python3
"""32B scale-dev sweep: does the dev-selected accuracy floor generalize to the
held-out test split? Unlike the ①/② confirmation setup, the scale-dev matrix
collected train+dev+test in one main run per (model, benchmark, seed), so dev
and test rows both live in the same sweep file (generated/sweep_scale_32b.jsonl.gz)
-- no separate confirmation sweep needed here.

Per rule, per split: worst-case mean accuracy drop across the 3 benchmarks
(32B has only one model, so "worst-case" collapses to worst-benchmark here,
unlike the multi-model 7B/8B/Llama sweeps which take worst-over-model).
"""
import json, gzip, sys, math, statistics
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else (
    "benchmark/FalseConsensus/governor_v2/generated/sweep_scale_32b.jsonl.gz")


def worst_bench(splitmap):
    return max(statistics.fmean(v) for v in splitmap.values()) if splitmap else None


by = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # rule->split->bench->[drops]
op = gzip.open if path.endswith(".gz") else open
for line in op(path, "rt"):
    r = json.loads(line)
    by[r["rule_id"]][r["split"]][r["benchmark"]].append(r.get("accuracy_drop_pp", 0.0))

dt = []
for rule, sp in by.items():
    if "dev" in sp and "test" in sp:
        d = worst_bench(sp["dev"])
        t = worst_bench(sp["test"])
        if d is not None and t is not None:
            dt.append((rule, d, t))

dt_dev = sorted(dt, key=lambda x: x[1])
dt_test = sorted(dt, key=lambda x: x[2])

print(f"rules with dev&test: {len(dt)}")
print(f"DEV floor  (min worst-bench drop): {dt_dev[0][1]:+.3f}pp  [{dt_dev[0][0][:40]}]  -> its TEST drop {dt_dev[0][2]:+.3f}pp")
print(f"TEST floor (min worst-bench drop): {dt_test[0][2]:+.3f}pp  [{dt_test[0][0][:40]}]  (test is held-out; floor-on-test is optimistic)")

xs = [d for _, d, _ in dt]
ys = [t for _, _, t in dt]
n = len(xs)
mx = statistics.fmean(xs)
my = statistics.fmean(ys)
cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
sy = math.sqrt(sum((y - my) ** 2 for y in ys))
print(f"dev<->test per-rule Pearson r = {cov / (sx * sy):.3f}  over {n} rules  (7B/8B was 0.96)")

safe_dev = [(d, t) for _, d, t in dt if d <= 1.5]
if safe_dev:
    td = [t for _, t in safe_dev]
    print(f"rules dev-drop<=1.5pp: {len(safe_dev)}  -> their TEST drop: min {min(td):+.2f} / mean {statistics.fmean(td):+.2f} / max {max(td):+.2f}pp")
