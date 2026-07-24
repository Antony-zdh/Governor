"""Stages 2-5 analysis for the False Consensus project.

Reads Stage 1 output (probes.csv + traj/*.json) and produces:

  Stage 2  Agreement vs Accuracy
    fig1_calibration.png       calibration on cumulative share (plan.md def)
    fig1b_window_calibration.png  calibration on last-5-probe window share
    fig2_share_hist.png        distribution of final agreement
  Stage 3  False Consensus export
    false_consensus_cases.json / .md
    (cumulative share=1 AND wrong, plus window-unanimous AND wrong)
  Stage 4  Trajectory analysis
    fig4_consensus_time.png    consensus time (window share) vs accuracy
    recovery / initial-belief statistics
  Stage 5  Consensus reliability + Governor-style early-stop simulation
    fig5_reliability.png       CR(s) = P(correct | share = s) + CCE

  report.md   all tables and headline numbers
"""

import argparse
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dynasor.core.evaluator import math_equal, strip_string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "TokenDeprivation"))
from utils import load_dataset  # noqa: E402

# dataviz reference palette (light mode)
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRAY = "#52514e"
GRID = "#e6e5e1"

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": GRID,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
        "text.color": "#0b0b0b",
        "axes.labelcolor": "#52514e",
        "xtick.color": "#52514e",
        "ytick.color": "#52514e",
    }
)

BINS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.999, 1.001]
BIN_LABELS = ["<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-<1", "=1.0"]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=str, default="math500")
    p.add_argument("--input", type=str, default="results/stage1_logging")
    p.add_argument("--output", type=str, default=None, help="defaults to <input>/analysis")
    p.add_argument("--window", type=int, default=5, help="window size for window share")
    p.add_argument("--certain-bar", type=int, default=3, help="Dynasor early-exit window")
    p.add_argument("--consensus-share", type=float, default=0.8)
    p.add_argument("--min-probes-for-consensus", type=int, default=3)
    p.add_argument("--model-label", type=str, default="DeepSeek-R1-Distill-7B",
                   help="series label shown in the calibration figure legends "
                        "(set this on cross-model runs, e.g. --model-label Qwen3-8B)")
    return p.parse_args()


import re


def unwrap_text(s):
    """`\\text{east}` -> `east` (strip_string erases \\text{...} to '')."""
    return re.sub(r"\\text\s*\{([^{}]*)\}", r"\1", str(s)).strip()


def eq(a, b):
    a, b = str(a), str(b)
    if a == "" or b == "":
        return a == b
    if a == b:
        return True
    try:
        return bool(math_equal(a, b))
    except Exception:
        return False


def group(answers):
    """Group answers into math-equivalence classes -> (counts, dominant)."""
    reps, counts = [], []
    for ans in answers:
        for i, rep in enumerate(reps):
            if eq(ans, rep):
                counts[i] += 1
                break
        else:
            reps.append(ans)
            counts.append(1)
    dominant = reps[int(np.argmax(counts))]
    return counts, dominant


def window_share(answers, w, min_nonempty=3):
    """Share over the non-empty answers in the last-w window.

    Empty probe answers (extraction failures / answers that don't fit in the
    probe budget) carry no agreement signal — a window needs at least
    `min_nonempty` real answers to define a share, else NaN.
    """
    win = [a for a in answers[-w:] if a != ""]
    if len(win) < min_nonempty:
        return float("nan"), ""
    counts, dominant = group(win)
    return max(counts) / len(win), dominant


def load(input_dir):
    df = pd.read_csv(os.path.join(input_dir, "probes.csv"), keep_default_na=False)
    df["final_correct"] = df["final_correct"].astype(str).str.lower() == "true"
    df["is_certain"] = df["is_certain"].astype(str).str.lower() == "true"
    trajs = {}
    traj_dir = os.path.join(input_dir, "traj")
    for name in sorted(os.listdir(traj_dir)):
        if name.endswith(".json"):
            with open(os.path.join(traj_dir, name), encoding="utf-8") as f:
                t = json.load(f)
            trajs[t["problem_id"]] = t
    return df, trajs


def per_problem(df, trajs, args, raw_targets):
    rows = []
    for pid, g in df.groupby("problem_id"):
        g = g.sort_values("probe_id")
        last = g.iloc[-1]
        answers = [str(a) for a in g["probe_answer"]]
        certains = list(g["is_certain"])
        tokens = list(g["token_position"])
        raw = str(raw_targets[pid])
        target = strip_string(raw)

        def correct_of(ans):
            # robust against strip_string mangling the reference answer
            # (e.g. `\text{east}` -> ""): match any surviving form
            if eq(ans, target) or eq(ans, raw):
                return True
            # `x\in[-2,7]` -> `[-2,7]`
            deprefixed = re.sub(r"^\s*[a-zA-Z]\s*\\in\s*", "", raw)
            if deprefixed != raw and eq(ans, strip_string(deprefixed)):
                return True
            unwrapped = unwrap_text(raw)
            return unwrapped != "" and str(ans).strip().lower() == unwrapped.lower()

        final_answer = str(last["final_answer"])
        final_correct = correct_of(final_answer)

        w_share, w_dom = window_share(answers, args.window)

        # Dynasor-style early stop: first probe where the last `bar` answers
        # are non-empty, mutually equal, and all certain.
        bar = args.certain_bar
        stop_idx, stop_answer = None, None
        for t in range(bar - 1, len(answers)):
            win = answers[t - bar + 1 : t + 1]
            cert = certains[t - bar + 1 : t + 1]
            if all(a != "" for a in win) and all(cert) and all(eq(a, win[0]) for a in win[1:]):
                stop_idx, stop_answer = t, win[0]
                break

        # consensus time: first probe (>= min_probes) where window share >= thr
        ct = None
        for t in range(args.min_probes_for_consensus - 1, len(answers)):
            s, _ = window_share(answers[max(0, t + 1 - args.window) : t + 1], args.window)
            if not np.isnan(s) and s >= args.consensus_share:
                ct = tokens[t]
                break

        rows.append(
            {
                "problem_id": pid,
                "n_probes": len(g),
                "final_share": last["share"],
                "final_entropy": last["entropy"],
                "unique_answers": last["unique_answers"],
                "dominant_answer": str(last["dominant_answer"]),
                "final_answer": final_answer,
                "final_correct": final_correct,
                "target": target if target else raw,
                "probe1_answer": answers[0],
                "probe1_correct": correct_of(answers[0]),
                "window_share": w_share,
                "window_dominant": w_dom,
                "window_dominant_correct": correct_of(w_dom) if w_dom else None,
                "stop_probe_idx": None if stop_idx is None else stop_idx + 1,
                "stop_tokens": None if stop_idx is None else tokens[stop_idx],
                "stop_answer": stop_answer,
                "stop_correct": None if stop_answer is None else correct_of(stop_answer),
                "consensus_time": ct,
                "tokens_used": trajs[pid]["tokens_used"],
                "finished_naturally": trajs[pid]["finished_naturally"],
            }
        )
    return pd.DataFrame(rows).set_index("problem_id")


def bin_calibration(pp, col):
    x = pp.copy()
    x["bin"] = pd.cut(x[col], bins=BINS, labels=BIN_LABELS, right=False)
    out = []
    for label in BIN_LABELS:
        sub = x[x["bin"] == label]
        if len(sub):
            out.append(
                {
                    "bin": label,
                    "n": len(sub),
                    "mean_share": sub[col].mean(),
                    "accuracy": sub["final_correct"].mean(),
                }
            )
    return pd.DataFrame(out)


def plot_calibration(cal, path, title, series_label, min_n=3):
    cal = cal[cal["n"] >= min_n]  # tiny bins are noise, keep them in the table only
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot([0, 1], [0, 1], ls="--", lw=1, color=GRAY, label="Perfect calibration")
    ax.plot(cal["mean_share"], cal["accuracy"], color=BLUE, lw=2, marker="o", ms=8, label=series_label)
    for _, r in cal.iterrows():
        ax.annotate(
            f"{r['accuracy']:.0%}\n(n={r['n']})",
            (r["mean_share"], r["accuracy"]),
            textcoords="offset points",
            xytext=(0, -26),
            ha="center",
            fontsize=8,
            color="#52514e",
        )
    ax.set_xlabel("Agreement (dominant answer share)")
    ax.set_ylabel("Accuracy")
    ax.set_title(title)
    ax.set_xlim(0.25, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def fig2_hist(pp, path):
    fig, ax = plt.subplots(figsize=(6, 4))
    bins = np.arange(0.0, 1.1, 0.1)
    ax.hist(pp["final_share"], bins=bins, color=BLUE, edgecolor="white", linewidth=2)
    ax.set_xlabel("Final agreement (dominant answer share, cumulative)")
    ax.set_ylabel("Number of problems")
    ax.set_title("Figure 2 · Agreement distribution")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def fig4_consensus_time(pp, path, thr):
    have = pp[pp["consensus_time"].notna()]
    ts = have["consensus_time"].astype(float).values
    corr = have["final_correct"].values
    edges = [0, 512, 1024, 1536, 2048, 3200]
    labels = ["<512", "512-1024", "1024-1536", "1536-2048", ">2048"]
    accs, ns = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (ts >= lo) & (ts < hi)
        ns.append(int(m.sum()))
        accs.append(float(corr[m].mean()) if m.sum() else np.nan)
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(labels))
    ax.bar(x, accs, color=BLUE, width=0.62, edgecolor="white")
    for xi, (a, n) in enumerate(zip(accs, ns)):
        if not np.isnan(a):
            ax.annotate(f"{a:.0%}\nn={n}", (xi, a), ha="center", va="bottom", fontsize=9, color="#52514e")
    ax.set_xticks(x, labels)
    ax.set_xlabel(f"Consensus time (tokens until window share ≥ {thr}, ≥3 probes)")
    ax.set_ylabel("Final accuracy")
    ax.set_ylim(0, 1.12)
    ax.set_title("Figure 4 · When consensus forms vs accuracy")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return {l: (n, None if np.isnan(a) else round(a, 3)) for l, n, a in zip(labels, ns, accs)}


def fig5_reliability(cal, path, min_n=3):
    cal = cal[cal["n"] >= min_n].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    x = np.arange(len(cal))
    ax.bar(x, cal["accuracy"], color=BLUE, width=0.62, edgecolor="white", label="P(correct | share)")
    ax.plot(x, cal["mean_share"], color=ORANGE, lw=2, marker="o", ms=7, label="Agreement (share)")
    for xi, (_, r) in enumerate(cal.iterrows()):
        gap = r["mean_share"] - r["accuracy"]
        ax.annotate(
            f"{gap:+.0%}", (xi, max(r["accuracy"], r["mean_share"])),
            textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8, color="#52514e",
        )
    ax.set_xticks(x, cal["bin"])
    ax.set_xlabel("Window-share bin (last 5 probes)")
    ax.set_ylabel("Probability")
    ax.set_ylim(0, 1.18)
    ax.set_title("Figure 5 · Consensus reliability (gap = calibration error)")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def export_cases(pp, trajs, out_dir):
    cum_fc = pp[
        (pp["final_share"] >= 1.0)
        & (pp["dominant_answer"].astype(str) != "")
        & (~pp["final_correct"])
    ]
    win_fc = pp[(pp["window_share"] >= 1.0) & (pp["window_dominant_correct"] == False)]  # noqa: E712
    stop_fc = pp[(pp["stop_answer"].notna()) & (pp["stop_correct"] == False)]  # noqa: E712
    ids = sorted(set(cum_fc.index) | set(win_fc.index) | set(stop_fc.index))
    cases = []
    for pid in ids:
        t = trajs[pid]
        cases.append(
            {
                "problem_id": int(pid),
                "kind": {
                    "cumulative_share1_wrong": bool(pid in cum_fc.index),
                    "window_unanimous_wrong": bool(pid in win_fc.index),
                    "governor_stop_wrong": bool(pid in stop_fc.index),
                },
                "problem": t["problem"],
                "target": t["target"],
                "final_answer": str(pp.loc[pid, "final_answer"]),
                "final_correct": bool(pp.loc[pid, "final_correct"]),
                "stop_answer": pp.loc[pid, "stop_answer"],
                "probe_answers": [p["answer"] for p in t["probes"]],
                "full_text": t["full_text"],
            }
        )
    with open(os.path.join(out_dir, "false_consensus_cases.json"), "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "false_consensus_cases.md"), "w", encoding="utf-8") as f:
        f.write("# False consensus cases\n\n")
        for c in cases:
            kinds = ", ".join(k for k, v in c["kind"].items() if v)
            f.write(
                f"## Problem {c['problem_id']}  ({kinds})\n\n"
                f"**Problem:** {c['problem']}\n\n"
                f"**Target:** `{c['target']}`  |  **Final:** `{c['final_answer']}`"
                f" (correct={c['final_correct']})  |  **Stop answer:** `{c['stop_answer']}`\n\n"
                f"**Probe answers:** {c['probe_answers']}\n\n---\n\n"
            )
    return cum_fc, win_fc, stop_fc, cases


def main():
    args = parse_args()
    out_dir = args.output or os.path.join(args.input, "analysis")
    os.makedirs(out_dir, exist_ok=True)
    df, trajs = load(args.input)
    raw_targets = {i: item["answer"] for i, item in enumerate(load_dataset(args.dataset))}
    pp = per_problem(df, trajs, args, raw_targets)
    pp.to_csv(os.path.join(out_dir, "per_problem.csv"))

    n_total = len(trajs)
    overall_acc = pp["final_correct"].mean()
    finished = np.mean([t["finished_naturally"] for t in trajs.values()])

    cal_cum = bin_calibration(pp, "final_share")
    cal_win = bin_calibration(pp[pp["window_share"].notna()], "window_share")
    plot_calibration(
        cal_cum, os.path.join(out_dir, "fig1_calibration.png"),
        "Figure 1 · Agreement vs Accuracy (cumulative share)", args.model_label,
    )
    plot_calibration(
        cal_win, os.path.join(out_dir, "fig1b_window_calibration.png"),
        f"Figure 1b · Agreement vs Accuracy (last-{args.window} window share)", args.model_label,
    )
    fig2_hist(pp, os.path.join(out_dir, "fig2_share_hist.png"))
    cum_fc, win_fc, stop_fc, cases = export_cases(pp, trajs, out_dir)
    ct_table = fig4_consensus_time(pp, os.path.join(out_dir, "fig4_consensus_time.png"), args.consensus_share)
    fig5_reliability(cal_win, os.path.join(out_dir, "fig5_reliability.png"))

    cce_cum = float(np.average(np.abs(cal_cum["mean_share"] - cal_cum["accuracy"]), weights=cal_cum["n"]))
    cce_win = float(np.average(np.abs(cal_win["mean_share"] - cal_win["accuracy"]), weights=cal_win["n"]))

    # exclude problems whose "consensus" is a run of empty probe answers
    # (answer too long for the probe budget carries no agreement signal)
    unan_cum = pp[(pp["final_share"] >= 1.0) & (pp["dominant_answer"].astype(str) != "")]
    unan_win = pp[pp["window_share"] >= 1.0]
    stopped = pp[pp["stop_answer"].notna()]

    # Recovery: window-unanimous (>= bar probes agreeing) on an answer that
    # differs from the final answer.
    recovered, rec_correct = [], 0
    for pid, r in pp.iterrows():
        answers = [str(a) for a in df[df["problem_id"] == pid].sort_values("probe_id")["probe_answer"]]
        bar = args.certain_bar
        for t in range(bar - 1, len(answers)):
            win = answers[t - bar + 1 : t + 1]
            if all(a != "" for a in win) and all(eq(a, win[0]) for a in win[1:]):
                if not eq(win[0], r["final_answer"]):
                    recovered.append(pid)
                    rec_correct += int(r["final_correct"])
                break

    p1c = pp["probe1_correct"]
    p1_wrong = pp[~p1c]

    L = []
    L.append("# False Consensus — Stage 2-5 report\n")
    L.append(f"- problems logged: **{n_total}**")
    L.append(f"- overall accuracy: **{overall_acc:.1%}**, finished naturally within budget: {finished:.1%}")
    L.append("")
    L.append("## Stage 2 · Agreement vs Accuracy\n")
    L.append("Cumulative share (plan.md definition, all probes of the trajectory):\n")
    L.append(cal_cum.to_markdown(index=False, floatfmt=".3f"))
    L.append("")
    L.append(f"Window share (last {args.window} probes — what a Governor actually sees):\n")
    L.append(cal_win.to_markdown(index=False, floatfmt=".3f"))
    L.append("")
    L.append(
        f"- cumulative share=1: {len(unan_cum)} problems, accuracy {unan_cum['final_correct'].mean():.1%} "
        f"→ false consensus {len(cum_fc)}"
    )
    L.append(
        f"- window share=1: {len(unan_win)} problems, window-answer accuracy "
        f"{unan_win['window_dominant_correct'].mean():.1%} → **false consensus {len(win_fc)} "
        f"({len(win_fc) / max(len(unan_win), 1):.1%} of unanimous)**"
    )
    L.append("")
    L.append("## Stage 3 · False consensus cases\n")
    L.append(f"Exported {len(cases)} cases: {[c['problem_id'] for c in cases]}")
    L.append("")
    L.append("## Stage 4 · Trajectory\n")
    for k, (n, a) in ct_table.items():
        L.append(f"- consensus at {k} tokens: n={n}, accuracy={'-' if a is None else f'{a:.1%}'}")
    L.append(f"- never reached window share ≥ {args.consensus_share}: {int(pp['consensus_time'].isna().sum())}")
    L.append("")
    L.append(
        f"Recovery: {len(recovered)} problems held a {args.certain_bar}-probe consensus that "
        f"differed from their final answer ({rec_correct} of them ended correct): {sorted(map(int, recovered))}"
    )
    L.append(
        f"Initial belief: probe1 correct in {int(p1c.sum())}/{len(pp)}; of the {len(p1_wrong)} "
        f"problems with wrong probe1, **{int(p1_wrong['final_correct'].sum())} "
        f"({p1_wrong['final_correct'].mean():.1%}) recovered to a correct final answer**."
    )
    L.append("")
    L.append("## Stage 5 · Consensus reliability + Governor simulation\n")
    L.append(f"- CR(cumulative share=1) = {unan_cum['final_correct'].mean():.3f}")
    L.append(f"- CR(window share=1) = {unan_win['window_dominant_correct'].mean():.3f}")
    L.append(f"- Consensus Calibration Error: cumulative = {cce_cum:.3f}, window = {cce_win:.3f}")
    L.append("")
    if len(stopped):
        saved = (stopped["tokens_used"] - stopped["stop_tokens"]).mean()
        L.append(
            f"Governor early-stop simulation (stop when last {args.certain_bar} probes agree, certain, non-empty):\n"
            f"- would stop on {len(stopped)}/{len(pp)} problems, stopped-answer accuracy "
            f"**{stopped['stop_correct'].mean():.1%}** (vs their final accuracy {stopped['final_correct'].mean():.1%})\n"
            f"- avg tokens saved on stopped problems: {saved:.0f}\n"
            f"- stops on a WRONG answer (the cost of false consensus): {len(stop_fc)} problems "
            f"{sorted(map(int, stop_fc.index))}"
        )
    report = "\n".join(L)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print("\nFigures and tables written to", out_dir)


if __name__ == "__main__":
    main()
