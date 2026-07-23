"""Merged comparison figures for the Stage 11-12 + probe-ablation report.

Reads the already-computed per_problem.csv of each experiment (no model server
needed) and produces overlay/comparison figures with CORRECT model labels —
fixing the hardcoded "DeepSeek-R1-Distill-7B" legend that analyze.py stamps on
every run's fig1/fig1b regardless of --model.

Outputs -> report/figures/*.png
"""
import os
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(HERE, "figures")
os.makedirs(FIGDIR, exist_ok=True)
RES = os.path.join(HERE, "..", "results")

# ---- palette -------------------------------------------------------------
BLUE = "#2a78d6"    # DeepSeek / baseline
ORANGE = "#eb6834"  # Qwen
TEAL = "#1f9e89"    # AMC23
MAGENTA = "#c8447a" # AIME24
PURPLE = "#7a5cc0"  # certaindex probe
GRAY = "#52514e"
GRID = "#e6e5e1"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.edgecolor": GRID,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
    "text.color": "#0b0b0b", "axes.labelcolor": "#333", "xtick.color": "#333", "ytick.color": "#333",
})

BINS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.999, 1.001]
BLAB = ["<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-<1", "=1.0"]

RUNS = {
    "deepseek": ("results/stage1_logging", "DeepSeek-7B", BLUE),
    "qwen":     ("results/stage11_cross_model/qwen3_8b_math500", "Qwen3-8B", ORANGE),
    "amc23":    ("results/stage12_cross_dataset/deepseek7b_amc23", "DeepSeek-7B · AMC23", TEAL),
    "aime24":   ("results/stage12_cross_dataset/deepseek7b_aime24", "DeepSeek-7B · AIME24", MAGENTA),
    "certaindex": ("results/probe_suffix_ablation/deepseek7b_math500_certaindex", "certaindex probe", PURPLE),
}


def load_pp(key):
    path = os.path.join(HERE, "..", RUNS[key][0], "analysis", "per_problem.csv")
    df = pd.read_csv(path)
    for c in ("final_correct", "probe1_correct"):
        df[c] = df[c].astype(str).str.lower() == "true"
    return df


def calib(df, col, min_n=3):
    x = df.dropna(subset=[col]).copy()
    x["bin"] = pd.cut(x[col], bins=BINS, labels=BLAB, right=False)
    rows = []
    for lab in BLAB:
        sub = x[x["bin"] == lab]
        if len(sub) >= min_n:
            rows.append({"share": sub[col].mean(), "acc": sub["final_correct"].mean(), "n": len(sub)})
    return pd.DataFrame(rows)


def ms(n, base=5.0, scale=16.0, nmax=375.0):
    return base + scale * np.sqrt(min(n, nmax)) / np.sqrt(nmax)


def draw_calib(ax, df, col, label, color, min_n=3):
    c = calib(df, col, min_n)
    ax.plot(c["share"], c["acc"], color=color, lw=2, marker="o", label=label, zorder=3,
            markersize=0)
    for _, r in c.iterrows():
        ax.plot(r["share"], r["acc"], marker="o", color=color, ms=ms(r["n"]), zorder=4,
                markeredgecolor="white", markeredgewidth=1, alpha=0.9)
    return c


def diag(ax):
    ax.plot([0, 1], [0, 1], ls="--", lw=1, color=GRAY, zorder=1)
    ax.text(0.97, 0.99, "perfect calibration", color=GRAY, fontsize=9,
            ha="right", va="bottom", rotation=38, rotation_mode="anchor")


def style(ax, xlab, ylab):
    ax.set_xlabel(xlab); ax.set_ylabel(ylab)
    ax.set_xlim(0.28, 1.02); ax.set_ylim(0.0, 1.03)


# ==== F1: cross-model calibration (DeepSeek vs Qwen, MATH500) ==============
def f1_models():
    ds, qw = load_pp("deepseek"), load_pp("qwen")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, col, ttl in [(axes[0], "final_share", "(a) Cumulative share — whole trajectory"),
                         (axes[1], "window_share", "(b) Window share — last 5 probes (what a Governor sees)")]:
        diag(ax)
        draw_calib(ax, ds, col, "DeepSeek-7B", BLUE)
        draw_calib(ax, qw, col, "Qwen3-8B", ORANGE)
        style(ax, "Agreement (dominant-answer share)", "Final accuracy")
        ax.set_title(ttl, fontsize=11, color="#111")
    axes[0].legend(frameon=False, loc="upper left", fontsize=10)
    fig.suptitle("Agreement vs accuracy, two models on MATH500  ·  marker size $\\propto\\sqrt{n}$",
                 fontsize=12.5, y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "f1_calibration_models.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ==== F2: cross-dataset window calibration (DeepSeek: MATH500/AMC23/AIME24) =
def f2_datasets():
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    diag(ax)
    for key, lab, col in [("deepseek", "MATH500 (n=500)", BLUE),
                          ("amc23", "AMC23 (n=40)", TEAL),
                          ("aime24", "AIME24 (n=30)", MAGENTA)]:
        draw_calib(ax, load_pp(key), "window_share", lab, col, min_n=3)
    style(ax, "Window agreement (last-5 share)", "Final accuracy")
    ax.legend(frameon=False, loc="upper left", fontsize=10, title="DeepSeek-7B, by dataset difficulty")
    ax.set_title("Harder datasets → unanimous windows are less trustworthy", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "f2_calibration_datasets.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ==== F3: probe-wording ablation window calibration (simple vs certaindex) ==
def f3_probe():
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    diag(ax)
    draw_calib(ax, load_pp("deepseek"), "window_share", "simple  `\\boxed{`", BLUE)
    draw_calib(ax, load_pp("certaindex"), "window_share", "certaindex  “I suddenly got the answer”", PURPLE)
    style(ax, "Window agreement (last-5 share)", "Final accuracy")
    ax.legend(frameon=False, loc="upper left", fontsize=10, title="DeepSeek-7B · MATH500, by probe wording")
    ax.set_title("Probe wording barely moves calibration…", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "f3_calibration_probe.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ==== F4: early-stop cost dumbbell (all configs) ==========================
def stop_stats(df):
    st = df[df["stop_answer"].notna() & (df["stop_answer"].astype(str) != "")].copy()
    st["stop_correct"] = st["stop_correct"].astype(str).str.lower() == "true"
    stop_acc = st["stop_correct"].mean()
    compl_acc = st["final_correct"].mean()
    wrong = int((~st["stop_correct"]).sum())
    saved = (st["tokens_used"] - st["stop_tokens"]).mean()
    return dict(n_stop=len(st), n=len(df), stop_acc=stop_acc, compl_acc=compl_acc,
                gap=compl_acc - stop_acc, wrong=wrong, saved=saved,
                overall=df["final_correct"].mean())


def f4_earlystop():
    order = [("certaindex", "DeepSeek · MATH500\n(certaindex probe)"),
             ("qwen", "Qwen3-8B · MATH500"),
             ("amc23", "DeepSeek · AMC23"),
             ("deepseek", "DeepSeek · MATH500\n(simple probe)"),
             ("aime24", "DeepSeek · AIME24")]
    stats = [(lab, stop_stats(load_pp(k))) for k, lab in order]
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    ys = np.arange(len(stats))[::-1]
    for y, (lab, s) in zip(ys, stats):
        ax.plot([s["stop_acc"], s["compl_acc"]], [y, y], color="#c9c8c4", lw=3, zorder=1,
                solid_capstyle="round")
        ax.scatter([s["compl_acc"]], [y], s=130, color=GRAY, zorder=3,
                   label="let it finish (same problems, run to completion)" if y == ys[0] else None)
        ax.scatter([s["stop_acc"]], [y], s=130, color=ORANGE, zorder=3,
                   label="stop early (3-probe consensus)" if y == ys[0] else None)
        mid = (s["stop_acc"] + s["compl_acc"]) / 2
        gp = round(s["compl_acc"] * 100, 1) - round(s["stop_acc"] * 100, 1)  # match report's rounded-% convention
        ax.annotate(f"−{gp:.1f} pp", (mid, y), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=9.5, color="#b0392f", weight="bold")
        ax.annotate(f"{s['wrong']} wrong stops", (mid, y), textcoords="offset points",
                    xytext=(0, -15), ha="center", fontsize=8.3, color=GRAY)
    ax.set_yticks(ys)
    ax.set_yticklabels([lab for lab, _ in stats], fontsize=9.5)
    ax.set_xlim(0.15, 1.0)
    ax.set_xlabel("Accuracy on the problems the Governor would stop on")
    ax.legend(frameon=False, loc="lower right", fontsize=9.5)
    ax.set_title("How much accuracy the 3-probe early-stop rule sacrifices\n"
                 "(gap = the price of false consensus; wider = worse)", fontsize=12)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "f4_earlystop_cost.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return stats


# ==== F5: consensus-time vs accuracy (DeepSeek vs Qwen) ===================
CT_BINS = [0, 512, 1024, 1536, 2048, 10 ** 9]
CT_LAB = ["<512", "512–1024", "1024–1536", "1536–2048", ">2048"]


def ct_curve(df):
    x = df.dropna(subset=["consensus_time"]).copy()
    x["b"] = pd.cut(x["consensus_time"], bins=CT_BINS, labels=CT_LAB, right=False)
    acc, ns = [], []
    for lab in CT_LAB:
        sub = x[x["b"] == lab]
        acc.append(sub["final_correct"].mean() if len(sub) else np.nan)
        ns.append(len(sub))
    return acc, ns


def f5_consensus_time():
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    xs = np.arange(len(CT_LAB))
    for key, lab, col in [("deepseek", "DeepSeek-7B", BLUE), ("qwen", "Qwen3-8B", ORANGE)]:
        acc, ns = ct_curve(load_pp(key))
        ax.plot(xs, acc, color=col, lw=2, marker="o", ms=8, label=lab, markeredgecolor="white")
        for x, a, n in zip(xs, acc, ns):
            if not np.isnan(a):
                ax.annotate(f"n={n}", (x, a), textcoords="offset points", xytext=(0, 8),
                            ha="center", fontsize=8, color=col)
    ax.set_xticks(xs); ax.set_xticklabels(CT_LAB)
    ax.set_xlabel("Token position where window consensus first forms")
    ax.set_ylabel("Final accuracy"); ax.set_ylim(0.4, 1.0)
    ax.legend(frameon=False, loc="lower left", fontsize=10)
    ax.set_title("Later-forming consensus is less reliable (both models)", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "f5_consensus_time.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    f1_models()
    f2_datasets()
    f3_probe()
    stats = f4_earlystop()
    f5_consensus_time()
    print("figures written to", FIGDIR)
    for lab, s in stats:
        print(f"  {lab.splitlines()[0]:28s} stop_acc={s['stop_acc']:.3f} compl={s['compl_acc']:.3f} "
              f"gap={s['gap']*100:.1f}pp wrong={s['wrong']} saved={s['saved']:.0f} overall={s['overall']:.3f}")
