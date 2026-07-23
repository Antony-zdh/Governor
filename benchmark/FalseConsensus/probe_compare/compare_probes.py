"""Stage 8 -- compare the 5 probe designs against P0 (plan.md SS6.4 metrics).

Reads:
  - results/stage8_probe_compare/probe_variants.csv   (P1_32/P1_64/P2/P3/P4 per checkpoint)
  - results/stage8_probe_compare/variant_traj/*.json   (same, per-problem, with status/parse_ok)
  - results/stage1_logging/probes.csv                 (P0 per-checkpoint: probe_answer, is_certain)
  - results/stage1_logging/traj/*.json                (target / final_correct / tokens_used)

For each design (P0, P1_32, P1_64, P2, P3, P4) it computes the SS6.4 comparison
metrics on the SAME main trajectories and SAME checkpoints:

  empty_rate          -- P(answer == "") over all checkpoints
  parse_ok_rate       -- P(format followed)  (P0: proxied by 1-empty, continuation design)
  artifact_rate       -- 1 - parse_ok_rate   (format artifacts)
  valid_answer_rate   -- P(non-empty parsed answer)
  window CCE          -- calibration error of (window-share agreement vs final correctness)
  early-stop rate     -- Dynasor-style stop (last `bar` non-empty, "certain", mutually equal)
  early-stop accuracy -- correctness of the stopped answer
  token saving        -- avg tokens saved on stopped problems
  wrong-stops         -- stops on a wrong answer (cost of false consensus)
  readiness_precision -- (P2/P3/P4 only) P(answer correct | probe status says ready)
  probe_cost          -- nominal max-token budget + mean actual output length

No analytical narrative is invented: only the computed numbers are reported,
and the SS6.5 success criteria are checked as factual comparisons.
"""

import argparse
import json
import os
import re
import sys
from statistics import mean

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dynasor.core.evaluator import math_equal, strip_string  # noqa: E402

DESIGNS = ["P0", "P1_32", "P1_64", "P2", "P3", "P4"]
NEW_DESIGNS = ["P1_32", "P1_64", "P2", "P3", "P4"]
# nominal max_probe_tokens per design (from run_probe_variants.build_prompt / P0=10)
NOMINAL_BUDGET = {"P0": 10, "P1_32": 32, "P1_64": 64, "P2": 40, "P3": 50, "P4": 40}
# status values that mean "the probe declares the prefix ready" (P2/P3/P4)
READY_STATUS = {"P2": {"answer"}, "P3": {"answer", "confident"}, "P4": {"answer"}}

BINS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.999, 1.001]
BIN_LABELS = ["<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-<1", "=1.0"]


def unwrap_text(s):
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
    reps, counts = [], []
    for ans in answers:
        for i, rep in enumerate(reps):
            if eq(ans, rep):
                counts[i] += 1
                break
        else:
            reps.append(ans)
            counts.append(1)
    dominant = reps[int(np.argmax(counts))] if reps else ""
    return counts, dominant


def window_share(answers, w, min_nonempty=3):
    win = [a for a in answers[-w:] if a != ""]
    if len(win) < min_nonempty:
        return float("nan"), ""
    counts, dominant = group(win)
    return max(counts) / len(win), dominant


def correct_of(ans, target_raw):
    """Robust correctness vs the reference target (mirrors analyze.py)."""
    target = strip_string(target_raw)
    if eq(ans, target) or eq(ans, target_raw):
        return True
    deprefixed = re.sub(r"^\s*[a-zA-Z]\s*\\in\s*", "", target_raw)
    if deprefixed != target_raw and eq(ans, strip_string(deprefixed)):
        return True
    unwrapped = unwrap_text(target_raw)
    return unwrapped != "" and str(ans).strip().lower() == unwrapped.lower()


def load_p0(stage1_dir):
    """P0 per-checkpoint answers + is_certain, aligned by (problem_id, probe_id)."""
    df = pd.read_csv(os.path.join(stage1_dir, "probes.csv"), keep_default_na=False)
    out = {}  # pid -> list of (probe_id, token_position, answer, is_certain)
    for pid, g in df.groupby("problem_id"):
        g = g.sort_values("probe_id")
        out[int(pid)] = [
            (int(r.probe_id), int(r.token_position), str(r.probe_answer),
             str(r.is_certain).lower() == "true")
            for r in g.itertuples()
        ]
    return out


def load_new(variant_dir):
    """P1-P4 per-checkpoint answers, aligned by design -> pid -> list."""
    out = {d: {} for d in NEW_DESIGNS}
    for fn in sorted(os.listdir(variant_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(variant_dir, fn), encoding="utf-8") as f:
            data = json.load(f)
        pid = int(data["problem_id"])
        # ensure parse for each design
        per_design = {d: [] for d in NEW_DESIGNS}
        for r in data["results"]:
            d = r["design"]
            ans = "" if r.get("answer") is None else str(r["answer"])
            if pd.isna(r.get("answer", "")) if False else False:
                ans = ""
            per_design[d].append((
                int(r["probe_id"]), int(r["token_position"]), ans,
                str(r.get("status", "")), bool(r.get("parse_ok", False)),
                str(r.get("raw_output", ""))
            ))
        for d in NEW_DESIGNS:
            per_design[d].sort(key=lambda x: x[0])
            out[d][pid] = per_design[d]
    return out


def load_trajs(stage1_dir):
    trajs = {}
    d = os.path.join(stage1_dir, "traj")
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                t = json.load(f)
            trajs[int(t["problem_id"])] = t
    return trajs


def certain_predicates(design):
    """Return (is_certain_fn, status_ready_fn) for the Dynasor early-stop rule.

    is_certain_fn(checkpoint_tuple) -> bool : 'certainty' gate for the window.
    status_ready_fn(checkpoint_tuple) -> bool : explicit readiness (P2/P3/P4).
    """
    if design == "P0":
        return (lambda c: c[3]), (lambda c: False)
    if design in ("P1_32", "P1_64"):
        # continuation probe: no is_certain signal; treat non-empty answer as 'certain'
        return (lambda c: c[2] != ""), (lambda c: False)
    ready = READY_STATUS[design]
    # P2/P3/P4: 'certain' = probe explicitly returned an answer (status in ready set)
    return (lambda c: c[3] in ready), (lambda c: c[3] in ready and c[2] != "")


def compute_design(design, pids, seqs, trajs, bar, window):
    """seqs: pid -> checkpoint list (probe_id, tok, answer, [is_certain|status], parse_ok, raw)."""
    is_certain_fn, status_ready_fn = certain_predicates(design)
    rows = []
    # checkpoint-level aggregates
    n_cp = 0; n_empty = 0; n_parse_ok = 0; n_valid = 0
    out_lens = []
    ready_correct = 0; ready_total = 0
    for pid in pids:
        cps = seqs.get(pid, [])
        if not cps:
            continue
        tgt = trajs[pid]["target"]
        tokens_used = trajs[pid]["tokens_used"]
        answers = [c[2] for c in cps]
        tok_positions = [c[1] for c in cps]
        for c in cps:
            n_cp += 1
            ans = c[2]
            if ans == "":
                n_empty += 1
            if design == "P0":
                ok = ans != ""  # P0: parse_ok proxied by non-empty
            else:
                ok = c[4]  # parse_ok
            n_parse_ok += int(ok)
            if ans != "":
                n_valid += 1
                if design != "P0" and len(c) > 5:
                    out_lens.append(len(c[5]))
            # readiness precision (P2/P3/P4): status says ready AND answer non-empty
            if design in READY_STATUS and status_ready_fn(c):
                ready_total += 1
                if correct_of(ans, tgt):
                    ready_correct += 1
        # Dynasor-style early stop with this design's certainty gate
        stop_idx, stop_ans = None, None
        for t in range(bar - 1, len(answers)):
            win = answers[t - bar + 1: t + 1]
            cer = [is_certain_fn(cps[i]) for i in range(t - bar + 1, t + 1)]
            if all(a != "" for a in win) and all(cer) and all(eq(a, win[0]) for a in win[1:]):
                stop_idx, stop_ans = t, win[0]
                break
        w_share, _ = window_share(answers, window)
        rows.append({
            "problem_id": pid,
            "n_cp": len(cps),
            "window_share": w_share,
            "stop_idx": None if stop_idx is None else stop_idx + 1,
            "stop_tokens": None if stop_idx is None else tok_positions[stop_idx],
            "stop_answer": stop_ans,
            "stop_correct": None if stop_ans is None else correct_of(stop_ans, tgt),
            "final_correct": bool(trajs[pid]["final_correct"]),
            "tokens_used": tokens_used,
        })
    pp = pd.DataFrame(rows)
    if pp.empty:
        return None
    metrics = {
        "design": design,
        "n_problems": len(pp),
        "n_checkpoints": n_cp,
        "empty_rate": n_empty / n_cp if n_cp else float("nan"),
        "parse_ok_rate": n_parse_ok / n_cp if n_cp else float("nan"),
        "artifact_rate": 1 - (n_parse_ok / n_cp if n_cp else 0),
        "valid_answer_rate": n_valid / n_cp if n_cp else float("nan"),
        "mean_output_len": (mean(out_lens) if out_lens else 0),
        "nominal_budget": NOMINAL_BUDGET[design],
    }
    # calibration (window share vs final correctness), CCE
    have = pp[pp["window_share"].notna()].copy()
    if len(have):
        have["bin"] = pd.cut(have["window_share"], bins=BINS, labels=BIN_LABELS, right=False)
        cal = have.groupby("bin", observed=False).agg(
            n=("final_correct", "size"),
            mean_share=("window_share", "mean"),
            acc=("final_correct", "mean"),
        ).reset_index()
        cal = cal[cal["n"] > 0]
        if len(cal):
            metrics["window_cce"] = float(
                np.average(np.abs(cal["mean_share"] - cal["acc"]), weights=cal["n"]))
            metrics["n_with_share"] = int(len(have))
    # early-stop
    stopped = pp[pp["stop_answer"].notna()]
    metrics["stop_rate"] = len(stopped) / len(pp) if len(pp) else float("nan")
    if len(stopped):
        metrics["stop_accuracy"] = float(stopped["stop_correct"].mean())
        metrics["stop_final_acc"] = float(stopped["final_correct"].mean())
        metrics["token_saving"] = float((stopped["tokens_used"] - stopped["stop_tokens"]).mean())
        metrics["wrong_stops"] = int((stopped["stop_correct"] == False).sum())  # noqa: E712
    else:
        metrics["stop_accuracy"] = float("nan")
        metrics["stop_final_acc"] = float("nan")
        metrics["token_saving"] = float("nan")
        metrics["wrong_stops"] = 0
    # readiness precision (P2/P3/P4)
    if design in READY_STATUS:
        metrics["ready_rate"] = ready_total / n_cp if n_cp else float("nan")
        metrics["ready_precision"] = ready_correct / ready_total if ready_total else float("nan")
        metrics["ready_n"] = ready_total
    return metrics, pp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage8-dir",
                    default=os.path.join(os.path.dirname(__file__), "..", "results", "stage8_probe_compare"))
    ap.add_argument("--stage1-dir",
                    default=os.path.join(os.path.dirname(__file__), "..", "results", "stage1_logging"))
    ap.add_argument("--bar", type=int, default=3, help="Dynasor early-exit window")
    ap.add_argument("--window", type=int, default=5)
    args = ap.parse_args()

    variant_dir = os.path.join(args.stage8_dir, "variant_traj")
    trajs = load_trajs(args.stage1_dir)
    p0 = load_p0(args.stage1_dir)
    new = load_new(variant_dir)

    # subset = problems that have BOTH P0 and new-design trajectories
    subset_ids = sorted(set(p0) & set(trajs))
    # restrict to the 100-probe subset used in Stage 8 (those with variant_traj files)
    subset_ids = [p for p in subset_ids if any(p in new[d] for d in NEW_DESIGNS)]
    print(f"Comparing on {len(subset_ids)} problems (Stage 8 subset).")

    all_metrics = []
    pps = {}
    for d in DESIGNS:
        seqs = p0 if d == "P0" else new[d]
        res = compute_design(d, subset_ids, seqs, trajs, args.bar, args.window)
        if res is None:
            continue
        m, pp = res
        all_metrics.append(m)
        pps[d] = pp

    df = pd.DataFrame(all_metrics)
    # order columns nicely
    cols = ["design", "n_problems", "n_checkpoints", "empty_rate", "parse_ok_rate",
            "artifact_rate", "valid_answer_rate", "window_cce", "n_with_share",
            "stop_rate", "stop_accuracy", "stop_final_acc", "token_saving",
            "wrong_stops", "ready_rate", "ready_precision", "ready_n",
            "nominal_budget", "mean_output_len"]
    df = df[[c for c in cols if c in df.columns]]
    csv_path = os.path.join(args.stage8_dir, "comparison_table.csv")
    df.to_csv(csv_path, index=False)
    print(df.to_string(index=False))
    print("\nWrote", csv_path)

    # markdown report
    L = []
    L.append("# Stage 8 — Probe design comparison (SS6.4 metrics)\n")
    L.append(f"Compared on the same {len(subset_ids)} main trajectories / checkpoints "
             f"(Stage 8 subset). Dynasor early-stop window `bar={args.bar}`, agreement "
             f"window `{args.window}`. P0 = current 10-token probe (from probes.csv); "
             "P1_32/P1_64 = longer continuation budget; P2/P3/P4 = instruction/tag probes.\n")
    L.append("## Metric table\n")
    L.append(df.to_markdown(index=False, floatfmt=".3f"))
    L.append("")
    L.append("Notes:")
    L.append("- `parse_ok_rate` for P0 is proxied by P(answer non-empty) since P0 has no "
             "parse flag; for P1-P4 it is the recorded parser result.")
    L.append("- `artifact_rate = 1 - parse_ok_rate` (format not followed).")
    L.append("- `window_cce` = weighted mean |agreement_share - accuracy| over window-share "
             "bins (only problems with >=3 non-empty answers in the window contribute).")
    L.append("- `stop_*` use the Dynasor rule (last `bar` answers non-empty, design's "
             "certainty gate true, mutually equal). For P0 the gate is `is_certain`; "
             "P1 uses non-empty; P2/P3/P4 use the probe's explicit answer status.")
    L.append("- `ready_*` (P2/P3/P4 only): explicit readiness signal — precision = "
             "P(answer correct | probe status says ready).\n")
    L.append("## SS6.5 success-criteria check (factual, vs P0)\n")
    base = {m["design"]: m for m in all_metrics}["P0"]
    for d in NEW_DESIGNS:
        m = {x["design"]: x for x in all_metrics}[d]
        L.append(f"### {d}")
        L.append(f"- artifact_rate: {m['artifact_rate']:.3f} vs P0 {base['artifact_rate']:.3f} "
                 f"→ {'lower' if m['artifact_rate'] < base['artifact_rate'] else 'not lower'}")
        L.append(f"- empty_rate: {m['empty_rate']:.3f} vs P0 {base['empty_rate']:.3f} "
                 f"→ {'lower' if m['empty_rate'] < base['empty_rate'] else 'not lower'}")
        sa = m.get('stop_accuracy'); ba = base.get('stop_accuracy')
        ts = m.get('token_saving'); ts_b = base.get('token_saving')
        if sa is not None and ba is not None and not np.isnan(sa) and not np.isnan(ba):
            L.append(f"- early-stop accuracy: {sa:.3f} vs P0 {ba:.3f} "
                     f"→ {'higher' if sa > ba else 'not higher'}"
                     f"  (token saving {ts:.0f} vs P0 {ts_b:.0f})")
        else:
            L.append(f"- early-stop: stop_rate={m.get('stop_rate'):.3f} "
                     f"(P0 {base.get('stop_rate'):.3f}); accuracy/token-saving N/A "
                     "(design rarely/never produces a stop window).")
        L.append("")
    md_path = os.path.join(args.stage8_dir, "comparison_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("Wrote", md_path)

    try:
        fig_path = plot_comparison(df, args.stage8_dir)
        print("Wrote", fig_path)
    except Exception as e:  # figure is optional; table+report already written
        print("Figure skipped:", e)


def plot_comparison(df, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    BLUE, ORANGE, GRAY, GRID = "#2a78d6", "#eb6834", "#52514e", "#e6e5e1"
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white", "axes.edgecolor": GRID,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
        "text.color": "#0b0b0b", "axes.labelcolor": "#52514e",
        "xtick.color": "#52514e", "ytick.color": "#52514e"})
    d = df.set_index("design").loc[DESIGNS].reset_index()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    x = np.arange(len(d)); w = 0.38
    ax1.bar(x - w/2, d["empty_rate"], w, color=BLUE, label="empty_rate")
    ax1.bar(x + w/2, d["artifact_rate"], w, color=ORANGE, label="artifact_rate")
    for xi, (e, a) in enumerate(zip(d["empty_rate"], d["artifact_rate"])):
        ax1.annotate(f"{e:.0%}", (xi - w/2, e), ha="center", va="bottom", fontsize=8, color=BLUE)
        ax1.annotate(f"{a:.0%}", (xi + w/2, a), ha="center", va="bottom", fontsize=8, color=ORANGE)
    ax1.set_xticks(x, d["design"]); ax1.set_ylim(0, 1.08)
    ax1.set_ylabel("rate"); ax1.set_title("Empty & artifact rate per probe design")
    ax1.legend(frameon=False, loc="upper right", fontsize=9)

    # Pareto: stop accuracy vs token saving, point size ~ stop_rate
    sa = d["stop_accuracy"].astype(float)
    ts = d["token_saving"].astype(float)
    sr = d["stop_rate"].astype(float).fillna(0)
    sizes = 40 + 320 * sr
    colors_l = [BLUE if s == "P0" else ORANGE for s in d["design"]]
    for xi, (a, t, si, c, lab) in enumerate(zip(sa, ts, sizes, colors_l, d["design"])):
        if not np.isnan(a) and not np.isnan(t):
            ax2.scatter([t], [a], s=[si], color=c, alpha=0.8, edgecolor="white", linewidth=1.2)
            ax2.annotate(lab, (t, a), textcoords="offset points", xytext=(6, 4), fontsize=9)
    ax2.set_xlabel("token saving on stopped problems")
    ax2.set_ylabel("early-stop accuracy")
    ax2.set_title("Early-stop Pareto (size ∝ stop_rate)")
    ax2.set_ylim(0.5, 0.95)
    fig.tight_layout()
    path = os.path.join(out_dir, "fig_compare.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


if __name__ == "__main__":
    main()
