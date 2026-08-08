"""B2b: extend the search grid past its edges and see whether the safe corner
opens up.

The dev Pareto frontier's low-drop end is entirely W=24/30 at s=1.0, i.e. the
MAXIMUM of the window axis. The truncated-search attack says: keep going and
you will find a rule that clears the conservative gate. Test it by replaying
window sizes and maturity floors BEYOND the preregistered grid, on the same
frozen dense_simple32 dev stream through the same validated replay path.

Grid extension (consensus_fixed, s=1.0, certainty off):
  W        30 (control, in-grid) 40 50 64 96 128 192 256
  maturity 0 512 4096 (in-grid) 8192 12288 (out of grid)
  interval 64 128 256 512 (in-grid; finer probing is the only way to keep a
           long window from consuming the whole trajectory)
  validity nonempty, schema
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

WS = [30, 40, 50, 64, 96, 128, 192, 256]
MATS = [0, 512, 4096, 8192, 12288]
INTERVALS = [64, 128, 256, 512]
VALIDITY = ["nonempty", "schema"]

_CACHE = []
_RULES = {}


def build_cache():
    split_map = RR.load_split_map(FC / "governor_v2/generated/split_manifest.json")
    cache = []
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
    return {"rule_id": rid,
            "drop": st.fmean(r[0] for r in rows),
            "saving": st.fmean(r[1] for r in rows),
            "psf": st.fmean(r[2] for r in rows),
            "stop_rate": None}


if __name__ == "__main__":
    import multiprocessing as mp; mp.set_start_method("fork", force=True)

    # template: an in-grid consensus_fixed rule, s=1.0, certainty off
    tmpl = None
    with gzip.open(FC / "results/governor_v2_ws_sweep/candidate_rules_v2.jsonl.gz", "rt") as f:
        for line in f:
            d = json.loads(line); av = d["metadata"]["axis_values"]
            if (d["metadata"]["template"] == "consensus_fixed"
                    and av.get("evidence.window_probes") == 30
                    and av.get("evidence.dominant_share_threshold") == 1.0
                    and av.get("maturity.minimum_tokens") == 512
                    and av.get("probe.schedule.interval_tokens") == 128
                    and av.get("validity.mode") == "nonempty"
                    and av.get("certainty.enabled") is False):
                tmpl = d
                break
    assert tmpl is not None

    for W in WS:
        for M in MATS:
            for I in INTERVALS:
                for V in VALIDITY:
                    r = copy.deepcopy(tmpl)
                    r["evidence"]["window_probes"] = W
                    r["maturity"]["minimum_tokens"] = M
                    r["probe"]["schedule"]["interval_tokens"] = I
                    r["probe"]["schedule"]["start_token"] = I
                    r["validity"]["mode"] = V
                    rid = f"ext__W{W}__M{M}__I{I}__{V}"
                    r["rule_id"] = rid
                    r["metadata"] = {"template": "consensus_fixed_extended",
                                     "axis_values": {"evidence.window_probes": W,
                                                     "maturity.minimum_tokens": M,
                                                     "probe.schedule.interval_tokens": I,
                                                     "validity.mode": V,
                                                     "evidence.dominant_share_threshold": 1.0,
                                                     "certainty.enabled": False}}
                    _RULES[rid] = r
    print(f"extended grid: {len(_RULES)} rules "
          f"({sum(1 for k in _RULES if int(k.split('__')[1][1:]) > 30 or int(k.split('__')[2][1:]) > 4096)} outside the preregistered grid)")

    _CACHE[:] = build_cache()
    ids = sorted(_RULES)
    out = {}
    with Pool(processes=10) as pool:
        for i, rec in enumerate(pool.imap_unordered(_replay, ids, chunksize=4), 1):
            out[rec["rule_id"]] = rec
            if i % 60 == 0 or i == len(ids):
                print(f"  replayed {i}/{len(ids)}", flush=True)

    gates = {n: [r for r in out.values()
                 if r["drop"] <= d and r["saving"] >= s and r["psf"] >= p]
             for n, d, s, p in GATES}
    print("\n=== extended-grid gate clearers ===")
    for n, v in gates.items():
        print(f"  {n}: {len(v)}")
        for r in sorted(v, key=lambda x: -x["saving"])[:5]:
            print(f"      {r['rule_id']}  drop {r['drop']:.3f}pp saving {100*r['saving']:.2f}% psf {r['psf']:.2f}")

    safe = [r for r in out.values() if r["drop"] <= 1.0]
    print(f"\nrules with drop <= 1.0pp: {len(safe)}")
    if safe:
        b = max(safe, key=lambda r: r["saving"])
        print(f"  best saving among them: {100*b['saving']:.3f}%  ({b['rule_id']}, drop {b['drop']:.3f}pp)")

    print("\n=== best (lowest drop) per window size, over maturity/interval/validity ===")
    print(f"{'W':>5} {'min drop':>9} {'its saving':>11} | {'max saving @ drop<=1pp':>22}")
    for W in WS:
        sub = [r for r in out.values() if r["rule_id"].split("__")[1] == f"W{W}"]
        lo = min(sub, key=lambda r: r["drop"])
        sf = [r for r in sub if r["drop"] <= 1.0]
        bs = f"{100*max(r['saving'] for r in sf):.3f}%" if sf else "none under 1pp"
        print(f"{W:>5} {lo['drop']:9.3f} {100*lo['saving']:10.3f}% | {bs:>22}")

    json.dump({k: {kk: vv for kk, vv in v.items() if kk != 'stop_rate'}
               for k, v in out.items()},
              open("/private/tmp/claude-501/-Users-antonyzhao-code-Governor/"
                   "00f2fc89-a89f-4be7-b854-293ba45bf9f0/scratchpad/b2_extended.json", "w"),
              indent=1)
