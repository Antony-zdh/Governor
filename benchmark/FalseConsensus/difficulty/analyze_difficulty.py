"""Stage 9 (partial) — difficulty-controlled mechanism analysis (plan.md §7).

Tests whether "later consensus -> lower accuracy" (Stage 2-5 finding) is a
real mechanism or confounded by problem difficulty, using only data already
available offline (MATH level, subject, entropy, answer switches, token
cap) — no new model generation needed.

Deferred (need Stage 6 human annotation and/or more design time, not
attempted here to avoid a rushed low-quality version):
  - Analysis 3 (difficulty-matched comparison)
  - Analysis 4 (recovery probability model)
  - `probe_validity` as a regression feature (plan.md §7.2) — Stage 6
    annotations don't exist yet; re-run this script's Analysis 2 once
    `audit/annotations.csv` lands.

Implements:
  - Analysis 1: stratified consensus-time-vs-accuracy within MATH level
  - Analysis 2: logistic regression for P(final correct), 5-fold CV accuracy
  - §7.4 Terminality / Correctness / Safe-stop probability by agreement bin
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from analyze import BINS, BIN_LABELS, eq, load, per_problem  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "TokenDeprivation"))
from utils import load_dataset  # noqa: E402


def per_problem_extras(df):
    rows = []
    for pid, g in df.groupby("problem_id"):
        g = g.sort_values("probe_id")
        ans = [str(a) for a in g["dominant_answer"]]
        entropy = g["entropy"].astype(float)
        switches = 0
        last = None
        for a in ans:
            if a == "":
                continue
            if last is not None and not eq(a, last):
                switches += 1
            last = a
        rows.append({"problem_id": pid, "avg_entropy": float(entropy.mean()), "num_switches": switches})
    return pd.DataFrame(rows).set_index("problem_id")


def analysis1_stratified(pp):
    x = pp.copy()
    x["ct_bin"] = pd.cut(
        x["consensus_time"], bins=[0, 512, 1024, 1536, 2048, 3200],
        labels=["<512", "512-1024", "1024-1536", "1536-2048", ">2048"],
    )
    out = x.groupby(["level", "ct_bin"], observed=True)["final_correct"].agg(["mean", "count"]).reset_index()
    out.columns = ["level", "consensus_time_bin", "accuracy", "n"]
    return out[out["n"] >= 3]


def analysis2_logistic(pp):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler

    x = pp.copy()
    x["consensus_time"] = x["consensus_time"].astype(float)
    num_cols = ["consensus_time", "level", "num_switches", "avg_entropy"]
    cat_cols = ["subject", "hit_token_cap"]
    X = x[num_cols + cat_cols]
    y = x["final_correct"].astype(int)

    pre = ColumnTransformer(
        [
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), num_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
        ]
    )
    pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000))])
    cv_acc = cross_val_score(pipe, X, y, cv=5, scoring="accuracy")
    pipe.fit(X, y)

    feature_names = num_cols + list(pipe.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(cat_cols))
    coefs = pipe.named_steps["clf"].coef_[0]
    coef_table = pd.DataFrame({"feature": feature_names, "coef": coefs, "odds_ratio": np.exp(coefs)})
    return coef_table.sort_values("coef", ascending=False), cv_acc


def stage9_4_probabilities(df, pp):
    """Terminality / Correctness / Safe-stop probability by cumulative
    agreement (share) bin, computed empirically per probe row."""
    final_by_pid = pp["final_answer"].to_dict()
    correct_of_by_pid = pp["final_correct"].to_dict()

    x = df.copy()
    x["bin"] = pd.cut(x["share"], bins=BINS, labels=BIN_LABELS, right=False)

    terminal_flags, correct_flags = [], []
    for _, row in x.iterrows():
        pid = row["problem_id"]
        dom = str(row["dominant_answer"])
        final_ans = str(final_by_pid.get(pid, ""))
        terminal_flags.append(eq(dom, final_ans))
        correct_flags.append(bool(row["final_correct"]) if eq(dom, final_ans) else eq(dom, str(pp.loc[pid, "target"])))
    x["terminal"] = terminal_flags
    x["dominant_correct"] = correct_flags
    x["safe_stop"] = x["terminal"] & x["dominant_correct"]

    out = []
    for label in BIN_LABELS:
        sub = x[x["bin"] == label]
        if len(sub) == 0:
            continue
        out.append(
            {
                "share_bin": label,
                "n_probes": len(sub),
                "terminality_T": float(sub["terminal"].mean()),
                "correctness_C": float(sub["dominant_correct"].mean()),
                "safe_stop_S": float(sub["safe_stop"].mean()),
            }
        )
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="math500")
    ap.add_argument("--input", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage1_logging"))
    ap.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "..", "results", "stage9_difficulty"))
    args = ap.parse_args()
    os.makedirs(args.output, exist_ok=True)

    print("Loading data ...")
    df, trajs = load(args.input)
    dataset = load_dataset(args.dataset)
    raw_targets = {i: item["answer"] for i, item in enumerate(dataset)}

    analyze_args = argparse.Namespace(
        input=args.input, dataset=args.dataset, window=5, certain_bar=3,
        consensus_share=0.8, min_probes_for_consensus=3,
    )
    pp = per_problem(df, trajs, analyze_args, raw_targets)

    pp["level"] = [dataset[pid].get("level") for pid in pp.index]
    pp["subject"] = [dataset[pid].get("subject", "unknown") for pid in pp.index]
    pp["hit_token_cap"] = ~pp["finished_naturally"].astype(bool)

    extras = per_problem_extras(df)
    pp = pp.join(extras)

    print("Analysis 1: stratified consensus-time vs accuracy by MATH level ...")
    strat = analysis1_stratified(pp)
    strat.to_csv(os.path.join(args.output, "analysis1_stratified.csv"), index=False)

    print("Analysis 2: logistic regression for P(final correct) ...")
    coef_table, cv_acc = analysis2_logistic(pp)
    coef_table.to_csv(os.path.join(args.output, "analysis2_logistic_coefs.csv"), index=False)

    print("Stage 9.4: Terminality / Correctness / Safe-stop probability by agreement bin ...")
    probs = stage9_4_probabilities(df, pp)
    probs.to_csv(os.path.join(args.output, "stage9_4_probabilities.csv"), index=False)

    pp.to_csv(os.path.join(args.output, "per_problem_with_difficulty.csv"))

    L = []
    L.append("# Stage 9 (partial) — Difficulty-controlled mechanism analysis\n")
    L.append(
        "Deferred: Analysis 3 (matched comparison), Analysis 4 (recovery "
        "probability model), and `probe_validity` as a regression feature "
        "(needs Stage 6 human annotations, which don't exist yet — "
        "Analysis 2 should be re-run once `audit/annotations.csv` lands).\n"
    )
    L.append("## Analysis 1 · Stratified consensus-time vs accuracy by MATH level\n")
    L.append(strat.to_markdown(index=False, floatfmt=".3f"))
    L.append("")
    L.append("## Analysis 2 · Logistic regression, P(final correct)\n")
    L.append(f"5-fold CV accuracy: {cv_acc.mean():.1%} +/- {cv_acc.std():.1%} (vanilla base rate: {pp['final_correct'].mean():.1%})\n")
    L.append(coef_table.to_markdown(index=False, floatfmt=".3f"))
    L.append("")
    L.append("## Stage 9.4 · Terminality / Correctness / Safe-stop probability (plan.md §7.4)\n")
    L.append(probs.to_markdown(index=False, floatfmt=".3f"))
    L.append("")
    L.append(
        "Interpretation check: if T (terminality) and C (correctness) diverge "
        "meaningfully across bins (e.g. high C but low T at moderate share), "
        "that supports plan.md's core claim that agreement alone isn't enough "
        "— safe-stop needs both correctness and terminality, not just share."
    )
    with open(os.path.join(args.output, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Wrote report.md to {args.output}")


if __name__ == "__main__":
    main()
