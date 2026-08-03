#!/usr/bin/env python3
"""Five rough concepts for Figure 1 (the idea figure).

Sketch quality on purpose: layout, hierarchy and reading order are real; icons,
exact wording and fine spacing are not. Pick one, then it gets built properly
(editable .pptx + PDF, real probe-stream data where the concept uses it).

Output: paper/revision_v3/concepts/fig1_concept{1..5}.png
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concepts")

INK = "#1f2328"
MUTED = "#6b7280"
CONS = "#f59e0b"
CONS_D = "#b45309"
CONS_BG = "#fef3c7"
DEER = "#059669"
DEER_D = "#065f46"
DEER_BG = "#d1fae5"
RED = "#dc2626"
RED_BG = "#fee2e2"
ZONE = ["#eaf2ea", "#e8eff8", "#f3ecf6"]
GREY_BG = "#f3f4f6"

plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42})


def canvas(w=7.0, h=2.9):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100 * h / w)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, fc="white", ec="#d9dde1", lw=1.0, r=1.2, z=2, alpha=1.0):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       fc=fc, ec=ec, lw=lw, zorder=z, alpha=alpha)
    ax.add_patch(p)
    return p


def txt(ax, x, y, s, size=7, color=INK, weight="normal", ha="center", va="center",
        style="normal", z=5):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, zorder=z,
            fontweight=weight, style=style, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, color=MUTED, lw=1.6, style="-|>", ls="-", z=4,
          mut=9):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=mut, color=color, lw=lw, ls=ls,
                                 zorder=z, shrinkA=0, shrinkB=0))


def ribbon(ax, x, y, w, h, z=5):
    """Schematic probe stream: wrong run, churn, then a stable correct tail."""
    seq = ([RED] * 10 + ["#fca5a5", "#fca5a5", RED, "#fca5a5"] + [DEER] * 22)
    cw = w / len(seq)
    for i, c in enumerate(seq):
        ax.add_patch(FancyBboxPatch((x + i * cw, y), cw * 1.02, h,
                                    boxstyle="round,pad=0,rounding_size=0",
                                    fc=c, ec="none", zorder=z))


# --------------------------------------------------------------------------- #
def concept1():
    """Zoned pipeline. Three labelled zones read left to right, each holding the
    evidence for one beat; the connecting questions sit on the arrows."""
    fig, ax = canvas()
    H = 41.4
    zones = [("1. THE PHENOMENON", 1, 28), ("2. THE SEARCH", 32, 36),
             ("3. THE VERDICT", 70, 29)]
    for i, (name, x, w) in enumerate(zones):
        box(ax, x, 4, w, 30, fc=ZONE[i], ec="none", r=1.6, z=1)
        txt(ax, x + w / 2, 36.5, name, size=8, weight="bold", color=INK)

    # zone 1
    box(ax, 3, 17, 24, 14, r=1.2)
    txt(ax, 15, 29, "one real trajectory", size=6, color=MUTED, style="italic")
    ribbon(ax, 5, 23, 20, 3)
    txt(ax, 9.5, 27.2, '10 × "37" ✗', size=6, color=RED, weight="bold")
    txt(ax, 21, 27.2, '"46" ✓', size=6, color=DEER_D, weight="bold")
    arrow(ax, 8, 22.6, 8, 21.2, color=RED, lw=1.2, mut=7)
    txt(ax, 15, 19.6, "consensus fires here,\non a wrong answer", size=6,
        color=RED)
    box(ax, 3, 7.5, 24, 7, fc=CONS_BG, ec=CONS, r=1.2)
    txt(ax, 15, 11, "harm : rescue ≈ 45 : 1", size=7.5, weight="bold",
        color=CONS_D)

    # zone 2
    box(ax, 34, 22, 32, 10, r=1.2)
    txt(ax, 50, 29.5, "3,520 preregistered consensus rules", size=7.5,
        weight="bold", color=CONS_D)
    txt(ax, 50, 25.5, "window W × share s × schedule / maturity / validity\n"
                      "replayed on 18 frozen environments", size=6, color=MUTED)
    box(ax, 34, 7.5, 32, 11, fc=GREY_BG, ec="#9ca3af", r=1.2)
    txt(ax, 50, 16, "three gates, fixed before the sweep", size=6, color=MUTED,
        style="italic")
    for k, (lab, c, yy) in enumerate((("C", "#16a34a", 12.8),
                                      ("B", "#2563eb", 10.6),
                                      ("T", "#9333ea", 8.4))):
        ax.add_patch(plt.Circle((37, yy), 1.0, fc=c, ec="none", zorder=5))
        txt(ax, 37, yy, lab, size=5.5, color="white", weight="bold")
        txt(ax, 40, yy, f"drop ≤ {[1.0, 2.0, 3.5][k]} pp     "
                        f"saving ≥ {[10, 20, 30][k]}%", size=6, ha="left")

    # zone 3
    box(ax, 72, 21, 25, 11, fc="white", ec=CONS, r=1.2)
    txt(ax, 84.5, 28, "consensus", size=8, weight="bold", color=CONS_D)
    txt(ax, 84.5, 24, "0 of 3 gates", size=9, weight="bold", color=RED)
    box(ax, 72, 7.5, 25, 11, fc=DEER_BG, ec=DEER, r=1.2)
    txt(ax, 84.5, 14.5, "DEER", size=8, weight="bold", color=DEER_D)
    txt(ax, 84.5, 10.6, "3 of 3 gates", size=9, weight="bold", color=DEER_D)

    for x1, x2, q in ((27.5, 33.5, "so can any\nrule be safe\nand saving?"),
                      (66.5, 71.5, "is early exit\nitself\nimpossible?")):
        arrow(ax, x1, 19, x2, 19, lw=2.0, mut=11)
        txt(ax, (x1 + x2) / 2, 25, q, size=5.4, color=MUTED, style="italic")

    box(ax, 1, 0.2, 96, 3.2, fc=INK, ec="none", r=0.8)
    txt(ax, 49, 1.8, "Early exit is possible — the consensus SIGNAL is what "
                     "cannot make it safe.", size=8, color="white",
        weight="bold")
    fig.savefig(f"{OUT}/fig1_concept1.png", dpi=190, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
def concept2():
    """Decision flowchart. One question enters, two signals branch out of the
    same pipeline, and the two outcomes are the answer."""
    fig, ax = canvas()
    box(ax, 30, 34, 40, 6, fc=GREY_BG, ec="#9ca3af", r=1.4)
    txt(ax, 50, 37, "Can a reasoning model stop early and stay accurate?",
        size=8, weight="bold")

    txt(ax, 50, 31.5, "what signal do we stop on?", size=6, color=MUTED,
        style="italic")
    arrow(ax, 50, 33.8, 26, 29.5, lw=1.5)
    arrow(ax, 50, 33.8, 74, 29.5, lw=1.5)

    box(ax, 6, 23, 40, 6, fc=CONS_BG, ec=CONS, r=1.2)
    txt(ax, 26, 26, "CONSENSUS: do recent probes agree?", size=7,
        weight="bold", color=CONS_D)
    box(ax, 54, 23, 40, 6, fc=DEER_BG, ec=DEER, r=1.2)
    txt(ax, 74, 26, "BOUNDARY CONFIDENCE (DEER)", size=7, weight="bold",
        color=DEER_D)

    box(ax, 6, 15, 88, 5.5, fc="#6b7280", ec="none", r=1.2)
    txt(ax, 50, 17.7, "IDENTICAL PIPELINE:  frozen trajectories · 18 environments"
                      " · same gates · same token accounting",
        size=6.6, color="white", weight="bold")
    arrow(ax, 26, 22.8, 26, 20.7, lw=1.4)
    arrow(ax, 74, 22.8, 74, 20.7, lw=1.4)
    arrow(ax, 26, 14.8, 26, 12.7, lw=1.4)
    arrow(ax, 74, 14.8, 74, 12.7, lw=1.4)

    box(ax, 6, 4.5, 40, 8, fc="white", ec=RED, r=1.2, lw=1.4)
    txt(ax, 26, 10, "3,520 rules swept", size=6, color=MUTED)
    txt(ax, 26, 7.2, "✗   0 of 3 gates", size=9.5, weight="bold", color=RED)
    box(ax, 54, 4.5, 40, 8, fc=DEER_BG, ec=DEER, r=1.2, lw=1.4)
    txt(ax, 74, 10, "14 thresholds swept", size=6, color=MUTED)
    txt(ax, 74, 7.2, "✓   3 of 3 gates", size=9.5, weight="bold", color=DEER_D)

    txt(ax, 50, 1.8, "The failure is the SIGNAL, not early exit.", size=8.5,
        weight="bold")
    fig.savefig(f"{OUT}/fig1_concept2.png", dpi=190, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
def concept3():
    """Trajectory hero. The phenomenon gets the top half at full width; the
    three results are small cards beneath it."""
    fig, ax = canvas()
    txt(ax, 2, 38, "What goes wrong", size=8.5, weight="bold", ha="left")
    txt(ax, 2, 34.6, "one real trajectory, probed every 64 tokens", size=6,
        color=MUTED, ha="left", style="italic")

    ribbon(ax, 4, 26, 92, 4.5)
    txt(ax, 16, 32.2, 'ten probes agree on "37" — all wrong', size=6.6,
        color=RED, weight="bold")
    txt(ax, 72, 32.2, 'the model finds "46" and holds it to the end', size=6.6,
        color=DEER_D, weight="bold")
    arrow(ax, 11, 25.6, 11, 23.6, color=RED, lw=1.4, mut=8)
    txt(ax, 11, 21.6, "a consensus rule stops here", size=6.4, color=RED,
        weight="bold")
    txt(ax, 60, 21.6, "everything to the right is never generated  →  the "
                      "recovery is destroyed", size=6.4, color=MUTED)

    txt(ax, 2, 17, "What we did about it", size=8.5, weight="bold", ha="left")
    cards = [
        ("3,520 rules", "every consensus rule in a\npreregistered space,\n"
         "18 frozen environments", CONS_BG, CONS, CONS_D),
        ("0 of 3 gates", "not one is both safe\nand saving —\n"
         "1 pp cap → 0.2% saved", RED_BG, RED, RED),
        ("DEER: 3 of 3", "same pipeline, same gates,\na non-consensus signal\n"
         "clears them all", DEER_BG, DEER, DEER_D),
    ]
    for i, (head, body, fc, ec, tc) in enumerate(cards):
        x = 3 + i * 31.7
        box(ax, x, 4, 29, 11, fc=fc, ec=ec, r=1.2)
        txt(ax, x + 14.5, 12.4, head, size=8.5, weight="bold", color=tc)
        txt(ax, x + 14.5, 7.8, body, size=6, color=INK)
        if i < 2:
            arrow(ax, x + 29.6, 9.5, x + 31.2, 9.5, lw=1.6, mut=9)

    txt(ax, 50, 1.3, "Early exit is possible — the consensus SIGNAL is not.",
        size=8, weight="bold")
    fig.savefig(f"{OUT}/fig1_concept3.png", dpi=190, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
def concept4():
    """Two funnels, side by side. The same three sieves; 3,520 rules go in on
    the left and none comes out, 14 thresholds go in on the right and 3 do."""
    fig, ax = canvas()
    txt(ax, 50, 39, "The same sieve, two signals", size=9, weight="bold")

    def funnel(x0, top_w, title, sub, n_in, colour, bg, survivors, verdict, vc):
        txt(ax, x0, 34.5, title, size=8, weight="bold", color=colour)
        txt(ax, x0, 31.6, sub, size=6, color=MUTED, style="italic")
        box(ax, x0 - top_w / 2, 27, top_w, 3.6, fc=bg, ec=colour, r=0.8)
        txt(ax, x0, 28.8, n_in, size=7, weight="bold", color=colour)
        for k, (lab, gc, yy) in enumerate((("C", "#16a34a", 21.5),
                                           ("B", "#2563eb", 16.0),
                                           ("T", "#9333ea", 10.5))):
            wt = top_w * (1 - 0.13 * k)
            wb = top_w * (1 - 0.13 * (k + 1))
            ax.add_patch(Polygon([(x0 - wt / 2, yy + 4.2), (x0 + wt / 2, yy + 4.2),
                                  (x0 + wb / 2, yy), (x0 - wb / 2, yy)],
                                 fc=GREY_BG, ec="#9ca3af", lw=0.9, zorder=2))
            ax.add_patch(plt.Circle((x0 - wt / 2 - 3.2, yy + 2.1), 1.1, fc=gc,
                                    ec="none", zorder=5))
            txt(ax, x0 - wt / 2 - 3.2, yy + 2.1, lab, size=5.5, color="white",
                weight="bold")
            txt(ax, x0, yy + 2.1, ["drop ≤ 1.0 pp · saving ≥ 10%",
                                   "drop ≤ 2.0 pp · saving ≥ 20%",
                                   "drop ≤ 3.5 pp · saving ≥ 30%"][k],
                size=5.6, color=INK)
        box(ax, x0 - 13, 3.8, 26, 5.4, fc=bg if survivors else "white",
            ec=vc, r=1.2, lw=1.4)
        txt(ax, x0, 6.5, verdict, size=9.5, weight="bold", color=vc)

    funnel(26, 40, "CONSENSUS", "do recent probes agree?",
           "3,520 preregistered rules", CONS_D, CONS_BG, False,
           "✗   0 survive", RED)
    funnel(74, 40, "DEER", "confident at a reasoning boundary?",
           "14 confidence thresholds", DEER_D, DEER_BG, True,
           "✓   3 survive", DEER_D)

    ax.plot([50, 50], [4, 33], color="#d9dde1", lw=1.0, ls="--", zorder=1)
    txt(ax, 50, 26.0, "identical\npipeline,\nsame gates,\nsame token\naccounting",
        size=5.6, color=MUTED, style="italic")

    txt(ax, 50, 1.2, "Early exit is possible — the consensus SIGNAL is not.",
        size=8, weight="bold")
    fig.savefig(f"{OUT}/fig1_concept4.png", dpi=190, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
def concept5():
    """Side-by-side scorecard. Same four questions asked of both signals, so the
    controlled comparison is the layout itself."""
    fig, ax = canvas()
    txt(ax, 50, 39.5, "One pipeline, two signals, four questions", size=9,
        weight="bold")

    box(ax, 34, 33.5, 30, 4.6, fc=CONS_BG, ec=CONS, r=1.0)
    txt(ax, 49, 35.8, "CONSENSUS", size=7.5, weight="bold", color=CONS_D)
    box(ax, 66, 33.5, 30, 4.6, fc=DEER_BG, ec=DEER, r=1.0)
    txt(ax, 81, 35.8, "DEER", size=7.5, weight="bold", color=DEER_D)

    rows = [
        ("what it reads", 'agreement among\nrecent probe answers',
         "the model's confidence\nat a reasoning boundary", None, None),
        ("how many settings\nwe swept", "3,520 rules\n(W × s × knobs)",
         "14 confidence\nthresholds", None, None),
        ("clears the gates?", "✗  0 of 3", "✓  3 of 3", RED, DEER_D),
        ("holds out of\nsample?", "✗  test, 32B, Llama:\ngate stays empty",
         "✓  test, 32B, Llama:\nall clear", RED, DEER_D),
    ]
    y = 28.5
    for i, (q, a, b, ca, cb) in enumerate(rows):
        h = 6.2
        box(ax, 2, y - h + 0.6, 30, h, fc=GREY_BG, ec="none", r=0.8)
        txt(ax, 17, y - h / 2 + 0.6, q, size=6.8, weight="bold")
        box(ax, 34, y - h + 0.6, 30, h, fc="white", ec="#e5e7eb", r=0.8)
        txt(ax, 49, y - h / 2 + 0.6, a, size=6.4,
            color=ca or INK, weight="bold" if ca else "normal")
        box(ax, 66, y - h + 0.6, 30, h, fc="white", ec="#e5e7eb", r=0.8)
        txt(ax, 81, y - h / 2 + 0.6, b, size=6.4,
            color=cb or INK, weight="bold" if cb else "normal")
        y -= h + 0.9

    box(ax, 2, 0.6, 94, 4.4, fc=INK, ec="none", r=0.9)
    txt(ax, 49, 2.8, "Same machinery, opposite outcomes → the failure is the "
                     "SIGNAL, not early exit.", size=7.8, color="white",
        weight="bold")
    fig.savefig(f"{OUT}/fig1_concept5.png", dpi=190, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for fn in (concept1, concept2, concept3, concept4, concept5):
        fn()
        print("wrote", fn.__name__)
