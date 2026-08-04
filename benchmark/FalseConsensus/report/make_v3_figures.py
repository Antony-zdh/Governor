#!/usr/bin/env python3
"""v3 figure set (paper revision issue 7): replace near-identical Pareto panels
with figures that each carry a distinct claim.

    fig_ws_heatmap        (W x s rule-space surface)          -> Results, sweep
    fig_split_transfer    (train -> dev -> test selection)    -> Results, selection
    fig_consensus_pos     (first-consensus position vs acc)   -> Results, phenomenon
    fig_harm_rescue       (harm:rescue vs window)             -> Analysis, mechanism

All numbers come from the committed banks under
results/governor_v2_ws_sweep/. Colour language is shared with
make_generalization_figs.py: consensus = amber/grey and fails, DEER = green and
clears, oracle = purple, gates = light shaded boxes.

Usage:  python3 make_v3_figures.py [--only NAME] [--no-cache]
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
BANK = RES / "governor_v2_ws_sweep"
OUT = HERE / "figures" / "gen"
PAPER = HERE.parent.parent.parent / "paper" / "figures" / "gen"

SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
DEVID = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
# preregistered gates: (name, max drop pp, min net saving, colour)
GATES = [("conservative", 1.0, 10.0, "#16a34a"),
         ("balanced", 2.0, 20.0, "#2563eb"),
         ("token_efficient", 3.5, 30.0, "#9333ea")]
DEER_SELECTED = {"C": 0.995, "B": 0.99, "T": 0.97}

C_CONS = "#f59e0b"
C_CONS_D = "#b45309"
C_CONS_L = "#fde68a"
C_DEER = "#059669"
C_DEER_D = "#065f46"
C_GREY = "#c2c6ce"
C_INK = "#1f2328"
C_MUTED = "#6b7280"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7,
    "axes.edgecolor": "#9ca3af",
    "axes.linewidth": 0.7,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load_gz(path):
    with gzip.open(path, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def rule_axes():
    """rule_id -> {'W':int, 's':float, 'interval':int, 'maturity':int, ...}"""
    out = {}
    for d in load_gz(BANK / "candidate_rules_v2.jsonl.gz"):
        ax = d["metadata"]["axis_values"]
        out[d["rule_id"]] = {
            "W": int(ax["evidence.window_probes"]),
            "s": float(ax["evidence.dominant_share_threshold"]),
            "interval": ax.get("probe.schedule.interval_tokens"),
            "maturity": ax.get("maturity.minimum_tokens"),
            "validity": ax.get("validity.mode"),
            "certainty": ax.get("certainty.enabled"),
            "template": d["metadata"]["template"],
        }
    return out


def consensus_rows():
    rows = list(load_gz(BANK / "dev/consensus_dev_train.jsonl.gz"))
    for r in load_gz(BANK / "test/consensus_test.jsonl.gz"):
        if r["model"] in DEVID and int(r["budget"]) == SEL[r["benchmark"]]:
            rows.append(r)
    return rows


def macro_by_rule(rows, split):
    """rule_id -> (macro accuracy drop pp, macro net saving %) over the 18 envs."""
    by = defaultdict(list)
    for r in rows:
        if r["split"] != split or r["model"] not in DEVID:
            continue
        if "budget" in r and int(r["budget"]) != SEL[r["benchmark"]]:
            continue
        by[r["rule_id"]].append(r)
    return {k: (st.fmean(x["accuracy_drop_pp"] for x in v),
                st.fmean(x["saving_fraction"] for x in v) * 100.0)
            for k, v in by.items()}


def deer_by_split():
    """split -> {tau: (drop, saving)} macro over that split's envs."""
    by = defaultdict(lambda: defaultdict(list))
    for r in load_gz(BANK / "deer/deer_threshold_sweep.jsonl.gz"):
        by[r["split"]][float(r["threshold"])].append(r)
    return {sp: {t: (st.fmean(x["accuracy_drop_pp"] for x in e),
                     st.fmean(x["saving_fraction"] for x in e) * 100.0)
                 for t, e in taus.items()}
            for sp, taus in by.items()}


def savefig(fig, name):
    for d in (OUT, PAPER):
        d.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=170, bbox_inches="tight")
    fig.savefig(PAPER / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# --------------------------------------------------------------------------- #
# Figure: W x s rule-space surface
# --------------------------------------------------------------------------- #
def fig_ws_heatmap():
    """Each (W, s) cell holds 160 rules (the operational knobs). We summarise a
    cell by its two extreme members, which is exactly what a gate asks about:

      (a) the cell's SAFEST rule   -> colour = its accuracy drop,
                                      annotation = the saving it buys
      (b) the cell's MOST ECONOMICAL rule -> colour = its net saving,
                                      annotation = the drop it costs

    A cell would clear the conservative gate only if some rule had drop <= 1.0 pp
    AND saving >= 10%; those cells are outlined. There are none.
    """
    axes_ = rule_axes()
    dev = macro_by_rule(consensus_rows(), "dev")

    cells = defaultdict(list)
    for rid, (d, s) in dev.items():
        a = axes_[rid]
        cells[(a["W"], a["s"])].append((d, s))

    Ws = sorted({k[0] for k in cells})
    Ss = sorted({k[1] for k in cells})

    safest = np.full((len(Ss), len(Ws)), np.nan)
    safest_sav = np.full_like(safest, np.nan)
    richest = np.full_like(safest, np.nan)
    richest_drop = np.full_like(safest, np.nan)
    passes = np.zeros_like(safest, dtype=bool)
    ncell = np.zeros_like(safest)

    for i, s in enumerate(Ss):
        for j, W in enumerate(Ws):
            v = cells.get((W, s))
            if not v:
                continue
            ncell[i, j] = len(v)
            d0, s0 = min(v, key=lambda t: t[0])
            safest[i, j], safest_sav[i, j] = d0, s0
            d1, s1 = max(v, key=lambda t: t[1])
            richest[i, j], richest_drop[i, j] = s1, d1
            passes[i, j] = any(d <= 1.0 and sv >= 10.0 for d, sv in v)

    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.55))

    cmap_d = LinearSegmentedColormap.from_list(
        "drop", ["#f7fbf9", "#fde68a", "#f59e0b", "#b45309", "#7c2d12"])
    cmap_s = LinearSegmentedColormap.from_list(
        "sav", ["#ffffff", "#d1fae5", "#6ee7b7", "#059669", "#064e3b"])

    def draw(ax, mat, ann, cmap, vmin, vmax, title, sub, fmt_c, fmt_a, cbl):
        m = np.ma.masked_invalid(mat)
        im = ax.imshow(m, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto",
                       origin="lower")
        ax.set_xticks(range(len(Ws)), [str(w) for w in Ws])
        ax.set_yticks(range(len(Ss)), [f"{s:.1f}" for s in Ss])
        ax.set_xlabel("window size $W$  (probes that must agree)")
        ax.set_ylabel("share threshold $s$")
        ax.set_title(title, fontweight="bold", pad=15)
        ax.text(0.5, 1.012, sub, transform=ax.transAxes, fontsize=6.6,
                color=C_MUTED, va="bottom", ha="center")
        for i in range(len(Ss)):
            for j in range(len(Ws)):
                if np.isnan(mat[i, j]):
                    ax.text(j, i, "n/a", ha="center", va="center", fontsize=6,
                            color="#b0b6bd")
                    continue
                rel = (mat[i, j] - vmin) / (vmax - vmin)
                col = "white" if rel > 0.62 else C_INK
                ax.text(j, i + 0.14, fmt_c(mat[i, j]), ha="center", va="center",
                        fontsize=6.6, color=col, fontweight="bold")
                ax.text(j, i - 0.20, fmt_a(ann[i, j]), ha="center", va="center",
                        fontsize=5.8, color=col)
                if passes[i, j]:
                    ax.add_patch(Rectangle((j - .5, i - .5), 1, 1, fill=False,
                                           ec=C_DEER, lw=2.0, zorder=5))
        ax.set_xticks(np.arange(-.5, len(Ws), 1), minor=True)
        ax.set_yticks(np.arange(-.5, len(Ss), 1), minor=True)
        ax.grid(which="minor", color="white", lw=1.1)
        ax.tick_params(which="minor", length=0)
        cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
        cb.set_label(cbl, fontsize=6.8)
        cb.ax.tick_params(labelsize=6.2)
        cb.outline.set_linewidth(0.5)

    draw(axs[0], safest, safest_sav, cmap_d, 0, 24,
         "a  The safest rule in each cell",
         "below: the saving it buys",
         lambda v: f"{v:.1f}", lambda v: f"{v:.0f}%",
         "accuracy drop (pp)")
    draw(axs[1], richest, richest_drop, cmap_s, 0, 100,
         "b  The most economical rule in each cell",
         "below: the drop it costs",
         lambda v: f"{v:.0f}%", lambda v: f"{v:.0f}pp",
         "net token saving (%)")
    fig.tight_layout(w_pad=2.4)
    savefig(fig, "fig_ws_heatmap")

    print("  cells:", int(ncell.sum()), "rules; passing cells:", int(passes.sum()))
    return {"safest": safest, "safest_sav": safest_sav,
            "richest": richest, "richest_drop": richest_drop,
            "W": Ws, "s": Ss}


# --------------------------------------------------------------------------- #
# Figure: train -> dev -> test selection transfer
# --------------------------------------------------------------------------- #
def fig_split_transfer():
    """The selection story as movement across splits. Consensus: the 478 rules
    that clear the conservative gate in-sample on train, summarised as median +
    IQR + range. DEER: its three dev-selected operating points, tracked
    individually. All three gates are drawn so the reader can see which one a
    curve would have to reach."""
    rows = consensus_rows()
    tr = macro_by_rule(rows, "train")
    dv = macro_by_rule(rows, "dev")
    te = macro_by_rule(rows, "test")
    deer = deer_by_split()

    winners = sorted(k for k, (d, s) in tr.items() if d <= 1.0 and s >= 10.0)
    splits = ["train", "dev", "test"]
    M = {"train": tr, "dev": dv, "test": te}
    x = np.arange(3)

    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.5))

    def band(ax, idx):
        vals = [[M[sp][r][idx] for r in winners] for sp in splits]
        ax.fill_between(x, [min(v) for v in vals], [max(v) for v in vals],
                        color=C_CONS_L, alpha=0.6, lw=0, zorder=2,
                        label=f"consensus train candidates (n={len(winners)}): range")
        ax.fill_between(x, [np.percentile(v, 25) for v in vals],
                        [np.percentile(v, 75) for v in vals],
                        color=C_CONS, alpha=0.45, lw=0, zorder=3, label="IQR")
        ax.plot(x, [st.median(v) for v in vals], "-o", color=C_CONS_D, ms=4.5,
                lw=1.9, zorder=4, label="median")

    def gates(ax, idx, lo, hi):
        for lab, (name, cap, floor, col) in zip("CBT", GATES):
            y = cap if idx == 0 else floor
            ax.axhline(y, color=col, ls="--", lw=0.9, zorder=1)
            ax.annotate(lab, (2.06, y), xycoords=("data", "data"), fontsize=6.6,
                        color=col, fontweight="bold", va="center")

    def deerlines(ax, idx):
        for lab, tau in DEER_SELECTED.items():
            ys = [deer[sp][tau][idx] for sp in splits]
            ax.plot(x, ys, "-", color=C_DEER, lw=1.3, zorder=5, alpha=0.9,
                    label="DEER, dev-selected (C/B/T)" if lab == "C" else None)
            ax.plot(x, ys, "*", color=C_DEER_D, ms=9, zorder=6, mec="white",
                    mew=0.6)

    ax = axs[0]
    band(ax, 0); gates(ax, 0, -2.5, 9); deerlines(ax, 0)
    ax.set_ylabel("accuracy drop (pp)")
    ax.set_ylim(-2.5, 8.6)
    ax.set_title("Accuracy drop", fontweight="bold", fontsize=8.5, pad=5)

    ax = axs[1]
    band(ax, 1); gates(ax, 1, 0, 45); deerlines(ax, 1)
    ax.set_ylabel("net token saving (%)")
    ax.set_ylim(0, 45)
    ax.set_title("Net token saving", fontweight="bold", fontsize=8.5, pad=5)

    n_pass = {sp: sum(1 for r in winners
                      if M[sp][r][0] <= 1.0 and M[sp][r][1] >= 10.0)
              for sp in splits}
    joint = sum(1 for r in winners
                if all(M[sp][r][0] <= 1.0 and M[sp][r][1] >= 10.0 for sp in splits))
    for ax in axs:
        ax.set_xticks(x, splits)
        ax.set_xlim(-0.22, 2.35)
        ax.grid(axis="y", alpha=0.15)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", bbox_to_anchor=(0.5, -0.10), ncol=4,
               framealpha=0, handlelength=1.5, borderpad=0.3, columnspacing=1.6,
               fontsize=6.6)
    fig.tight_layout(w_pad=2.2)
    savefig(fig, "fig_split_transfer")
    print(f"  winners={len(winners)}  in-gate per split={n_pass}  joint={joint}")
    return {"winners": len(winners), "n_pass": n_pass, "joint": joint}


# --------------------------------------------------------------------------- #
# Figure: harm:rescue vs window size
# --------------------------------------------------------------------------- #
def fig_harm_rescue():
    """Widening the window lowers the directional harm:rescue ratio -- but only
    by making the rule stop firing, so the saving falls with it."""
    cache = OUT / "harm_rescue_cache.json"
    if not cache.exists():
        raise SystemExit("run compute_harm_rescue.py first")
    d = json.loads(cache.read_text())
    cons = d["consensus"]
    Ws = sorted(int(k) for k in cons)
    ratio = [cons[str(w)]["ratio"] for w in Ws]
    sav = [cons[str(w)]["saving"] for w in Ws]
    nstop = [cons[str(w)]["n_stopped"] for w in Ws]
    deer = d.get("deer", {})

    fig, ax = plt.subplots(figsize=(3.45, 2.6))
    x = np.arange(len(Ws))
    dx = len(Ws) + 0.45

    ax2 = ax.twinx()
    ax2.bar(x, sav, width=0.62, color=C_CONS, alpha=0.28, zorder=0,
            label="net token saving")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("net token saving (%)", color=C_CONS_D, fontsize=7.4)
    ax2.tick_params(axis="y", colors=C_CONS_D, labelsize=7)
    ax2.spines["right"].set_color(C_CONS_D)

    ax.axhline(1.0, color=C_MUTED, ls=":", lw=0.9, zorder=1)
    ax.plot(x, ratio, "-o", color=C_CONS_D, ms=4.5, lw=1.9, zorder=5,
            label="consensus")
    if deer:
        rs = [v["ratio"] for v in deer.values()]
        ax.axhspan(min(rs), max(rs), color=C_DEER, alpha=0.13, zorder=0)
        # DEER's saving gets the same bar treatment as the consensus windows,
        # so the two are read on the same axis rather than as loose markers.
        ax2.bar([dx], [st.fmean(v["saving"] for v in deer.values())], width=0.62,
                color=C_DEER, alpha=0.30, zorder=0)
        for v in deer.values():
            ax.plot([dx], [v["ratio"]], "*", color=C_DEER_D, ms=9, mec="white",
                    mew=0.5, zorder=7, label=None)
        ax.plot([], [], "*", color=C_DEER_D, ms=9, label="DEER (C/B/T)")
        ax.axvline(len(Ws) - 0.28, color="#d1d5db", lw=0.8, zorder=1)
        ax.text(-0.55, (min(rs) * max(rs)) ** 0.5,
                f"DEER holds {min(rs):.1f}–{max(rs):.1f}:1\nwhile saving 28–32%",
                fontsize=6.2, color=C_DEER_D, va="center", ha="left", zorder=8,
                bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.0))

    ax.set_yscale("log")
    ax.set_ylim(0.7, 100)
    ax.set_yticks([1, 2, 5, 10, 20, 50], ["1:1", "2:1", "5:1", "10:1", "20:1", "50:1"])
    ax.minorticks_off()
    ax.annotate("1:1", (dx + 0.28, 1.0), fontsize=6.2, color=C_MUTED,
                va="center", ha="left", annotation_clip=False)
    ax.set_ylabel("harm : rescue", fontsize=8)
    ax.set_xlim(-0.7, len(Ws) + 0.9)
    ax.set_xticks(list(x) + [dx], [str(w) for w in Ws] + ["DEER"])
    ax.set_xlabel("window size $W$")
    ax.grid(axis="y", alpha=0.15, which="major")
    ax.set_title("Lowering the ratio means refusing to fire",
                 fontweight="bold", fontsize=8.5, pad=5)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=6.2, framealpha=0.95,
              handlelength=1.4, borderpad=0.35)
    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    fig.tight_layout()
    savefig(fig, "fig_harm_rescue")
    print("  ratios:", {w: round(cons[str(w)]["ratio"], 2) for w in Ws})
    print("  stops :", {w: cons[str(w)]["n_stopped"] for w in Ws})
    if deer:
        print("  DEER  :", {k: round(v["ratio"], 2) for k, v in deer.items()})


# --------------------------------------------------------------------------- #
# Figure: where consensus forms vs. whether it is right
# --------------------------------------------------------------------------- #
def fig_consensus_pos():
    """Consensus fires early, and early is exactly where it is least reliable.
    Position is a fraction of the trajectory's own length, which controls for
    problem difficulty."""
    cache = OUT / "consensus_position_cache.json"
    if not cache.exists():
        raise SystemExit("run compute_consensus_position.py first")
    d = json.loads(cache.read_text())
    rel, meta = d["relative"], d["meta"]

    fig, axs = plt.subplots(2, 1, figsize=(3.45, 3.1), sharex=True,
                            gridspec_kw={"height_ratios": [2.7, 1]})
    x = np.arange(len(rel))
    THIN = 20
    thin = [i for i, b in enumerate(rel) if b["n"] < THIN]
    solid = [i for i, b in enumerate(rel) if b["n"] >= THIN]

    ax = axs[0]
    if thin:
        ax.axvspan(min(thin) - 0.5, len(rel) - 0.5, color="#f3f4f6", zorder=0)
        ax.text((min(thin) + len(rel) - 1) / 2, 5, f"n < {THIN}", ha="center",
                fontsize=5.8, color=C_MUTED)
    ax.fill_between(x, [b["consensus_acc"] for b in rel],
                    [b["final_acc"] for b in rel], color="#fecaca", alpha=0.55,
                    lw=0, zorder=2, label="accuracy thrown away")
    ax.plot(x, [b["final_acc"] for b in rel], "-", color=C_DEER, lw=1.8,
            zorder=5, alpha=0.45)
    ax.plot(x, [b["consensus_acc"] for b in rel], "-", color=C_CONS_D, lw=1.8,
            zorder=5, alpha=0.45)
    ax.plot(solid, [rel[i]["final_acc"] for i in solid], "-o", color=C_DEER,
            ms=4.5, lw=1.8, zorder=6, label="run to completion")
    ax.plot(solid, [rel[i]["consensus_acc"] for i in solid], "-o", color=C_CONS_D,
            ms=4.5, lw=1.8, zorder=6, label="answer consensus commits to")
    ax.plot(thin, [rel[i]["final_acc"] for i in thin], "o", color="white",
            mec=C_DEER, mew=1.2, ms=4.0, zorder=6)
    ax.plot(thin, [rel[i]["consensus_acc"] for i in thin], "o", color="white",
            mec=C_CONS_D, mew=1.2, ms=4.0, zorder=6)
    for i, b in enumerate(rel):
        if b["n"] >= THIN:
            ax.annotate(f"−{b['final_acc']-b['consensus_acc']:.0f}",
                        (i, (b["final_acc"] + b["consensus_acc"]) / 2),
                        ha="center", va="center", fontsize=6.0, color="#991b1b")
    ax.set_ylabel("accuracy (%)")
    ax.set_ylim(0, 108)
    ax.grid(axis="y", alpha=0.15)
    ax.set_title("Consensus forms early, where it is least reliable",
                 fontweight="bold", fontsize=8.3, pad=5)
    ax.legend(loc="lower left", fontsize=6.1, framealpha=0.95, handlelength=1.5,
              borderpad=0.35, labelspacing=0.25)

    ax = axs[1]
    ax.bar(x, [b["n"] for b in rel], width=0.66, color=C_GREY, zorder=3)
    for i, b in enumerate(rel):
        ax.annotate(f"{b['n']}", (i, b["n"]), xytext=(0, 2),
                    textcoords="offset points", ha="center", fontsize=5.8,
                    color=C_MUTED)
    ax.set_ylabel("trajectories", fontsize=7)
    ax.set_ylim(0, max(b["n"] for b in rel) * 1.35)
    ax.set_xticks(x, [b["label"] for b in rel])
    ax.tick_params(axis="x", labelsize=6.6)
    ax.set_xlabel("first consensus, as % of the trajectory's own length")
    ax.grid(axis="y", alpha=0.15)
    fig.tight_layout(h_pad=0.6)
    savefig(fig, "fig_consensus_pos")
    for b in rel:
        print(f"  {b['label']:>8} n={b['n']:>4} consensus={b['consensus_acc']:5.1f}%"
              f" final={b['final_acc']:5.1f}%")


# --------------------------------------------------------------------------- #
# Figure: what consensus actually stops on (human annotation)
# --------------------------------------------------------------------------- #
# Adjudicated coding. Labels of record come from the committed adjudication
# layer (results/human_eval/adjudicated/taxonomy_adjudicated.csv), not from
# either annotator's raw export: A is reserved for cases where the model really
# had settled on a wrong numeric answer, D for cases where it had not settled at
# all. The coarse coding both annotators share (settled-or-not / format / other)
# is what the reliability statistic is computed on; adjudication produces labels
# of record and does not retroactively change that statistic.
ADJUDICATED = ("benchmark/FalseConsensus/results/human_eval/adjudicated/"
               "taxonomy_adjudicated.csv")
TAX_ORDER = ["D", "A", "E", "O"]
TAX_LABEL = {"D": "unconverged guess",
             "A": "converged, wrong",
             "E": "format artifact",
             "O": "other"}
TAX_COLOR = {"D": "#b45309", "A": "#f59e0b", "E": "#d97706", "O": "#a8a29e"}


def fig_taxonomy():
    """Two annotators over 134 stopped-but-wrong cases. The great majority of
    false-consensus stops are answers the model had not converged on -- a guess
    or placeholder the probe compelled it to emit -- or artifacts of the probe's
    output format. Only a fifth are cases where it had genuinely settled on a
    wrong value."""
    import csv
    repo = HERE.parent.parent.parent

    def load(fname):
        out = {}
        with open(repo / fname, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t = r["HUMAN_type[A-E]"].strip().upper()
                out[r["problem_id"]] = t
        return out

    def load_adjudicated():
        out = {}
        with open(repo / ADJUDICATED, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t = r["adjudicated_type"].strip().upper()
                out[r["problem_id"]] = t if t in ("A", "D", "E") else "O"
        return out

    a1, a2 = load("taxonomy_review_1.csv"), load("taxonomy_review_2.csv")
    keys = sorted(set(a1) & set(a2))
    n = len(keys)

    adj = load_adjudicated()
    counts = {c: sum(1 for k in keys if adj[k] == c) for c in TAX_ORDER}

    # reliability on the coarse coding both annotators share
    coarse = lambda t: "AD" if t in ("A", "D") else (t if t == "E" else "O")
    c1 = [coarse(a1[k]) for k in keys]
    c2 = [coarse(a2[k]) for k in keys]
    cats = sorted(set(c1) | set(c2))
    po = sum(x == y for x, y in zip(c1, c2)) / n
    pe = sum((c1.count(c) / n) * (c2.count(c) / n) for c in cats)
    kappa = (po - pe) / (1 - pe)

    fig, ax = plt.subplots(figsize=(3.45, 1.7))
    y = np.arange(len(TAX_ORDER))[::-1]
    vals = [counts[c] / n * 100 for c in TAX_ORDER]
    ax.barh(y, vals, height=0.62, color=[TAX_COLOR[c] for c in TAX_ORDER],
            zorder=3)
    for i, c in enumerate(TAX_ORDER):
        ax.annotate(f"{vals[i]:.0f}%   ($n$={counts[c]})", (vals[i], y[i]),
                    xytext=(4, 0), textcoords="offset points", va="center",
                    fontsize=6.4, color=C_MUTED)
    ax.set_yticks(y, [TAX_LABEL[c] for c in TAX_ORDER])
    ax.tick_params(axis="y", labelsize=7.2)
    ax.set_xlim(0, 96)
    ax.set_xlabel("share of stopped-but-wrong cases (%)", fontsize=7.6)
    ax.grid(axis="x", alpha=0.15)
    ax.set_title("What consensus actually stops on", fontweight="bold",
                 fontsize=8.5, pad=5)
    ax.annotate(f"$n$ = {n},  $\\kappa$ = {kappa:.2f}", (0.985, 0.06),
                xycoords="axes fraction", ha="right", fontsize=6.4, color=C_MUTED)
    fig.tight_layout()
    savefig(fig, "fig_taxonomy")
    print(f"  n={n} kappa={kappa:.3f}")
    print("  adjudicated:", {c: f"{counts[c]} ({vals[i]:.1f}%)"
                             for i, c in enumerate(TAX_ORDER)})


def fig_wording_taxonomy():
    """Merged Figure 2: two sides of the stability--terminality gap.
    (a) probe-wording sensitivity vs. trajectory position -- early 'answers'
    depend on how the probe is worded; (b) the human taxonomy of
    stopped-but-wrong cases -- most are placeholders the model had not
    converged on."""
    import csv
    repo = HERE.parent.parent.parent

    fig, (axA, axB) = plt.subplots(
        1, 2, figsize=(7.0, 2.35), gridspec_kw={"width_ratios": [1.0, 1.08]})

    # ---- panel (a): wording sensitivity vs position ----
    wd = json.loads((OUT / "probe_wording.json").read_text())
    bins = wd["bins"]
    labels = ["0–10", "10–20", "20–40", "40–70", "70–100"]
    x = np.arange(len(bins))
    agree = [b["agree_pct"] for b in bins]
    correct = [b["correct_pct"] for b in bins]

    axA.axvspan(-0.45, 0.5, color="#f3f4f6", zorder=0)
    axA.text(0.02, 3, "same frozen prefix,\ntwo probe wordings", fontsize=5.9,
             color=C_MUTED, va="bottom")
    axA.plot(x, agree, "-o", color=C_CONS_D, lw=1.9, ms=4.6, zorder=5,
             label="two wordings agree")
    axA.plot(x, correct, "--o", color=C_MUTED, lw=1.5, ms=3.8, zorder=5,
             label="probe answer correct")
    axA.annotate(f"{agree[0]:.0f}%", (0, agree[0]), xytext=(0, 6),
                 textcoords="offset points", ha="center", fontsize=6.4,
                 color=C_CONS_D)
    axA.annotate(f"{agree[-1]:.0f}%", (len(bins) - 1, agree[-1]), xytext=(0, 6),
                 textcoords="offset points", ha="center", fontsize=6.4,
                 color=C_CONS_D)
    axA.set_ylim(0, 106)
    axA.set_xticks(x, labels)
    axA.tick_params(axis="x", labelsize=6.7)
    axA.set_xlabel("position (% of the trajectory's own length)", fontsize=7.4)
    axA.set_ylabel("% of probe points", fontsize=7.6)
    axA.grid(axis="y", alpha=0.15)
    axA.set_title("(a) Early answers depend on how you ask",
                  fontweight="bold", fontsize=8.2, pad=5)
    axA.legend(loc="lower right", fontsize=6.3, framealpha=0.95,
               handlelength=1.6, borderpad=0.35, labelspacing=0.25)

    # ---- panel (b): human error taxonomy ----
    def load(fname):
        out = {}
        with open(repo / fname, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                out[r["problem_id"]] = r["HUMAN_type[A-E]"].strip().upper()
        return out

    def load_adjudicated():
        out = {}
        with open(repo / ADJUDICATED, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t = r["adjudicated_type"].strip().upper()
                out[r["problem_id"]] = t if t in ("A", "D", "E") else "O"
        return out

    a1, a2 = load("taxonomy_review_1.csv"), load("taxonomy_review_2.csv")
    keys = sorted(set(a1) & set(a2))
    n = len(keys)
    adj = load_adjudicated()
    counts = {c: sum(1 for k in keys if adj[k] == c) for c in TAX_ORDER}
    coarse = lambda t: "AD" if t in ("A", "D") else (t if t == "E" else "O")
    c1 = [coarse(a1[k]) for k in keys]
    c2 = [coarse(a2[k]) for k in keys]
    cats = sorted(set(c1) | set(c2))
    po = sum(u == v for u, v in zip(c1, c2)) / n
    pe = sum((c1.count(c) / n) * (c2.count(c) / n) for c in cats)
    kappa = (po - pe) / (1 - pe)

    y = np.arange(len(TAX_ORDER))[::-1]
    vals = [counts[c] / n * 100 for c in TAX_ORDER]
    axB.barh(y, vals, height=0.62, color=[TAX_COLOR[c] for c in TAX_ORDER],
             zorder=3)
    for i, c in enumerate(TAX_ORDER):
        axB.annotate(f"{vals[i]:.0f}%  ($n$={counts[c]})", (vals[i], y[i]),
                     xytext=(4, 0), textcoords="offset points", va="center",
                     fontsize=6.3, color=C_MUTED)
    axB.set_yticks(y, [TAX_LABEL[c] for c in TAX_ORDER])
    axB.tick_params(axis="y", labelsize=7.2)
    axB.set_xlim(0, 104)
    axB.set_xlabel("share of stopped-but-wrong cases (%)", fontsize=7.4)
    axB.grid(axis="x", alpha=0.15)
    axB.set_title("(b) What consensus actually stops on",
                  fontweight="bold", fontsize=8.2, pad=5)
    axB.annotate(f"$n$={n},  $\\kappa$={kappa:.2f}", (0.985, 0.06),
                 xycoords="axes fraction", ha="right", fontsize=6.3,
                 color=C_MUTED)

    fig.tight_layout(w_pad=1.8)
    savefig(fig, "fig_wording_taxonomy")
    print(f"  wording bins={len(bins)} first_agree={agree[0]:.1f} "
          f"last_agree={agree[-1]:.1f}; taxonomy n={n} kappa={kappa:.3f}")


FIGS = {
    "ws_heatmap": fig_ws_heatmap,
    "split_transfer": fig_split_transfer,
    "harm_rescue": fig_harm_rescue,
    "consensus_pos": fig_consensus_pos,
    "taxonomy": fig_taxonomy,
    "wording_taxonomy": fig_wording_taxonomy,
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    for name, fn in FIGS.items():
        if a.only and a.only != name:
            continue
        print(f"== {name}")
        fn()
