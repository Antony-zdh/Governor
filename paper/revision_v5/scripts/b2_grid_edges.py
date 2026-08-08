"""B2: is the empty safe corner an artifact of a truncated search grid?

A negative result over a rule family is only as strong as the family. The
hostile version: "you searched 3,520 rules but the good one lies just outside
your grid." The diagnostic is whether the rules that DEFINE the frontier sit at
grid edges. An interior optimum means extending the grid would not help; an
edge optimum means the search was truncated in the direction that matters.

Reports the (drop, saving) Pareto frontier over the committed dev archive and
the axis values of every frontier rule, flagging min/max-of-grid positions.
"""
import sys, gzip, json, statistics as st
from collections import defaultdict, Counter
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_harm_rescue as CHR

AXES = ["evidence.window_probes", "evidence.dominant_share_threshold",
        "maturity.minimum_tokens", "probe.schedule.interval_tokens",
        "validity.mode", "certainty.enabled"]

meta = {}
grid = defaultdict(set)
with gzip.open(FC / "results/governor_v2_ws_sweep/candidate_rules_v2.jsonl.gz", "rt") as f:
    for line in f:
        d = json.loads(line)
        av = d["metadata"]["axis_values"]
        meta[d["rule_id"]] = (d["metadata"]["template"], av)
        for a in AXES:
            if a in av:
                grid[a].add(json.dumps(av[a]))

num = {a: sorted(float(json.loads(v)) for v in grid[a])
       for a in AXES if all(json.loads(v).__class__ in (int, float) for v in grid[a])}
print("numeric grid ranges:")
for a, vs in num.items():
    print(f"  {a:38s} {vs}")

drops, savs = defaultdict(list), defaultdict(list)
for r in CHR._load_dev_rows():
    drops[r["rule_id"]].append(r["accuracy_drop_pp"])
    savs[r["rule_id"]].append(r["saving_fraction"])
pts = {k: (st.fmean(v), st.fmean(savs[k])) for k, v in drops.items()}
print(f"\nrules scored: {len(pts)}")

# Pareto frontier: minimise drop, maximise saving
items = sorted(pts.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
front, best = [], -9e9
for rid, (d, s) in items:
    if s > best:
        front.append((rid, d, s))
        best = s
print(f"Pareto-frontier rules: {len(front)}")

print(f"\n{'drop_pp':>8} {'saving':>8}  W    s    matur interval validity  certain  template")
for rid, d, s in front:
    t, av = meta[rid]
    print(f"{d:8.3f} {100*s:7.2f}%  "
          f"{av.get('evidence.window_probes'):<4} "
          f"{av.get('evidence.dominant_share_threshold'):<4} "
          f"{av.get('maturity.minimum_tokens'):<5} "
          f"{str(av.get('probe.schedule.interval_tokens','event')):<8} "
          f"{str(av.get('validity.mode')):<9} "
          f"{str(av.get('certainty.enabled')):<8} {t}")

print("\naxis-value census over the frontier (edge = at grid min or max):")
for a in AXES:
    c = Counter(json.dumps(meta[r][1].get(a)) for r, _, _ in front)
    lo, hi = (min(num[a]), max(num[a])) if a in num else (None, None)
    tag = lambda v: ("" if lo is None or json.loads(v) is None else
                     ("  <-MIN" if float(json.loads(v)) == lo else
                      "  <-MAX" if float(json.loads(v)) == hi else ""))
    print(f"  {a}")
    for v, n in sorted(c.items(), key=lambda x: -x[1]):
        print(f"      {v:<12} {n:3d}{tag(v)}")

# the two rules that actually matter for the headline
safe = [(rid, d, s) for rid, (d, s) in pts.items() if d <= 1.0]
best_safe = max(safe, key=lambda x: x[2])
over10 = [(rid, d, s) for rid, (d, s) in pts.items() if s >= 0.10]
min_drop10 = min(over10, key=lambda x: x[1])
for label, (rid, d, s) in [("max saving @ drop<=1pp", best_safe),
                           ("min drop @ saving>=10%", min_drop10)]:
    print(f"\n{label}: {rid}  drop {d:.3f}pp saving {100*s:.3f}%")
    print(f"   {meta[rid][0]}  {json.dumps(meta[rid][1], sort_keys=True)[:300]}")
