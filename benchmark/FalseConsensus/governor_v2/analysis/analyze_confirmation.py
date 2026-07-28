#!/usr/bin/env python3
"""Confirmation-phase (TEST split) frontier/gate analysis.

Replays the SAME frozen 17,712-rule schema on the held-out test split (dev
models at seeds 45/46/47; unseen models Llama-8B and Qwen-32B at seed 45) and
asks: does the dev negative result reproduce out of distribution?
  - does ANY rule clear the conservative gate on test?
  - per-model worst-case drop distribution / percentiles on test;
  - direction-of-effect on test;
  - held-out-model (unseen architecture / scale) breakdown.
No GPU. Input: concatenated confirmation sweep rows.
"""
import json, sys, statistics
from collections import defaultdict

FN = sys.argv[1] if len(sys.argv) > 1 else (
    "/private/tmp/claude-501/-Users-moyunxiang-kevinelw-study-coding-SummerRe-"
    "Governor/c6056a0d-fbdc-49a2-82f2-4dfb4cc30540/scratchpad/conf_sweep/"
    "confirmation_metrics.jsonl")

rows = [json.loads(l) for l in open(FN) if l.strip()]
# match the dev selection: one operating (cap) budget per benchmark
OP_BUDGET = {"math500": 16384, "amc23": 16384, "aime24": 32768}
rows = [r for r in rows if r["budget"] == OP_BUDGET[r["benchmark"]]]
print(f"rows(at operating budget)={len(rows)}")
by_rule = defaultdict(list)
for r in rows:
    by_rule[r["rule_id"]].append(r)
models = sorted({r["model"] for r in rows})
roles = {r["model"]: r.get("model_role", "?") for r in rows}
seeds = sorted({r["seed"] for r in rows})
benches = sorted({r["benchmark"] for r in rows})
print(f"rules={len(by_rule)}  models={[m.split('/')[-1] for m in models]}")
print(f"roles={ {m.split('/')[-1]: roles[m] for m in models} }")
print(f"seeds={seeds}  benches={benches}")
env_per_rule = statistics.mode(len(v) for v in by_rule.values())
print(f"envs/rule (mode)={env_per_rule}")

def percentile(sv, q):
    if not sv: return float("nan")
    idx = q*(len(sv)-1); lo=int(idx); hi=min(lo+1,len(sv)-1); f=idx-lo
    return sv[lo]*(1-f)+sv[hi]*f

def worst_per_model(rows_):
    g = defaultdict(list)
    for row in rows_:
        g[row["model"]].append(float(row["accuracy_drop_pp"]))
    return max(statistics.fmean(v) for v in g.values())

def worst_per_benchmark(rows_):
    g = defaultdict(list)
    for row in rows_:
        g[row["benchmark"]].append(float(row["accuracy_drop_pp"]))
    return max(statistics.fmean(v) for v in g.values())

def psf(rows_):
    s = [float(r["saving_fraction"]) for r in rows_]
    return sum(v > 0 for v in s)/len(s)

per_rule_mm = {rid: worst_per_model(rs) for rid, rs in by_rule.items()}
per_rule_mb = {rid: worst_per_benchmark(rs) for rid, rs in by_rule.items()}
per_rule_psf = {rid: psf(rs) for rid, rs in by_rule.items()}

vals = sorted(per_rule_mm.values())
print("\n=== TEST-split per-rule worst-case per-model drop ===")
for q in (0.0, 0.01, 0.05, 0.25, 0.5):
    print(f"  p{int(q*100):>3} = {percentile(vals,q):.3f} pp")
print(f"  min = {vals[0]:.3f} pp")

# conservative gate: per-model<=1.5, per-benchmark<=2.0, psf>=0.8
gate = [rid for rid in by_rule
        if per_rule_mm[rid] <= 1.5 and per_rule_mb[rid] <= 2.0 and per_rule_psf[rid] >= 0.8]
print(f"\n=== CONSERVATIVE GATE on TEST (<=1.5 / <=2.0 / psf>=0.8) ===")
print(f"  rules clearing gate on test: {len(gate)}")
print(f"  rules with worst-case per-model drop <= 1.5pp (accuracy half only): "
      f"{sum(1 for v in vals if v<=1.5)}")

# direction of effect on test
cells = [float(r["accuracy_drop_pp"]) for r in rows]
lose = sum(1 for d in cells if d>0); gain=sum(1 for d in cells if d<0)
print(f"\n=== DIRECTION OF EFFECT on TEST ===")
print(f"  rules losing (worst-case per-model drop>0): "
      f"{sum(1 for v in vals if v>0)}/{len(vals)} = {100*sum(1 for v in vals if v>0)/len(vals):.2f}%")
print(f"  cells: n={len(cells)} lose>0={100*lose/len(cells):.2f}% gain<0={100*gain/len(cells):.2f}% "
      f"mean drop={statistics.fmean(cells):.2f}pp")

# per-model: does ANY rule keep THIS model's mean drop <=1.5 with positive saving?
print(f"\n=== PER-MODEL: least-bad mean drop, and safe-with-saving rules ===")
for m in models:
    mrows_by_rule = defaultdict(list)
    for rid, rs in by_rule.items():
        sel=[r for r in rs if r["model"]==m]
        if sel: mrows_by_rule[rid]=sel
    # per-model least-bad mean drop over that model's envs
    md = {rid: statistics.fmean(float(r["accuracy_drop_pp"]) for r in rs)
          for rid, rs in mrows_by_rule.items()}
    ms = {rid: sum(float(r["saving_fraction"])>0 for r in rs)/len(rs)
          for rid, rs in mrows_by_rule.items()}
    least = min(md.values())
    safe_saving = sum(1 for rid in md if md[rid] <= 1.5 and ms[rid] >= 0.8)
    print(f"  {roles[m]:22} {m.split('/')[-1]:32} least-bad mean drop={least:6.2f}pp  "
          f"rules(drop<=1.5 & psf>=0.8)={safe_saving}")
