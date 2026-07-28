#!/usr/bin/env python3
"""Leakage-safe confirmation: does ANY rule clear the conservative gate on BOTH
dev and test? Re-estimating the gate directly on test is in-sample selection;
the held-out question is generalization = the dev->test intersection.

dev metrics: generated/sweep_*.jsonl.gz (train+dev). test metrics: confirmation
sweep rows (test only). Per-model drop computed on the EVAL split of each side
(dev-split for dev, test-split for test) so the two are apples-to-apples.
"""
import json, gzip, glob, statistics, sys
from collections import defaultdict

TEST_FN = sys.argv[1] if len(sys.argv) > 1 else (
    "/private/tmp/claude-501/-Users-moyunxiang-kevinelw-study-coding-SummerRe-"
    "Governor/c6056a0d-fbdc-49a2-82f2-4dfb4cc30540/scratchpad/conf_sweep/"
    "confirmation_metrics.jsonl")
OP = {"math500": 16384, "amc23": 16384, "aime24": 32768}

def worst_per_model(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["model"]].append(float(r["accuracy_drop_pp"]))
    return max(statistics.fmean(v) for v in g.values())
def worst_per_bench(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["benchmark"]].append(float(r["accuracy_drop_pp"]))
    return max(statistics.fmean(v) for v in g.values())
def psf(rows):
    s = [float(r["saving_fraction"]) for r in rows]
    return sum(v > 0 for v in s)/len(s)

# ---- DEV (dev-split only, matching the eval split) ----
dev = defaultdict(list)
for fn in sorted(glob.glob("benchmark/FalseConsensus/governor_v2/generated/sweep_*.jsonl.gz")):
    with gzip.open(fn, "rt") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            r = json.loads(line)
            if r["split"] == "dev":
                dev[r["rule_id"]].append(r)
dev_mm = {k: worst_per_model(v) for k, v in dev.items()}
dev_mb = {k: worst_per_bench(v) for k, v in dev.items()}
dev_psf = {k: psf(v) for k, v in dev.items()}

# ---- TEST ----
test = defaultdict(list)
for line in open(TEST_FN):
    line = line.strip()
    if not line: continue
    r = json.loads(line)
    if r["budget"] == OP[r["benchmark"]]:
        test[r["rule_id"]].append(r)
test_mm = {k: worst_per_model(v) for k, v in test.items()}
test_mb = {k: worst_per_bench(v) for k, v in test.items()}
test_psf = {k: psf(v) for k, v in test.items()}

rules = sorted(set(dev_mm) & set(test_mm))
print(f"rules in both dev&test: {len(rules)}")

def gate(mm, mb, ps, k):  # conservative
    return mm[k] <= 1.5 and mb[k] <= 2.0 and ps[k] >= 0.8

dev_pass = {k for k in rules if gate(dev_mm, dev_mb, dev_psf, k)}
test_pass = {k for k in rules if gate(test_mm, test_mb, test_psf, k)}
both = dev_pass & test_pass
print(f"\n=== CONSERVATIVE GATE (per-model<=1.5, per-bench<=2.0, psf>=0.8) ===")
print(f"  pass on DEV (dev-split): {len(dev_pass)}")
print(f"  pass on TEST           : {len(test_pass)}")
print(f"  pass on BOTH           : {len(both)}   <-- leakage-safe generalization")

# accuracy-only half of the gate
d15 = {k for k in rules if dev_mm[k] <= 1.5}
t15 = {k for k in rules if test_mm[k] <= 1.5}
print(f"\n=== accuracy half only (per-model drop <= 1.5pp) ===")
print(f"  dev<=1.5: {len(d15)}   test<=1.5: {len(t15)}   both<=1.5: {len(d15 & t15)}")
# with positive net savings too (psf>=0.8)
d15s = {k for k in d15 if dev_psf[k] >= 0.8}
t15s = {k for k in t15 if test_psf[k] >= 0.8}
print(f"  dev(<=1.5 & psf>=.8): {len(d15s)}  test: {len(t15s)}  both: {len(d15s & t15s)}")

# where do the test-passers land on dev, and vice versa?
import statistics as st
if test_pass:
    tp_devdrop = sorted(dev_mm[k] for k in test_pass)
    print(f"\n=== the {len(test_pass)} TEST-gate-passers, evaluated on DEV ===")
    print(f"  their dev per-model drop: min={tp_devdrop[0]:.2f} median={st.median(tp_devdrop):.2f} "
          f"max={tp_devdrop[-1]:.2f} pp; how many also <=1.5 on dev: {sum(1 for x in tp_devdrop if x<=1.5)}")
# dev least-bad rule on test; test least-bad rule on dev
dev_best = min(rules, key=lambda k: dev_mm[k])
test_best = min(rules, key=lambda k: test_mm[k])
print(f"\n=== tracking the extremes across splits ===")
print(f"  dev least-bad rule: dev_mm={dev_mm[dev_best]:.2f} -> test_mm={test_mm[dev_best]:.2f} pp")
print(f"  test least-bad rule: test_mm={test_mm[test_best]:.2f} -> dev_mm={dev_mm[test_best]:.2f} pp")
# correlation
xs=[dev_mm[k] for k in rules]; ys=[test_mm[k] for k in rules]
mx=st.fmean(xs); my=st.fmean(ys)
cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
den=(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))**0.5
print(f"  Pearson corr(dev_mm, test_mm) = {cov/den:.3f}")
