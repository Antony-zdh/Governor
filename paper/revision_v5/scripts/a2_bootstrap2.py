"""A2b: stratified bootstrap respecting the crossed design.

The 18 dev environments are a fully crossed 2 models x 3 benchmarks design with
3 seeds each. Resampling all 18 with replacement (a2_bootstrap.py) can produce
worlds made mostly of 6-problem aime24 cells, which is not a world this design
could have produced. The design-respecting resample is over SEEDS within each
(model, benchmark) cell, holding the 2x3 structure fixed.

Reports both, plus which rules clear and what they actually look like.
"""
import sys, json, random, statistics as st
from collections import defaultdict
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_harm_rescue as CHR

GATES = [("conservative", 1.0, 0.10, 0.80),
         ("balanced", 2.0, 0.20, 0.80),
         ("token_efficient", 3.5, 0.30, 0.70)]

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
print(f"rules {len(by_rule)}  envs {len(envs)}  cells {len(cell_idx)} x {len(cell_idx[0])} seeds")

rule_ids = sorted(by_rule)
mat = [[by_rule[r][e] for e in envs] for r in rule_ids]


def gates_on(idx):
    out = {g[0]: [] for g in GATES}
    best_safe = None
    for ri, row in enumerate(mat):
        d = st.fmean(row[i][0] for i in idx)
        s = st.fmean(row[i][1] for i in idx)
        psf = st.fmean(1.0 if row[i][1] > 0 else 0.0 for i in idx)
        if d <= 1.0 and (best_safe is None or s > best_safe):
            best_safe = s
        for name, dc, sc, pc in GATES:
            if d <= dc and s >= sc and psf >= pc:
                out[name].append(rule_ids[ri])
    return out, best_safe


random.seed(20260808)
B = 2000
for label, sampler in [
    ("stratified (seeds within each model x benchmark cell)",
     lambda: [random.choice(c) for c in cell_idx for _ in range(3)]),
    ("naive (all 18 environments with replacement)",
     lambda: [random.randrange(len(envs)) for _ in range(len(envs))]),
]:
    counts = {n: 0 for n, *_ in GATES}
    anyc = 0
    sav = []
    winners = defaultdict(int)
    for b in range(B):
        idx = sampler()
        g, bs = gates_on(idx)
        if bs is not None:
            sav.append(bs)
        hit = False
        for n in counts:
            if g[n]:
                counts[n] += 1
                hit = True
                if n == "conservative":
                    for w in g[n]:
                        winners[w] += 1
        anyc += hit
    sav.sort()
    q = lambda p: 100 * sav[int(p * (len(sav) - 1))]
    print(f"\n=== {label}, B={B} ===")
    for n in counts:
        print(f"  P({n} non-empty) = {counts[n]}/{B} = {100*counts[n]/B:.2f}%")
    print(f"  P(any) = {anyc}/{B} = {100*anyc/B:.2f}%")
    print(f"  max saving @ drop<=1pp: median {q(0.5):.3f}%  "
          f"95% CI [{q(0.025):.3f}%, {q(0.975):.3f}%]  max {100*sav[-1]:.3f}%  "
          f"(replicates with no rule under 1pp: {B-len(sav)})")
    if winners:
        top = sorted(winners.items(), key=lambda x: -x[1])[:5]
        print(f"  distinct rules ever clearing conservative: {len(winners)}")
        for rid, c in top:
            row = by_rule[rid]
            d = st.fmean(v[0] for v in row.values())
            s = st.fmean(v[1] for v in row.values())
            print(f"    {rid}  in {c} replicates | true macro drop {d:.3f}pp saving {100*s:.3f}%")
