#!/usr/bin/env python3
"""v2 Pareto figure: the safe-and-saving corner is empty for consensus, DEER fills it.

Reads the v2 consensus sweep shards and the DEER threshold sweep, aggregates
each rule to macro-mean-over-environments (model x benchmark x seed) dev totals
(accuracy drop, net token saving), and plots:
  * every consensus rule as a grey point;
  * the consensus dev Pareto frontier as a red step;
  * the DEER threshold frontier as green markers;
  * the three preregistered gate regions (safe-and-saving boxes).
"""
from __future__ import annotations

import argparse
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


def load_jsonl(paths):
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def macro_dev(rows):
    """rule_id -> (drop_pp, saving_frac, psf, method)."""
    by_rule = defaultdict(list)
    for r in rows:
        if str(r["split"]) != "dev":
            continue
        by_rule[str(r["rule_id"])].append(r)
    out = {}
    for rid, envs in by_rule.items():
        drops = [float(e["accuracy_drop_pp"]) for e in envs]
        saves = [float(e["saving_fraction"]) for e in envs]
        out[rid] = (
            statistics.fmean(drops),
            statistics.fmean(saves) * 100.0,
            sum(s > 0 for s in saves) / len(saves),
            str(envs[0].get("method", "consensus")),
        )
    return out


def frontier(points):
    """(drop, saving) non-dominated: minimize drop, maximize saving."""
    pts = sorted(points, key=lambda t: (t[0], -t[1]))
    fr, best = [], float("-inf")
    for d, s in pts:
        if s > best:
            fr.append((d, s))
            best = s
    return fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", nargs="+", required=True)
    ap.add_argument("--deer", nargs="+", required=True)
    ap.add_argument("--protocol", default=REPO / "benchmark/FalseConsensus/governor_v2/protocol_v2.json")
    ap.add_argument("--output", default=REPO / "paper/figures/governor_v2_pareto_dev.pdf")
    args = ap.parse_args()

    cons = macro_dev(load_jsonl(args.consensus))
    deer = macro_dev(load_jsonl(args.deer))
    gates = json.loads(Path(args.protocol).read_text())["selection"]["operating_points"]

    cons_pts = [(d, s) for (d, s, _, _) in cons.values()]
    deer_pts = sorted([(d, s) for (d, s, _, _) in deer.values()], key=lambda t: t[0])

    fig, ax = plt.subplots(figsize=(7.0, 5.0))

    # gate regions (safe-and-saving corners): drop <= cap AND saving >= floor
    gate_colors = {"conservative": "#16a34a", "balanced": "#2563eb", "token_efficient": "#9333ea"}
    for g in gates:
        cap = float(g["total_accuracy_drop_pp_max"])
        floor = float(g["minimum_total_saving_fraction"]) * 100.0
        c = gate_colors.get(g["name"], "#888")
        ax.add_patch(
            Rectangle(
                (0, floor), cap, 100 - floor,
                facecolor=c, alpha=0.06, edgecolor=c, lw=1.0, ls="--", zorder=1,
            )
        )
        ax.text(cap - 0.05, floor + 1.2, g["name"], fontsize=7.5, color=c,
                ha="right", va="bottom", zorder=6)

    # consensus cloud
    ax.scatter(
        [d for d, s in cons_pts], [s for d, s in cons_pts],
        s=6, c="#b8bcc4", alpha=0.5, linewidths=0, zorder=2,
        label=f"consensus rules (n={len(cons_pts)})",
    )
    # consensus frontier
    cf = frontier(cons_pts)
    ax.step([d for d, s in cf], [s for d, s in cf], where="post",
            color="#dc2626", lw=1.6, zorder=4, label="consensus dev frontier")

    # DEER frontier
    ax.plot([d for d, s in deer_pts], [s for d, s in deer_pts],
            "-D", color="#059669", ms=5, lw=1.6, zorder=5, label="DEER (threshold sweep)")

    ax.set_xlabel("total accuracy drop (pp, macro over 18 dev environments)")
    ax.set_ylabel("net token saving (%)")
    ax.set_xlim(-1.0, 30)
    ax.set_ylim(-5, 75)
    ax.axhline(0, color="#ccc", lw=0.8, zorder=0)
    ax.axvline(0, color="#ccc", lw=0.8, zorder=0)
    ax.set_title("The safe-and-saving corner is empty for consensus; DEER fills it",
                 fontsize=10)
    ax.legend(loc="lower right", fontsize=8, framealpha=0.95)
    ax.grid(True, alpha=0.15)
    fig.tight_layout()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output)
    fig.savefig(str(args.output).replace(".pdf", ".png"), dpi=150)
    print(f"wrote {args.output}")
    print(f"consensus rules plotted: {len(cons_pts)}; DEER points: {len(deer_pts)}")


if __name__ == "__main__":
    main()
