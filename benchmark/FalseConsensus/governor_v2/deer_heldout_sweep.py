#!/usr/bin/env python3
"""DEER threshold sweep on the held-out 32B / Llama-8B confidence bank.

Reuses deer_threshold_sweep helpers; joins the heldout bank (test scope, 3 seeds)
with the confirmation main trajectories and prints, per held-out model, the DEER
threshold frontier (macro over 9 envs) and gate pass counts.
"""
from __future__ import annotations
import glob, json, statistics, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deer_threshold_sweep import (THRESHOLDS, direct_submit_decision, eq,
                                   replay_problem, iter_bank, selection_budgets)
from replay_rules import load_split_map

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BANK = REPO / "results/related_work/deer_confidence_bank_cap30_heldout/test"
MAIN = REPO / "results/governor_v2"
MODELS = {
    "qwen32b": ("Qwen-32B (scale)", "deepseek-ai-deepseek-r1-distill-qwen-32b"),
    "llama8b": ("Llama-8B (arch/family)", "deepseek-ai-deepseek-r1-distill-llama-8b"),
}
GATES = [("conservative",1.0,0.10,0.80),("balanced",2.0,0.20,0.80),("token_efficient",3.5,0.30,0.70)]


def load_main(main_run):
    idx={}
    for p in (main_run/"traj").glob("problem_*.json"):
        t=json.loads(p.read_text()); idx[int(t["problem_id"])]={
            "target":t["target"],"final_answer":t.get("final_answer"),
            "tokens_used":int(t["tokens_used"]),"finished_naturally":bool(t["finished_naturally"])}
    return idx


def main():
    protocol=json.loads((HERE/"protocol_v2.json").read_text())
    budgets=selection_budgets(protocol)
    split_map=load_split_map(HERE/"generated/split_manifest.json")
    for key,(label,slug) in MODELS.items():
        # env rows: threshold -> list of per-env (drop, saving, psf-contrib)
        per_thr=defaultdict(list)
        for env_dir in sorted(BANK.glob(f"{key}__*__seed_*")):
            _,benchmark,seedtag=env_dir.name.split("__")
            seed=int(seedtag.replace("seed_","")); budget=budgets[benchmark]
            main_run=MAIN/f"confirmation__{slug}__{benchmark}__seed_{seed}"/"main"
            mainidx=load_main(main_run)
            recs={int(r["problem_id"]):r for r in iter_bank(env_dir)}
            base={}
            for pid,m in mainidx.items():
                comp=m["finished_naturally"] and m["tokens_used"]<=budget
                base[pid]={"baseline_complete":comp,
                    "baseline_correct":(eq(m["final_answer"],m["target"]) if comp and m["final_answer"] is not None else False),
                    "baseline_tokens":min(m["tokens_used"],budget)}
            for thr in THRESHOLDS:
                vals=[replay_problem(recs[pid],mainidx[pid],base[pid],thr,budget) for pid in recs]
                bl=statistics.fmean(v["baseline_decode_tokens"] for v in vals)
                tot=statistics.fmean(v["total_decode_tokens"] for v in vals)
                drop=100*(statistics.fmean(v["baseline_correct"] for v in vals)-statistics.fmean(v["correct"] for v in vals))
                sav=(bl-tot)/bl if bl else 0.0
                per_thr[thr].append((drop,sav))
        print(f"\n### {label} — DEER threshold frontier (macro over {len(per_thr[THRESHOLDS[0]])} env)")
        frontier=[]
        for thr in sorted(per_thr,reverse=True):
            rows=per_thr[thr]; d=statistics.fmean(x[0] for x in rows); s=statistics.fmean(x[1] for x in rows)
            psf=sum(x[1]>0 for x in rows)/len(rows); frontier.append((thr,d,s,psf))
            print(f"  tau={thr:g}  drop={d:6.2f}pp  save={s*100:5.1f}%  psf={psf:.2f}")
        for g,cap,fl,ps in GATES:
            ok=[(t,d,s,p) for (t,d,s,p) in frontier if d<=cap and s>=fl and p>=ps]
            best=max(ok,key=lambda z:z[2]) if ok else None
            print(f"  [{g}] pass={len(ok)}"+(f"  best tau={best[0]:g} drop={best[1]:.2f} save={best[2]*100:.1f}%" if best else ""))


if __name__=="__main__":
    main()
