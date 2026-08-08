#!/usr/bin/env python3
"""A4: does DEER's headline saving survive excluding budget-hitting trajectories?

Budget-hitters (baseline never finished within the selection budget) are scored
baseline_correct=False and baseline_tokens=budget. Any early stop on them is
pure free saving with zero possible accuracy cost. If they carry a
disproportionate share of baseline tokens, DEER's saving is partly an artifact
of the truncation, not of early exit.

Recompute DEER dev macro drop / saving at every threshold, all problems vs
non-capped only.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(ROOT / "governor_v2")); sys.path.insert(0, str(ROOT / "related_work"))

import deer_threshold_sweep as D
from replay_rules import load_split_map

protocol = json.loads((ROOT / "governor_v2/protocol_v2.json").read_text())
budgets = D.selection_budgets(protocol)
split_map = load_split_map(ROOT / "governor_v2/generated/split_manifest.json")
bank = ROOT / "results/related_work/deer_confidence_bank_cap30/full"
main_root = ROOT / "results/governor_v2"

# per env: threshold -> (rows for dev split)
env_rows: dict[str, dict[float, list]] = {}
for env_dir in sorted(bank.iterdir()):
    if not env_dir.is_dir():
        continue
    model_key, benchmark, seed_tag = env_dir.name.split("__")
    seed = int(seed_tag.replace("seed_", ""))
    budget = budgets[benchmark]
    main_run = main_root / f"development__{D.SLUG[model_key]}__{benchmark}__seed_{seed}" / "main"
    main_index = D.load_main_index(main_run)
    records = {int(r["problem_id"]): r for r in D.iter_bank(env_dir)}
    baseline_index = {}
    for pid, m in main_index.items():
        complete = m["finished_naturally"] and m["tokens_used"] <= budget
        baseline_index[pid] = {
            "baseline_complete": complete,
            "baseline_correct": (D.eq(m["final_answer"], m["target"])
                                 if complete and m["final_answer"] is not None else False),
            "baseline_tokens": min(m["tokens_used"], budget),
        }
    dev_pids = [p for p in records if split_map.get((benchmark, p)) == "dev"]
    per_thr = {}
    for thr in D.THRESHOLDS:
        per_thr[thr] = [
            D.replay_problem(records[p], main_index[p], baseline_index[p], thr, budget)
            for p in sorted(dev_pids)
        ]
    env_rows[env_dir.name] = per_thr
    sys.stderr.write(f"{env_dir.name}: dev n={len(dev_pids)}\n")

from replay_rules import summarize


def macro(thr, keep):
    drops, savs, stops = [], [], []
    ns = 0
    for name, per_thr in env_rows.items():
        vals = [v for v in per_thr[thr] if keep(v)]
        if not vals:
            continue
        s = summarize(vals)
        drops.append(s["accuracy_drop_pp"]); savs.append(s["saving_fraction"])
        stops.append(s["stop_rate"]); ns += s["n"]
    return (sum(drops)/len(drops), 100*sum(savs)/len(savs), 100*sum(stops)/len(stops), ns)


print(f"{'thr':>10} | {'ALL: drop':>9} {'saving':>8} {'n':>5} | {'NO-CAP: drop':>12} {'saving':>8} {'n':>5} | dsav")
for thr in D.THRESHOLDS:
    a = macro(thr, lambda v: True)
    b = macro(thr, lambda v: not v["capped"])
    print(f"{thr:>10g} | {a[0]:9.3f} {a[1]:7.2f}% {a[3]:5d} | {b[0]:12.3f} {b[1]:7.2f}% {b[3]:5d} | {b[1]-a[1]:+6.2f}")

# token share carried by capped trajectories, macro over envs
shares = []
for name, per_thr in env_rows.items():
    vals = per_thr[D.THRESHOLDS[0]]
    tot = sum(v["baseline_decode_tokens"] for v in vals)
    cap = sum(v["baseline_decode_tokens"] for v in vals if v["capped"])
    shares.append((name, 100*sum(1 for v in vals if v["capped"])/len(vals), 100*cap/tot))
print("\nper-env capped rate / capped share of baseline tokens (dev):")
for n, r, s in sorted(shares, key=lambda x: -x[2]):
    print(f"  {n:52s} {r:6.2f}%  {s:6.2f}%")
print(f"  macro: capped {sum(x[1] for x in shares)/len(shares):.2f}%  token share {sum(x[2] for x in shares)/len(shares):.2f}%")
