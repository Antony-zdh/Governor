#!/usr/bin/env python3
"""Where consensus forms, and whether it is right when it does (paper §4.1).

For every dev-split trajectory we find the FIRST time a window of `W` recent
non-empty probes all agree, and record:

  * the token position at which that happened,
  * that position as a FRACTION of the trajectory's own full length -- which
    normalises away problem difficulty, so a consensus at 500 tokens on a
    600-token problem is correctly read as "late", not "early",
  * whether the agreed answer is correct,
  * whether the trajectory's own final answer is correct.

The gap between those last two is the accuracy a stop at that moment would
throw away.

Output: report/figures/gen/consensus_position_cache.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
GOV = FC / "governor_v2"
RES = FC / "results"
CACHE = HERE / "figures" / "gen" / "consensus_position_cache.json"

sys.path.insert(0, str(GOV))
import replay_rules as RR  # noqa: E402

SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
DEVID = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
WINDOW = 3          # "three consecutive agreeing probes" -- the §4.1 heuristic
REL_BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0]
ABS_BINS = [0, 512, 1024, 2048, 4096, 10**9]
ABS_LABELS = ["<512", "512–1k", "1k–2k", "2k–4k", ">4k"]


def rel_label(i):
    lo, hi = REL_BINS[i], REL_BINS[i + 1]
    return f"{lo:.0%}–{hi:.0%}".replace("%", "")


def first_consensus(probes, window=WINDOW):
    """(token_position, answer) of the first full window of agreeing non-empty
    probes, or None. Empty/invalid probes break the run, matching the sweep's
    window_share semantics with s = 1.0."""
    run_ans, run_n, run_start = None, 0, None
    for pr in sorted(probes, key=lambda z: int(z["token_position"])):
        a = RR.normalize_answer(pr.get("probe_answer"))
        pos = int(pr["token_position"])
        if not a:
            run_ans, run_n, run_start = None, 0, None
            continue
        if a == run_ans:
            run_n += 1
        else:
            run_ans, run_n, run_start = a, 1, pos
        if run_n >= window:
            return pos, run_ans, run_start
    return None


def main():
    split_map = RR.load_split_map(GOV / "generated/split_manifest.json")
    recs = []
    for main_run in RR.discover_runs(RES / "governor_v2", "development"):
        manifest = json.loads((main_run / "run_manifest.json").read_text())
        s = manifest["run_settings"]
        if s["model"] not in DEVID:
            continue
        bench = s["dataset"]
        budget = SEL[bench]
        n_env = 0
        for tp in sorted((main_run / "traj").glob("problem_*.json")):
            traj = json.loads(tp.read_text(encoding="utf-8"))
            pid = int(traj["problem_id"])
            if split_map.get((bench, pid)) != "dev":
                continue
            probes = [p for p in RR.load_probes(main_run, pid)
                      if int(p["token_position"]) <= budget]
            total = min(int(traj["tokens_used"]), budget)
            final_ok = RR.answers_equal(traj.get("final_answer"), traj["target"])
            hit = first_consensus(probes)
            rec = {"model": s["model"], "benchmark": bench,
                   "seed": int(s.get("seed", s.get("base_seed", -1))),
                   "problem_id": pid, "total_tokens": total,
                   "final_correct": bool(final_ok), "formed": hit is not None}
            if hit:
                pos, ans, start = hit
                rec.update({
                    "position": pos,
                    "rel_position": (pos / total) if total else None,
                    "consensus_correct": bool(RR.answers_equal(ans, traj["target"])),
                })
            recs.append(rec)
            n_env += 1
        print(f"  {bench:<8} {s['model'].split('/')[-1]:<28} "
              f"seed {s.get('seed', s.get('base_seed'))}: {n_env} dev problems",
              flush=True)

    formed = [r for r in recs if r["formed"] and r.get("rel_position") is not None]
    print(f"\n{len(recs)} dev trajectories; consensus (W={WINDOW}, s=1.0) forms in "
          f"{len(formed)} ({len(formed)/len(recs):.1%})")

    def bucket(key, edges, labels=None):
        out = []
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            sel = [r for r in formed if lo <= r[key] < hi] if i < len(edges) - 2 \
                else [r for r in formed if lo <= r[key] <= hi]
            if not sel:
                out.append(None)
                continue
            out.append({
                "label": labels[i] if labels else rel_label(i),
                "n": len(sel),
                "consensus_acc": st.fmean(r["consensus_correct"] for r in sel) * 100,
                "final_acc": st.fmean(r["final_correct"] for r in sel) * 100,
                "lo": lo, "hi": hi,
            })
        return out

    res = {
        "meta": {"window": WINDOW, "split": "dev", "n_trajectories": len(recs),
                 "n_formed": len(formed),
                 "overall_final_acc": st.fmean(r["final_correct"] for r in recs) * 100,
                 "formed_final_acc": st.fmean(r["final_correct"] for r in formed) * 100,
                 "formed_consensus_acc": st.fmean(r["consensus_correct"] for r in formed) * 100},
        "relative": [b for b in bucket("rel_position", REL_BINS) if b],
        "absolute": [b for b in bucket("position", ABS_BINS, ABS_LABELS) if b],
        "scatter": [{"rel": r["rel_position"], "ok": r["consensus_correct"],
                     "final_ok": r["final_correct"], "benchmark": r["benchmark"]}
                    for r in formed],
    }

    print("\nby RELATIVE position (fraction of the trajectory generated):")
    for b in res["relative"]:
        print(f"  {b['label']:>9}  n={b['n']:>4}  consensus answer correct "
              f"{b['consensus_acc']:5.1f}%   vs run-to-completion {b['final_acc']:5.1f}%"
              f"   (gap {b['final_acc']-b['consensus_acc']:5.1f} pp)")
    print("\nby ABSOLUTE position (tokens):")
    for b in res["absolute"]:
        print(f"  {b['label']:>9}  n={b['n']:>4}  consensus {b['consensus_acc']:5.1f}%"
              f"   final {b['final_acc']:5.1f}%")
    print(f"\noverall: consensus-at-stop {res['meta']['formed_consensus_acc']:.1f}%  "
          f"vs run-to-completion {res['meta']['formed_final_acc']:.1f}%")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(res, indent=1))
    print("wrote", CACHE)


if __name__ == "__main__":
    main()
