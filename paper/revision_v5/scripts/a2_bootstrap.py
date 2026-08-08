"""A2: is 0/3,520 a power problem?

Attack: 18 environments, aime24 dev n=6 per seed. A reviewer can say the sweep
simply lacks the power to detect a rule that works.

Test: nonparametric bootstrap over the 18 environments (resample environments
with replacement, recompute every rule's macro drop / saving / psf, re-apply the
three gates). Also report the margin by which the frontier misses.
"""
import sys, json, gzip, random, statistics as st
from collections import defaultdict
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_harm_rescue as CHR

GATES = [
    ("conservative", 1.0, 0.10, 0.80),
    ("balanced", 2.0, 0.20, 0.80),
    ("token_efficient", 3.5, 0.30, 0.70),
]

by_rule = defaultdict(dict)  # rule_id -> env -> (drop, saving)
envs = set()
for r in CHR._load_dev_rows():
    env = (r["model"], r["benchmark"], r["seed"])
    envs.add(env)
    by_rule[r["rule_id"]][env] = (r["accuracy_drop_pp"], r["saving_fraction"])
envs = sorted(envs)
print(f"rules {len(by_rule)}  envs {len(envs)}")
full = {r: v for r, v in by_rule.items() if len(v) == len(envs)}
print(f"rules with all {len(envs)} envs: {len(full)}")

rule_ids = sorted(full)
mat = [[full[r][e] for e in envs] for r in rule_ids]


def gates_on(idx):
    out = {g[0]: 0 for g in GATES}
    best_safe = -9.0
    for row in mat:
        d = st.fmean(row[i][0] for i in idx)
        s = st.fmean(row[i][1] for i in idx)
        psf = st.fmean(1.0 if row[i][1] > 0 else 0.0 for i in idx)
        if d <= 1.0 and s > best_safe:
            best_safe = s
        for name, dc, sc, pc in GATES:
            if d <= dc and s >= sc and psf >= pc:
                out[name] += 1
    return out, best_safe


base_idx = list(range(len(envs)))
g, bs = gates_on(base_idx)
print(f"\npoint estimate: gates {g}  max saving @ drop<=1pp = {100*bs:.4f}%")

random.seed(20260808)
B = 2000
any_clear = 0
maxsav = []
percounts = {n: 0 for n, *_ in GATES}
for b in range(B):
    idx = [random.randrange(len(envs)) for _ in range(len(envs))]
    g, bs = gates_on(idx)
    maxsav.append(bs)
    for n in percounts:
        if g[n] > 0:
            percounts[n] += 1
    if any(g[n] > 0 for n in g):
        any_clear += 1
    if (b + 1) % 200 == 0:
        print(f"  {b+1}/{B} replicates, any-gate-nonempty so far: {any_clear}", flush=True)

maxsav.sort()
print(f"\nbootstrap B={B} over environments")
for n in percounts:
    print(f"  P(gate {n} non-empty) = {percounts[n]}/{B}")
print(f"  P(any gate non-empty)  = {any_clear}/{B}")
q = lambda p: 100 * maxsav[int(p * (B - 1))]
print(f"  max saving @ drop<=1pp: median {q(0.5):.3f}%  "
      f"95% CI [{q(0.025):.3f}%, {q(0.975):.3f}%]  max over replicates {100*maxsav[-1]:.3f}%")
print(f"  (the conservative gate needs 10%)")
