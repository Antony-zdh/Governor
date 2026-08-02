#!/usr/bin/env python3
"""Held-out (32B / Llama-8B) confirmation at 3 seeds (45/46/47).

Consensus only: the DEER confidence bank was not collected on these models.
For each held-out model: aggregate every consensus rule to macro (drop, saving)
over its 9 test environments (3 benchmarks x 3 seeds), report gate behaviour and
the frontier-reproduction correlation of the per-rule drop against dev.
"""
from __future__ import annotations

import glob
import json
import math
import statistics
import sys
from collections import defaultdict

SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
GATES = [("conservative", 1.0, 0.10, 0.80),
         ("balanced", 2.0, 0.20, 0.80),
         ("token_efficient", 3.5, 0.30, 0.70)]


def load(pat):
    return [json.loads(l) for f in glob.glob(pat) for l in open(f) if l.strip()]


def agg(rows, keep):
    by = defaultdict(list)
    for r in rows:
        if keep(r):
            by[str(r["rule_id"])].append(r)
    out = {}
    for rid, ev in by.items():
        d = statistics.fmean(float(e["accuracy_drop_pp"]) for e in ev)
        s = statistics.fmean(float(e["saving_fraction"]) for e in ev)
        p = sum(float(e["saving_fraction"]) > 0 for e in ev) / len(ev)
        out[rid] = (d, s, p, len(ev))
    return out


def pearson(a, b):
    k = list(set(a) & set(b))
    xs = [a[i][0] for i in k]; ys = [b[i][0] for i in k]
    mx = statistics.fmean(xs); my = statistics.fmean(ys)
    cov = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
    return cov/(sx*sy) if sx and sy else float("nan")


def main():
    heldout = load(sys.argv[1])          # heldout_sweep/shard_*.jsonl
    dev_rows = load(sys.argv[2])         # v2_sweep_r/shard_*.jsonl
    dev = agg(dev_rows, lambda r: r["split"] == "dev" and int(r["budget"]) == SEL[r["benchmark"]])

    selb = lambda r: int(r["budget"]) == SEL[r["benchmark"]]
    for tag, pred in (("Qwen-32B (scale)", lambda r: "32B" in r["model"]),
                      ("Llama-8B (arch/family)", lambda r: "Llama" in r["model"])):
        a = agg(heldout, lambda r, p=pred: p(r) and selb(r))
        nenv = next(iter(a.values()))[3] if a else 0
        print(f"\n### {tag} — {len(a)} rules, {nenv} env each (3 bench x 3 seeds)")
        print(f"  frontier reproduction: drop dev<->heldout r = {pearson(dev, a):.3f}")
        for gname, cap, floor, psf in GATES:
            passes = [v for v in a.values() if v[0] <= cap and v[1] >= floor and v[2] >= psf]
            capd = [v for v in a.values() if v[0] <= cap]
            best = max(capd, key=lambda v: v[1]) if capd else None
            msg = f"  [{gname}] consensus_pass={len(passes)}"
            if best:
                msg += f" | max saving within drop<= {cap}: {best[1]*100:.1f}% (drop {best[0]:.2f}pp)"
            print(msg)


if __name__ == "__main__":
    main()
