"""A2c: is the 4% bootstrap gate-clearing rate a real candidate rule, or just
max-taking over 3,520 correlated rules?

For each individual rule compute P(clears the conservative gate) under the
stratified seed bootstrap. If no single rule has an appreciable probability,
the 4% any-rule rate is a multiple-comparisons artifact and the empty corner
stands.
"""
import sys, random, statistics as st
from collections import defaultdict
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_harm_rescue as CHR

by_rule = defaultdict(dict)
cells = defaultdict(list)
for r in CHR._load_dev_rows():
    env = (r["model"], r["benchmark"], r["seed"])
    by_rule[r["rule_id"]][env] = (r["accuracy_drop_pp"], r["saving_fraction"])
    if env not in cells[(r["model"], r["benchmark"])]:
        cells[(r["model"], r["benchmark"])].append(env)
envs = sorted({e for v in by_rule.values() for e in v})
pos = {e: i for i, e in enumerate(envs)}
cell_idx = [[pos[e] for e in sorted(v)] for v in cells.values()]
rule_ids = sorted(by_rule)
mat = [[by_rule[r][e] for e in envs] for r in rule_ids]

random.seed(20260808)
B = 2000
idxs = [[random.choice(c) for c in cell_idx for _ in range(3)] for _ in range(B)]

hits = [0] * len(rule_ids)
for ri, row in enumerate(mat):
    for idx in idxs:
        d = st.fmean(row[i][0] for i in idx)
        if d > 1.0:
            continue
        s = st.fmean(row[i][1] for i in idx)
        if s < 0.10:
            continue
        if st.fmean(1.0 if row[i][1] > 0 else 0.0 for i in idx) >= 0.80:
            hits[ri] += 1
    if (ri + 1) % 500 == 0:
        print(f"  {ri+1}/{len(rule_ids)}", flush=True)

order = sorted(range(len(rule_ids)), key=lambda i: -hits[i])
print(f"\nper-rule P(clears conservative) under stratified seed bootstrap, B={B}")
print(f"rules with P > 0: {sum(1 for h in hits if h)}")
for i in order[:10]:
    row = by_rule[rule_ids[i]]
    d = st.fmean(v[0] for v in row.values()); s = st.fmean(v[1] for v in row.values())
    print(f"  {rule_ids[i]}  P={hits[i]/B:.4f}  true macro drop {d:.3f}pp saving {100*s:.3f}%")
