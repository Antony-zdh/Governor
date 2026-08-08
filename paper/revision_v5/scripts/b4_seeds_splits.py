"""B4: are the 18 "environments" really 18, and are the splits clean?

(a) Split integrity: train/dev/test problem-id sets disjoint per benchmark, and
    the held-out models scored on the same ids as the dev models.
(b) Seed independence: the 18 environments are 6 (model x benchmark) cells x 3
    seeds. If seeds are near-duplicates, macro-over-18 carries the precision of
    6, and every macro standard error in the paper (and my A2 bootstrap) is
    overstated. Decompose per-rule drop variance into between-cell and
    within-cell(seed) components and report the intraclass correlation.
"""
import sys, json, gzip, statistics as st
from collections import defaultdict
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_harm_rescue as CHR
import replay_rules as RR

# ---------- (a) splits ----------
man = json.loads((FC / "governor_v2/generated/split_manifest.json").read_text())
print("=== B4a split integrity ===")
sets = defaultdict(lambda: defaultdict(set))
hashes = defaultdict(dict)
for a in man["assignments"]:
    sets[a["benchmark"]][a["split"]].add(str(a["problem_id"]))
    hashes[a["benchmark"]][str(a["problem_id"])] = a.get("content_hash")
for bench in sorted(sets):
    s = sets[bench]; ks = sorted(s)
    tot = sum(len(s[k]) for k in ks); uni = len(set().union(*s.values()))
    print(f"  {bench:8s} " + "  ".join(f"{k}={len(s[k])}" for k in ks) +
          f"   total={tot} union={uni} " + ("OK disjoint" if tot == uni else "*** OVERLAP ***"))
    for i, a in enumerate(ks):
        for b in ks[i+1:]:
            ov = s[a] & s[b]
            if ov:
                print(f"      *** {a} n {b}: {sorted(ov)[:10]} ({len(ov)})")
    hs = [h for h in hashes[bench].values() if h]
    dup = len(hs) - len(set(hs))
    print(f"           content_hash duplicates within benchmark: {dup}")

# ---------- (b) seeds ----------
print("\n=== B4b seed independence ===")
# per-problem trajectory agreement across seeds
agree_pairs = defaultdict(lambda: [0, 0])
tok = defaultdict(dict)
for main_run in RR.discover_runs(FC / "results/governor_v2", "development"):
    s = json.loads((main_run / "run_manifest.json").read_text())["run_settings"]
    if s["model"] not in CHR.DEVID:
        continue
    key = (s["model"], s["dataset"])
    seed = int(s.get("seed", s.get("base_seed", -1)))
    for tp in (main_run / "traj").glob("problem_*.json"):
        t = json.loads(tp.read_text())
        tok[key].setdefault(int(t["problem_id"]), {})[seed] = (
            int(t["tokens_used"]), RR.normalize_answer(t.get("final_answer")))

for key, per_pid in sorted(tok.items()):
    same_ans = tot = 0
    tokrel = []
    for pid, bys in per_pid.items():
        seeds = sorted(bys)
        for i, a in enumerate(seeds):
            for b in seeds[i+1:]:
                tot += 1
                same_ans += bys[a][1] == bys[b][1]
                m = max(bys[a][0], bys[b][0])
                tokrel.append(abs(bys[a][0] - bys[b][0]) / m if m else 0.0)
    print(f"  {key[0].split('/')[-1]:28s} {key[1]:8s} n={len(per_pid):3d}  "
          f"seed-pairs with identical final answer {100*same_ans/tot:5.1f}%   "
          f"median |token diff|/max {100*st.median(tokrel):5.1f}%")

# ICC of per-rule drop across seeds within cell
rows = defaultdict(dict)
for r in CHR._load_dev_rows():
    rows[r["rule_id"]][(r["model"], r["benchmark"], r["seed"])] = r["accuracy_drop_pp"]
cells = defaultdict(list)
for env in next(iter(rows.values())):
    cells[(env[0], env[1])].append(env)

between, within = [], []
for rid, per_env in rows.items():
    cm = {c: st.fmean(per_env[e] for e in es) for c, es in cells.items()}
    gm = st.fmean(cm.values())
    between.append(st.fmean((v - gm) ** 2 for v in cm.values()))
    w = []
    for c, es in cells.items():
        if len(es) > 1:
            w.append(st.fmean((per_env[e] - cm[c]) ** 2 for e in es))
    within.append(st.fmean(w))
B_, W_ = st.fmean(between), st.fmean(within)
print(f"\n  per-rule drop variance decomposition over {len(rows)} rules, "
      f"{len(cells)} cells x 3 seeds")
print(f"    mean between-cell variance : {B_:8.3f}")
print(f"    mean within-cell (seed) var: {W_:8.3f}")
print(f"    ICC = between/(between+within) = {B_/(B_+W_):.4f}")
print(f"    effective #independent environments ~= "
      f"{18 / (1 + 2*B_/(B_+W_)):.2f}  (18 if seeds independent, 6 if identical)")
