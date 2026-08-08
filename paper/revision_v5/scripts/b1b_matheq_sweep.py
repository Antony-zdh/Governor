"""B1b: re-run the whole 3,520-rule sweep with MATH-equality consensus.

replay_rules compares probe answers as strings. B1 measured that 2.82% of the
adjacent string switches (0.81% of all transitions) are actually math-equal, and
25.6% of problems contain at least one collapsible pair. Small, but the only way
to settle whether the empty safe corner is a parsing artifact is to remove the
artifact and re-run.

Method: per problem, cluster the observed probe answers into math-equivalence
classes and rewrite every probe answer to its class representative (frozen data
is copied, never mutated). String-equality consensus over the canonicalised
stream IS math-equality consensus. Then replay the committed 3,520-rule grid.
"""
import sys, gzip, json, copy, statistics as st
from multiprocessing import Pool
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_boundary_consensus_v5 as B
import replay_rules as RR
from replay_rules import RuleSpec

GATES = [("conservative", 1.0, 0.10, 0.80),
         ("balanced", 2.0, 0.20, 0.80),
         ("token_efficient", 3.5, 0.30, 0.70)]

_CACHE = []
_RULES = {}
_pc = {}


def meq(a, b):
    if a == b:
        return True
    k = (a, b) if a <= b else (b, a)
    v = _pc.get(k)
    if v is None:
        v = B._eq_hardkill(a, b)
        _pc[k] = v
    return v


def build_cache(canonicalise: bool):
    split_map = RR.load_split_map(FC / "governor_v2/generated/split_manifest.json")
    cache = []
    collapsed = 0
    for main_run in RR.discover_runs(FC / "results/governor_v2", "development"):
        s = json.loads((main_run / "run_manifest.json").read_text())["run_settings"]
        if s["model"] not in B.DEVID:
            continue
        bench = str(s["dataset"]); budget = B.SEL[bench]
        items = []
        for traj_path in sorted((main_run / "traj").glob("problem_*.json")):
            traj = json.loads(traj_path.read_text(encoding="utf-8"))
            pid = int(traj["problem_id"])
            if split_map.get((bench, pid)) != "dev":
                continue
            probes = RR.load_probes(main_run, pid)
            if not probes:
                continue
            if canonicalise:
                distinct = list(dict.fromkeys(
                    RR.normalize_answer(p.get("probe_answer")) for p in probes))
                reps, canon = [], {}
                for a in distinct:
                    if not a:
                        canon[a] = a
                        continue
                    for r in reps:
                        if meq(a, r):
                            canon[a] = r
                            break
                    else:
                        reps.append(a); canon[a] = a
                if sum(1 for a in distinct if a and canon[a] != a):
                    collapsed += 1
                probes = [dict(p, probe_answer=canon[RR.normalize_answer(
                    p.get("probe_answer"))]) for p in probes]
            corr = {}
            for pr in probes:
                a = RR.normalize_answer(pr.get("probe_answer"))
                if a and a not in corr:
                    corr[a] = B._eq_hardkill(a, traj["target"])
            base_ok = (B._eq_hardkill(traj["final_answer"], traj["target"])
                       if "final_answer" in traj else bool(traj["final_correct"]))
            items.append((traj, probes, corr, base_ok))
        cache.append((bench, budget, items))
        print(f"  cached {bench:8s} {s['model'].split('/')[-1]:28s}: {len(items)}", flush=True)
    print(f"  problems whose answer stream was collapsed: {collapsed}", flush=True)
    return cache


def _replay(rid):
    rule = RuleSpec.from_dict(_RULES[rid])
    rows = []
    for bench, budget, items in _CACHE:
        if not items:
            continue
        vals = [RR.replay_one(t, p, rule, bench, budget, probes_are_scheduled=False,
                              answer_correctness=c, baseline_answer_correctness=b)
                for t, p, c, b in items]
        base = st.fmean(v["baseline_correct"] for v in vals)
        acc = st.fmean(v["correct"] for v in vals)
        bl = st.fmean(v["baseline_decode_tokens"] for v in vals)
        tot = st.fmean(v["total_decode_tokens"] for v in vals)
        sav = (bl - tot) / bl if bl else 0.0
        rows.append((100 * (base - acc), sav, 1.0 if sav > 0 else 0.0))
    return {"rule_id": rid, "drop": st.fmean(r[0] for r in rows),
            "saving": st.fmean(r[1] for r in rows), "psf": st.fmean(r[2] for r in rows)}


def report(out, label):
    gates = {n: [r for r in out.values()
                 if r["drop"] <= d and r["saving"] >= s and r["psf"] >= p]
             for n, d, s, p in GATES}
    safe = [r for r in out.values() if r["drop"] <= 1.0]
    print(f"\n=== {label} ===")
    print(f"  gates: " + "  ".join(f"{n}={len(v)}" for n, v in gates.items()))
    print(f"  rules with drop <= 1.0pp: {len(safe)}")
    if safe:
        b = max(safe, key=lambda r: r["saving"])
        print(f"  max saving among them: {100*b['saving']:.4f}%  ({b['rule_id']}, "
              f"drop {b['drop']:.4f}pp)")
    for thr in (0.10, 0.20, 0.30):
        c = [r["drop"] for r in out.values() if r["saving"] >= thr]
        print(f"  min drop at >={int(100*thr)}% saving: "
              f"{min(c):.4f}pp" if c else f"  none reach {int(100*thr)}%")
    return gates


if __name__ == "__main__":
    import multiprocessing as mp; mp.set_start_method("fork", force=True)
    with gzip.open(FC / "results/governor_v2_ws_sweep/candidate_rules_v2.jsonl.gz", "rt") as f:
        for line in f:
            d = json.loads(line)
            _RULES[d["rule_id"]] = d
    ids = sorted(_RULES)
    print(f"rules: {len(ids)}")

    for canon, label in [(False, "STRING-equality consensus (control = committed method)"),
                         (True, "MATH-equality consensus (B1 counterfactual)")]:
        print(f"\n--- building cache, canonicalise={canon} ---", flush=True)
        _CACHE[:] = build_cache(canon)
        out = {}
        with Pool(processes=10) as pool:
            for i, rec in enumerate(pool.imap_unordered(_replay, ids, chunksize=8), 1):
                out[rec["rule_id"]] = rec
                if i % 800 == 0 or i == len(ids):
                    print(f"  replayed {i}/{len(ids)}", flush=True)
        report(out, label)
        json.dump(out, open(f"/private/tmp/claude-501/-Users-antonyzhao-code-Governor/"
                            f"00f2fc89-a89f-4be7-b854-293ba45bf9f0/scratchpad/"
                            f"b1b_{'math' if canon else 'string'}.json", "w"))
