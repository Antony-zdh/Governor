"""Stage 7 — offline stop-rule Pareto sweep (plan.md §5).

Replays many candidate early-stop rules against the existing Stage 1 logs
(no model server needed) and reports the accuracy/token-saving frontier,
answering: is there a rule that clearly beats "3 consecutive same answers"
(which already loses 16.4pp accuracy per the Stage 2-5 report)?

Grid: plan.md §5.2 lists 6+ independent parameters whose full cross product
is unions of ~60k meaningless combinations at n=500. Instead this grids a
representative subset per rule family (documented inline, and the exact
config count is printed and written to report.md) rather than the full
cartesian product.

Data limitation: logging_run.py never recorded per-request latency, so
wall_clock / prefill_cost_estimate (plan.md §5.5) are not available here.
Only token-based costs are reported; this gap is called out in report.md
rather than papering over it with fabricated timing numbers.
"""

import argparse
import json
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import analyze  # noqa: E402
from analyze import BLUE, GRAY, GRID, ORANGE, group, load, strip_string, unwrap_text  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "TokenDeprivation"))
from utils import load_dataset  # noqa: E402

SINGLE_LETTER_RE = re.compile(r"^[A-Da-d]$")
PROBE_OUTPUT_TOKENS = 10  # probe_tokens default in logging_run.py

# math_equal (sympy-based) is expensive and the same small set of distinct
# per-problem answer strings gets compared over and over across ~150 rule
# configs. Memoize pairwise results globally, and monkeypatch analyze.group's
# `eq` lookup too since it resolves `eq` from analyze.py's own module globals.
_EQ_CACHE = {}
_real_eq = analyze.eq


def eq(a, b):
    a, b = str(a), str(b)
    if a == b:
        return True
    key = (a, b) if a <= b else (b, a)
    if key not in _EQ_CACHE:
        _EQ_CACHE[key] = _real_eq(a, b)
    return _EQ_CACHE[key]


analyze.eq = eq


# ---------------------------------------------------------------------------
# Ground truth (mirrors analyze.py's per_problem() correct_of closure exactly,
# since that closure isn't exported as a standalone function)
# ---------------------------------------------------------------------------


def make_correct_of(raw_targets, pid):
    raw = str(raw_targets[pid])
    target = strip_string(raw)

    def correct_of(ans):
        if eq(ans, target) or eq(ans, raw):
            return True
        deprefixed = re.sub(r"^\s*[a-zA-Z]\s*\\in\s*", "", raw)
        if deprefixed != raw and eq(ans, strip_string(deprefixed)):
            return True
        unwrapped = unwrap_text(raw)
        return unwrapped != "" and str(ans).strip().lower() == unwrapped.lower()

    return correct_of


# ---------------------------------------------------------------------------
# Validity filters (plan.md §5.2 validity_filter)
# ---------------------------------------------------------------------------


def apply_validity_filter(answers, mode):
    if mode in (None, "none"):
        return list(answers)
    if mode == "nonempty_only":
        return list(answers)
    if mode in ("nonempty_and_nonletter", "answer_type_aware"):
        # answer_type_aware is a placeholder: Stage 6 human annotation
        # (benchmark/FalseConsensus/audit/) hasn't been completed yet, so
        # there is no real per-answer-type label to filter on. Until it is,
        # this mode is identical to nonempty_and_nonletter — documented here
        # rather than fabricated.
        return ["" if SINGLE_LETTER_RE.match(a) else a for a in answers]
    raise ValueError(mode)


# ---------------------------------------------------------------------------
# Rule simulators — each returns (stop_idx, stop_answer) or (None, None)
# ---------------------------------------------------------------------------


def simulate_vanilla(n):
    return None, None


def simulate_hard_cap(tok, dominant_cum, cap_tokens):
    for t in range(len(tok)):
        if tok[t] >= cap_tokens:
            return t, dominant_cum[t]
    return None, None


def simulate_consecutive(tok, raw_ans, cert, patience, min_tokens, require_certain, validity_mode):
    ans = apply_validity_filter(raw_ans, validity_mode)
    require_nonempty = validity_mode not in (None, "none")
    n = len(ans)
    for t in range(patience - 1, n):
        if tok[t] < min_tokens:
            continue
        window = ans[t - patience + 1 : t + 1]
        if require_nonempty and any(a == "" for a in window):
            continue
        if require_certain and not all(cert[t - patience + 1 : t + 1]):
            continue
        if all(eq(a, window[0]) for a in window[1:]):
            return t, window[0]
    return None, None


def simulate_window_share(tok, raw_ans, window_size, share_threshold, min_valid_probes, min_tokens, validity_mode, max_switches=None):
    ans = apply_validity_filter(raw_ans, validity_mode)
    n = len(ans)
    switches = 0
    last_seen = None
    for t in range(n):
        if ans[t] != "":
            if last_seen is not None and not eq(ans[t], last_seen):
                switches += 1
            last_seen = ans[t]
        if tok[t] < min_tokens:
            continue
        win = ans[max(0, t - window_size + 1) : t + 1]
        nonempty_win = [a for a in win if a != ""]
        if len(nonempty_win) < min_valid_probes:
            continue
        counts, dominant = group(nonempty_win)
        share = max(counts) / len(nonempty_win)
        if share < share_threshold:
            continue
        if max_switches is not None and switches > max_switches:
            continue
        return t, dominant
    return None, None


def simulate_entropy(tok, entropy_arr, dominant_cum, min_tokens, mode, threshold=None, k=None):
    n = len(entropy_arr)
    for t in range(n):
        if tok[t] < min_tokens:
            continue
        if mode == "current_entropy_below_threshold":
            if entropy_arr[t] <= threshold:
                return t, dominant_cum[t]
        elif mode == "low_entropy_for_k_steps":
            if t - k + 1 >= 0 and all(e <= threshold for e in entropy_arr[t - k + 1 : t + 1]):
                return t, dominant_cum[t]
        elif mode == "non_increasing_last_k":
            if t - k + 1 >= 0:
                w = entropy_arr[t - k + 1 : t + 1]
                if all(w[i] <= w[i - 1] + 1e-9 for i in range(1, len(w))):
                    return t, dominant_cum[t]
    return None, None


def simulate_production_bug(raw_ans, cert):
    """Reproduces the actual pre-fix should_early_exit behavior: stops as
    soon as >=2 probes exist and the LATEST probe's text has no uncertain
    words — the nested consistency/non-empty/equal-group checks were dead
    code (log.md 2026-07-23), so they are deliberately NOT applied here."""
    n = len(raw_ans)
    bar = 2
    for t in range(bar - 1, n):
        if cert[t]:
            return t, raw_ans[t]
    return None, None


# ---------------------------------------------------------------------------
# Config grid (representative subset per family, not full cross product)
# ---------------------------------------------------------------------------


def build_configs():
    configs = []

    configs.append({"config_id": "vanilla", "family": "vanilla", "label": "Vanilla (full generation)"})

    for cap in [512, 1024, 1536, 2048, 3072]:
        configs.append(
            {"config_id": f"hard_cap_{cap}", "family": "hard_cap", "label": f"Hard cap {cap} tok", "cap_tokens": cap}
        )

    for patience in [3, 4, 5, 6, 8]:
        for min_tokens in [0, 512, 1024, 2048]:
            for require_certain in [True, False]:
                cid = f"consec_p{patience}_mt{min_tokens}_cert{int(require_certain)}"
                configs.append(
                    {
                        "config_id": cid,
                        "family": "consecutive",
                        "label": f"{patience}-consecutive, min_tok={min_tokens}, certain={require_certain}",
                        "patience": patience,
                        "min_tokens": min_tokens,
                        "require_certain": require_certain,
                        "validity_mode": "nonempty_only",
                    }
                )

    for window_size in [3, 5, 8]:
        for share_threshold in [0.6, 0.8, 1.0]:
            for min_valid in [3, 5, 8]:
                for min_tokens in [0, 512]:
                    cid = f"window_w{window_size}_s{share_threshold}_mv{min_valid}_mt{min_tokens}"
                    configs.append(
                        {
                            "config_id": cid,
                            "family": "window_share",
                            "label": f"window={window_size}, share>={share_threshold}, min_valid={min_valid}, min_tok={min_tokens}",
                            "window_size": window_size,
                            "share_threshold": share_threshold,
                            "min_valid_probes": min_valid,
                            "min_tokens": min_tokens,
                            "validity_mode": "nonempty_only",
                        }
                    )

    for mode in ["none", "nonempty_and_nonletter", "answer_type_aware"]:
        cid = f"window_validity_{mode}"
        configs.append(
            {
                "config_id": cid,
                "family": "window_share",
                "label": f"window=5, share>=0.8, min_valid=5, min_tok=512, validity={mode}",
                "window_size": 5,
                "share_threshold": 0.8,
                "min_valid_probes": 5,
                "min_tokens": 512,
                "validity_mode": mode,
            }
        )

    for share_threshold in [0.8, 1.0]:
        for max_switches in [0, 1, 2, None]:
            cid = f"history_s{share_threshold}_switch{max_switches}"
            configs.append(
                {
                    "config_id": cid,
                    "family": "window_share",
                    "label": f"history-aware: window=5, share>={share_threshold}, min_valid=5, min_tok=512, max_switches={max_switches}",
                    "window_size": 5,
                    "share_threshold": share_threshold,
                    "min_valid_probes": 5,
                    "min_tokens": 512,
                    "validity_mode": "nonempty_only",
                    "max_switches": max_switches,
                }
            )

    for threshold in [0.0, 0.3, 0.5]:
        for min_tokens in [0, 512]:
            cid = f"entropy_below_{threshold}_mt{min_tokens}"
            configs.append(
                {
                    "config_id": cid,
                    "family": "entropy",
                    "label": f"entropy<={threshold}, min_tok={min_tokens}",
                    "entropy_mode": "current_entropy_below_threshold",
                    "threshold": threshold,
                    "min_tokens": min_tokens,
                }
            )
    for threshold in [0.0, 0.3, 0.5]:
        for k in [3, 5, 8]:
            for min_tokens in [0, 512]:
                cid = f"entropy_lowk_{threshold}_k{k}_mt{min_tokens}"
                configs.append(
                    {
                        "config_id": cid,
                        "family": "entropy",
                        "label": f"entropy<={threshold} for {k} steps, min_tok={min_tokens}",
                        "entropy_mode": "low_entropy_for_k_steps",
                        "threshold": threshold,
                        "k": k,
                        "min_tokens": min_tokens,
                    }
                )
    for k in [3, 5, 8]:
        for min_tokens in [0, 512]:
            cid = f"entropy_nonincr_k{k}_mt{min_tokens}"
            configs.append(
                {
                    "config_id": cid,
                    "family": "entropy",
                    "label": f"entropy non-increasing for {k} steps, min_tok={min_tokens}",
                    "entropy_mode": "non_increasing_last_k",
                    "k": k,
                    "min_tokens": min_tokens,
                }
            )

    configs.append(
        {
            "config_id": "production_bug_prefix",
            "family": "production_bug",
            "label": "Actual pre-fix production should_early_exit (window=2, no consistency check)",
        }
    )

    return configs


def run_config(cfg, problems):
    """problems: list of dicts with precomputed per-problem arrays. Returns
    a list of (pid, stop_idx, stop_answer) for problems where the rule
    triggered, using None for stop_idx when it didn't."""
    out = []
    fam = cfg["family"]
    for p in problems:
        tok, ans, cert, entropy_arr, dominant_cum = p["tok"], p["ans"], p["cert"], p["entropy"], p["dominant_cum"]
        if fam == "vanilla":
            stop_idx, stop_ans = None, None
        elif fam == "hard_cap":
            stop_idx, stop_ans = simulate_hard_cap(tok, dominant_cum, cfg["cap_tokens"])
        elif fam == "consecutive":
            stop_idx, stop_ans = simulate_consecutive(
                tok, ans, cert, cfg["patience"], cfg["min_tokens"], cfg["require_certain"], cfg["validity_mode"]
            )
        elif fam == "window_share":
            stop_idx, stop_ans = simulate_window_share(
                tok, ans, cfg["window_size"], cfg["share_threshold"], cfg["min_valid_probes"],
                cfg["min_tokens"], cfg["validity_mode"], cfg.get("max_switches"),
            )
        elif fam == "entropy":
            stop_idx, stop_ans = simulate_entropy(
                tok, entropy_arr, dominant_cum, cfg["min_tokens"], cfg["entropy_mode"],
                cfg.get("threshold"), cfg.get("k"),
            )
        elif fam == "production_bug":
            stop_idx, stop_ans = simulate_production_bug(ans, cert)
        else:
            raise ValueError(fam)
        out.append((p["pid"], stop_idx, stop_ans))
    return out


def aggregate(cfg, results, problems_by_pid):
    rows_correct_to_wrong = 0
    rows_recovery_truncated = 0
    overthinking_avoided = 0
    n = len(results)
    triggered = 0
    stop_corrects = []
    accuracies = []
    main_tokens_list = []
    probe_calls_list = []

    for pid, stop_idx, stop_ans in results:
        p = problems_by_pid[pid]
        correct_of = p["correct_of"]
        full_tokens = p["tokens_used_full"]
        full_probes = p["num_probes"]
        final_correct = p["final_correct"]
        probe1_correct = p["probe1_correct"]

        if stop_idx is None:
            accuracies.append(final_correct)
            main_tokens_list.append(full_tokens)
            probe_calls_list.append(full_probes)
            continue

        triggered += 1
        stop_correct = bool(correct_of(stop_ans))
        stop_corrects.append(stop_correct)
        accuracies.append(stop_correct)
        stop_tokens = p["tok"][stop_idx]
        main_tokens_list.append(stop_tokens)
        probe_calls_list.append(stop_idx + 1)

        if final_correct and not stop_correct:
            if probe1_correct:
                rows_correct_to_wrong += 1
            else:
                rows_recovery_truncated += 1
        if stop_correct and (full_tokens - stop_tokens) >= 256:
            overthinking_avoided += 1

    n_stopped = len(stop_corrects)
    return {
        "config_id": cfg["config_id"],
        "family": cfg["family"],
        "label": cfg["label"],
        "n_problems": n,
        "overall_accuracy": float(np.mean(accuracies)),
        "avg_main_tokens": float(np.mean(main_tokens_list)),
        "avg_probe_calls": float(np.mean(probe_calls_list)),
        "avg_probe_output_tokens": float(np.mean(probe_calls_list) * PROBE_OUTPUT_TOKENS),
        "avg_total_generated_tokens": float(np.mean(main_tokens_list) + np.mean(probe_calls_list) * PROBE_OUTPUT_TOKENS),
        "stop_coverage": triggered / n,
        "false_stop_rate": (1 - np.mean(stop_corrects)) if n_stopped else float("nan"),
        "correct_stop_rate": float(np.mean(stop_corrects)) if n_stopped else float("nan"),
        "no_stop_rate": 1 - triggered / n,
        "correct_to_wrong_truncation": rows_correct_to_wrong,
        "wrong_to_correct_recovery_truncated": rows_recovery_truncated,
        "overthinking_avoided": overthinking_avoided,
        "wall_clock": None,
        "prefill_cost_estimate": None,
    }


def precompute_problems(df, trajs, raw_targets):
    problems = []
    for pid, g in df.groupby("problem_id"):
        g = g.sort_values("probe_id")
        tok = list(g["token_position"])
        ans = [str(a) for a in g["probe_answer"]]
        cert = list(g["is_certain"])
        entropy_arr = list(g["entropy"])
        dominant_cum = [str(d) for d in g["dominant_answer"]]
        correct_of = make_correct_of(raw_targets, pid)
        last = g.iloc[-1]
        final_answer = str(last["final_answer"])
        final_correct = bool(correct_of(final_answer))
        probe1_correct = bool(correct_of(ans[0]))
        problems.append(
            {
                "pid": pid,
                "tok": tok,
                "ans": ans,
                "cert": cert,
                "entropy": entropy_arr,
                "dominant_cum": dominant_cum,
                "correct_of": correct_of,
                "tokens_used_full": trajs[pid]["tokens_used"],
                "num_probes": len(g),
                "final_correct": final_correct,
                "final_answer": final_answer,
                "probe1_correct": probe1_correct,
            }
        )
    return problems


def select_operating_points(results_df, vanilla_acc):
    frontier_candidates = results_df[results_df["config_id"] != "vanilla"].copy()
    frontier_candidates["acc_drop"] = vanilla_acc - frontier_candidates["overall_accuracy"]

    conservative = frontier_candidates[frontier_candidates["acc_drop"] <= 0.01]
    conservative = conservative.sort_values("avg_total_generated_tokens").head(1)

    balanced = frontier_candidates[frontier_candidates["acc_drop"] <= 0.03]
    balanced = balanced.sort_values("avg_total_generated_tokens").head(1)

    aggressive = frontier_candidates.sort_values("avg_total_generated_tokens").head(1)

    return conservative, balanced, aggressive


def make_figures(results_df, vanilla_acc, out_dir):
    plt.rcParams.update(
        {
            "figure.facecolor": "white", "axes.facecolor": "white",
            "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID,
            "grid.linewidth": 0.8, "axes.axisbelow": True,
            "axes.spines.top": False, "axes.spines.right": False,
            "font.size": 11, "text.color": "#0b0b0b",
            "axes.labelcolor": GRAY, "xtick.color": GRAY, "ytick.color": GRAY,
        }
    )
    non_vanilla = results_df[results_df["config_id"] != "vanilla"]

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.scatter(non_vanilla["avg_total_generated_tokens"], non_vanilla["overall_accuracy"], s=14, color=BLUE, alpha=0.6)
    vrow = results_df[results_df["config_id"] == "vanilla"].iloc[0]
    ax.scatter([vrow["avg_total_generated_tokens"]], [vrow["overall_accuracy"]], s=90, color=ORANGE, marker="*", label="Vanilla (full generation)", zorder=5)
    ax.set_xlabel("Average total generated tokens (main + probe)")
    ax.set_ylabel("Overall accuracy")
    ax.set_title("Figure A · Accuracy vs total tokens")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "figureA_accuracy_vs_tokens.png"), dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.scatter(non_vanilla["stop_coverage"], non_vanilla["false_stop_rate"], s=14, color=BLUE, alpha=0.6)
    ax.set_xlabel("Stop coverage (fraction of problems the rule triggers on)")
    ax.set_ylabel("False-stop rate (stopped-answer wrong)")
    ax.set_title("Figure B · Stop coverage vs false-stop rate")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "figureB_coverage_vs_falsestop.png"), dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 5))
    main_saving = 1 - non_vanilla["avg_main_tokens"] / vrow["avg_main_tokens"]
    acc_drop = vanilla_acc - non_vanilla["overall_accuracy"]
    ax.scatter(main_saving, acc_drop, s=14, color=BLUE, alpha=0.6)
    ax.axhline(0.01, ls="--", lw=1, color=GRAY, label="1pp drop (Conservative bound)")
    ax.axhline(0.03, ls=":", lw=1, color=GRAY, label="3pp drop (Balanced bound)")
    ax.set_xlabel("Main-reasoning token saving (fraction vs vanilla)")
    ax.set_ylabel("Accuracy drop vs vanilla")
    ax.set_title("Figure C · Main-token saving vs accuracy drop")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "figureC_saving_vs_accdrop.png"), dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="math500")
    ap.add_argument("--input", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage1_logging"))
    ap.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage7_pareto"))
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("Loading probes.csv + traj/*.json ...")
    df, trajs = load(args.input)
    raw_targets = {i: item["answer"] for i, item in enumerate(load_dataset(args.dataset))}

    print("Precomputing per-problem arrays ...")
    problems = precompute_problems(df, trajs, raw_targets)
    problems_by_pid = {p["pid"]: p for p in problems}

    configs = build_configs()
    print(f"Grid size: {len(configs)} configs (representative subset per family, not full cross product)")

    rows = []
    for cfg in configs:
        results = run_config(cfg, problems)
        rows.append(aggregate(cfg, results, problems_by_pid))

    results_df = pd.DataFrame(rows)
    results_df.to_csv(os.path.join(args.output, "sweep_results.csv"), index=False)
    print(f"Wrote {len(results_df)} rows to sweep_results.csv")

    # --- Sanity check against analyze.py's existing report.md numbers ---
    sanity_id = "consec_p3_mt0_cert1"
    sanity = results_df[results_df["config_id"] == sanity_id].iloc[0]
    n_triggered = int(round(sanity["stop_coverage"] * sanity["n_problems"]))
    print(
        f"\nSanity check ({sanity_id} should match analyze.py report.md's Dynasor simulation):\n"
        f"  triggered: {n_triggered}/{sanity['n_problems']} (expected 416/500)\n"
        f"  stop accuracy: {sanity['correct_stop_rate']:.1%} (expected 69.2%)\n"
    )

    vanilla_acc = float(results_df[results_df["config_id"] == "vanilla"]["overall_accuracy"].iloc[0])
    conservative, balanced, aggressive = select_operating_points(results_df, vanilla_acc)

    make_figures(results_df, vanilla_acc, args.output)

    L = []
    L.append("# Stage 7 — Stop-rule Pareto Sweep report\n")
    L.append(f"- grid size: **{len(configs)}** configs (representative subset per plan.md §5.2 family, not full cross product; families: vanilla, hard_cap, consecutive, window_share [incl. history-aware + validity-filter variants], entropy, production_bug)")
    L.append(f"- vanilla (full generation) accuracy: **{vanilla_acc:.1%}**")
    L.append("")
    L.append("## Sanity check\n")
    L.append(
        f"`{sanity_id}` (3-consecutive, certain, min_tokens=0, validity=nonempty_only) reproduces the "
        f"existing Dynasor-style simulation from `analyze.py`'s report.md:\n\n"
        f"- triggered: {n_triggered}/{sanity['n_problems']} (existing report: 416/500)\n"
        f"- stop-answer accuracy: {sanity['correct_stop_rate']:.1%} (existing report: 69.2%)\n"
        f"- avg main tokens: {sanity['avg_main_tokens']:.0f}\n"
    )
    L.append("")
    L.append("## Data limitation\n")
    L.append(
        "`logging_run.py` never recorded per-request latency, so `wall_clock` / "
        "`prefill_cost_estimate` (plan.md §5.5) are not available. Only "
        "token-based costs (`avg_main_tokens`, `avg_probe_output_tokens`, "
        "`avg_total_generated_tokens`) are reported below."
    )
    L.append("")
    L.append("## Selected operating points (plan.md §5.7)\n")
    for name, sub in [("Conservative (accuracy drop ≤1pp)", conservative), ("Balanced (accuracy drop ≤3pp)", balanced), ("Aggressive (max token saving)", aggressive)]:
        L.append(f"### {name}\n")
        if len(sub) == 0:
            L.append("No config in the swept grid satisfies this bound.\n")
            continue
        r = sub.iloc[0]
        L.append(
            f"- `{r['config_id']}` — {r['label']}\n"
            f"- accuracy: {r['overall_accuracy']:.1%} (vanilla {vanilla_acc:.1%}, "
            f"drop {vanilla_acc - r['overall_accuracy']:+.1%})\n"
            f"- avg total generated tokens: {r['avg_total_generated_tokens']:.0f} "
            f"(main {r['avg_main_tokens']:.0f} + probe {r['avg_probe_output_tokens']:.0f})\n"
            f"- stop coverage: {r['stop_coverage']:.1%}, false-stop rate: {r['false_stop_rate']:.1%}\n"
            f"- correct→wrong truncation: {int(r['correct_to_wrong_truncation'])}, "
            f"wrong→correct recovery truncated: {int(r['wrong_to_correct_recovery_truncated'])}, "
            f"overthinking avoided: {int(r['overthinking_avoided'])}\n"
        )
    L.append("## Production bug baseline\n")
    prod = results_df[results_df["config_id"] == "production_bug_prefix"].iloc[0]
    L.append(
        f"Reproducing the actual pre-fix `should_early_exit` behavior (log.md 2026-07-23): "
        f"accuracy {prod['overall_accuracy']:.1%}, stop coverage {prod['stop_coverage']:.1%}, "
        f"false-stop rate {prod['false_stop_rate']:.1%} — quantifies how much worse the real "
        f"deployed rule was vs. the documented 3-consecutive-consistent design intent."
    )
    L.append("")
    L.append("Full grid: see `sweep_results.csv`. Figures: figureA/B/C `.png` in this directory.")

    with open(os.path.join(args.output, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Wrote report.md to {args.output}")


if __name__ == "__main__":
    main()
