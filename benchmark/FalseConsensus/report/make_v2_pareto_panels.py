#!/usr/bin/env python3
"""Generate the 8 v2 Pareto panels: 3 splits + 3 benchmarks + 2 models.

Each panel plots every consensus rule as (macro accuracy drop, macro net saving)
over the panel's environment subset, the consensus dev/subset Pareto frontier,
the DEER threshold frontier, and the three gate regions.
"""
from __future__ import annotations

import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SB = "/private/tmp/claude-501/-Users-antonyzhao-code-Governor/c0818fb1-6756-48d4-ab8d-4610ead6f681/scratchpad"
OUT = REPO / "paper/figures/panels"
SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
DEV_MODELS = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
GATES = [("conservative", 1.0, 0.10, "#16a34a"),
         ("balanced", 2.0, 0.20, "#2563eb"),
         ("token_efficient", 3.5, 0.30, "#9333ea")]


def load(files):
    return [json.loads(l) for f in glob.glob(files) for l in open(f) if l.strip()]


def macro(rows, keep):
    by = defaultdict(list)
    for r in rows:
        if keep(r):
            by[str(r["rule_id"])].append(r)
    out = {}
    for rid, ev in by.items():
        d = [float(e["accuracy_drop_pp"]) for e in ev]
        s = [float(e["saving_fraction"]) for e in ev]
        out[rid] = (statistics.fmean(d), statistics.fmean(s) * 100.0,
                    str(ev[0].get("method", "consensus")))
    return out


def frontier(pts):
    pts = sorted(pts, key=lambda t: (t[0], -t[1]))
    fr, best = [], float("-inf")
    for d, s in pts:
        if s > best:
            fr.append((d, s)); best = s
    return fr


def panel(ax, cons, deer, title):
    for name, cap, floor, c in GATES:
        ax.add_patch(Rectangle((0, floor * 100), cap, 100 - floor * 100,
                     facecolor=c, alpha=0.06, edgecolor=c, lw=0.8, ls="--", zorder=1))
    cp = [(d, s) for d, s, _ in cons.values()]
    ax.scatter([d for d, s in cp], [s for d, s in cp], s=5, c="#b8bcc4",
               alpha=0.5, linewidths=0, zorder=2, label=f"consensus (n={len(cp)})")
    cf = frontier(cp)
    ax.step([d for d, s in cf], [s for d, s in cf], where="post",
            color="#dc2626", lw=1.4, zorder=4, label="consensus frontier")
    dp = sorted([(d, s) for d, s, _ in deer.values()], key=lambda t: t[0])
    if dp:
        ax.plot([d for d, s in dp], [s for d, s in dp], "-D", color="#059669",
                ms=4, lw=1.4, zorder=5, label="DEER")
    ax.set_xlim(-1, 30); ax.set_ylim(-5, 75)
    ax.axhline(0, color="#ddd", lw=0.6, zorder=0)
    ax.set_xlabel("total accuracy drop (pp)"); ax.set_ylabel("net token saving (%)")
    ax.set_title(title, fontsize=10)
    ax.legend(loc="lower right", fontsize=7, framealpha=0.95)
    ax.grid(True, alpha=0.15)


def make(name, cons_rows, deer_rows, ckeep, dkeep, title):
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    panel(ax, macro(cons_rows, ckeep), macro(deer_rows, dkeep), title)
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf"); fig.savefig(OUT / f"{name}.png", dpi=140)
    plt.close(fig)
    print(f"wrote panels/{name}")


def main():
    dev_train = load(f"{SB}/v2_sweep_r/shard_*.jsonl")
    test = load(f"{SB}/v2_sweep_test/shard_*.jsonl")
    deer = load(f"{SB}/deer_sweep.jsonl")
    selb = lambda r: int(r["budget"]) == SEL[r["benchmark"]]

    # splits
    make("split_train", dev_train, deer,
         lambda r: r["split"] == "train" and selb(r), lambda r: r["split"] == "train",
         "Train split")
    make("split_dev", dev_train, deer,
         lambda r: r["split"] == "dev" and selb(r), lambda r: r["split"] == "dev",
         "Dev split")
    make("split_test", test, deer,
         lambda r: r["split"] == "test" and r["model"] in DEV_MODELS and selb(r),
         lambda r: r["split"] == "test", "Test split (held-out seeds)")

    # benchmarks (dev)
    for b in ("math500", "amc23", "aime24"):
        make(f"bench_{b}", dev_train, deer,
             lambda r, b=b: r["split"] == "dev" and r["benchmark"] == b and selb(r),
             lambda r, b=b: r["split"] == "dev" and r["benchmark"] == b,
             f"{b} (dev)")

    # models (dev)
    for mid, tag in (("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek7b"),
                     ("Qwen/Qwen3-8B", "qwen3_8b")):
        make(f"model_{tag}", dev_train, deer,
             lambda r, m=mid: r["split"] == "dev" and r["model"] == m and selb(r),
             lambda r, m=mid: r["split"] == "dev" and r["model"] == m,
             mid.split("/")[-1] + " (dev)")


if __name__ == "__main__":
    main()
