#!/usr/bin/env python3
"""Test-split + held-out confirmation of the v2 gates for consensus and DEER."""
from __future__ import annotations

import glob
import json
import statistics
import sys
from collections import defaultdict

SELBUDGET = {"math500": 16384, "amc23": 16384, "aime24": 32768}
GATES = [
    ("conservative", 1.0, 0.10, 0.80),
    ("balanced", 2.0, 0.20, 0.80),
    ("token_efficient", 3.5, 0.30, 0.70),
]
DEV_MODELS = {
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "Qwen/Qwen3-8B",
}


def load(paths):
    for f in paths:
        for line in open(f, encoding="utf-8"):
            if line.strip():
                yield json.loads(line)


def sel_rows(rows):
    for r in rows:
        if int(r["budget"]) == SELBUDGET[r["benchmark"]]:
            yield r


def agg(rows):
    by = defaultdict(list)
    for r in rows:
        by[str(r["rule_id"])].append(r)
    out = {}
    for rid, envs in by.items():
        d = [float(e["accuracy_drop_pp"]) for e in envs]
        s = [float(e["saving_fraction"]) for e in envs]
        out[rid] = (
            statistics.fmean(d),
            statistics.fmean(s),
            sum(x > 0 for x in s) / len(s),
            str(envs[0].get("method", "consensus")),
            len(envs),
        )
    return out


def gate_report(name, a):
    print(f"\n### {name} (n_rules={len(a)})")
    cons = {k: v for k, v in a.items() if v[3] != "deer_direct_submit"}
    deer = {k: v for k, v in a.items() if v[3] == "deer_direct_submit"}
    for gname, cap, floor, psf in GATES:
        def passes(v):
            return v[0] <= cap and v[1] >= floor and v[2] >= psf
        cp = [v for v in cons.values() if passes(v)]
        dp = [(k, v) for k, v in deer.items() if passes(v)]
        # best consensus saving within the drop cap (diagnostic)
        capd = [v for v in cons.values() if v[0] <= cap]
        best_cap = max(capd, key=lambda v: v[1]) if capd else None
        line = f"  [{gname}] consensus_pass={len(cp)}"
        if deer:
            line += f"  deer_pass={len(dp)}"
        print(line)
        if best_cap:
            print(f"       consensus best saving within drop<= {cap}: {best_cap[1]*100:.1f}% (drop {best_cap[0]:.2f}pp)")
        if dp:
            dp.sort(key=lambda kv: -kv[1][1])
            k, v = dp[0]
            print(f"       DEER best: {k} drop={v[0]:.2f}pp save={v[1]*100:.1f}% psf={v[2]:.2f}")


def main():
    test_files = glob.glob(sys.argv[1])
    deer_file = sys.argv[2] if len(sys.argv) > 2 else None
    rows = list(sel_rows(load(test_files)))

    dev_rows = [r for r in rows if r["model"] in DEV_MODELS]
    b32 = [r for r in rows if "32B" in r["model"]]
    llama = [r for r in rows if "Llama" in r["model"]]

    deer_test = []
    if deer_file:
        deer_test = [r for r in load([deer_file]) if r["split"] == "test"]

    gate_report("TEST, dev models (7B+Qwen3, seeds45-47) + DEER", agg(dev_rows + deer_test))
    gate_report("HELD-OUT scale: Qwen-32B (seed45)", agg(b32))
    gate_report("HELD-OUT arch/family: Llama-8B (seed45)", agg(llama))


if __name__ == "__main__":
    main()
