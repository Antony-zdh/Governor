"""Stage 6 -- Probe Validity Audit analysis (plan.md SS4.6/4.7).

Consumes the user's real annotations (single annotator, 100/296 cases
labeled -- Round 1 target was 100 but plan.md SS4.5 assumed two independent
annotators for a kappa check; we only have one, so kappa is reported as
N/A rather than fabricated) joined back to probe_audit_cases.jsonl for the
token_position / final_correct / probe_answer / context_probes fields
needed for the position/consensus/correctness breakdowns.

Usage: python3 analyze_audit.py [--annotations annotations.csv]
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from analyze import eq  # noqa: E402

LABELS = [
    "supported_correct",
    "supported_wrong",
    "tentative_guess",
    "incomplete_answer",
    "format_artifact",
    "inconsistent_with_prefix",
    "ambiguous",
]

POSITION_BINS = [0, 512, 1024, 2048, 10**9]
POSITION_LABELS = ["<512", "512-1024", "1024-2048", ">2048"]

SHARE_BINS = [-0.01, 0.0, 0.5, 0.99, 1.01]
SHARE_LABELS = ["0 (无邻居一致)", "0-0.5", "0.5-1 (不含1)", "1.0 (完全一致)"]


def load_cases(path):
    cases = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            cases[d["case_id"]] = d
    return cases


def answer_type(ans):
    ans = str(ans) if ans is not None and pd.notna(ans) else ""
    if ans == "":
        return "empty"
    if len(ans) == 1 and ans.upper() in "ABCD":
        return "single_letter"
    return "other"


def local_share(case):
    """Share of context_probes (excluding the current probe) whose answer
    matches the current probe's answer -- a local consensus-strength proxy,
    since no single 'consensus strength' field is logged per-case."""
    ctx = case["context_probes"]
    cur = next((c for c in ctx if c.get("is_current")), None)
    others = [c for c in ctx if not c.get("is_current")]
    if cur is None or not others:
        return np.nan
    cur_ans = cur.get("answer", "")
    matches = sum(1 for c in others if eq(c.get("answer", ""), cur_ans))
    return matches / len(others)


def bootstrap_ci(values, n_boot=2000, seed=42):
    """95% CI on a proportion via simple bootstrap -- appropriate given the
    small (n<=100, often much smaller per-subgroup) sample sizes here rather
    than pretending a normal-approximation CI is meaningful."""
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return (np.nan, np.nan)
    rng = np.random.RandomState(seed)
    means = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(n_boot)]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def rate_table(df, by_col, valid_col="valid_as_current_answer"):
    rows = []
    for key, g in df.groupby(by_col, observed=True):
        vals = g[valid_col].astype(float).values
        lo, hi = bootstrap_ci(vals)
        rows.append(
            {
                by_col: key,
                "n": len(g),
                "validity_rate": vals.mean() if len(vals) else np.nan,
                "ci95_lo": lo,
                "ci95_hi": hi,
            }
        )
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--annotations", default=os.path.join(here, "annotations.csv"))
    ap.add_argument("--cases", default=os.path.join(here, "probe_audit_cases.jsonl"))
    ap.add_argument("--output", default=here)
    args = ap.parse_args()

    ann = pd.read_csv(args.annotations)
    ann = ann[ann["label"].notna() & (ann["label"] != "")].copy()
    cases = load_cases(args.cases)

    ann["case"] = ann["case_id"].map(cases)
    missing = ann["case"].isna().sum()
    if missing:
        print(f"WARNING: {missing} annotated case_ids not found in {args.cases}")
        ann = ann[ann["case"].notna()]

    ann["token_position"] = ann["case"].apply(lambda c: c["token_position"])
    ann["final_correct"] = ann["case"].apply(lambda c: bool(c["final_correct"]))
    ann["probe_answer_normalized"] = ann["case"].apply(lambda c: c["probe_answer_normalized"])
    ann["final_answer"] = ann["case"].apply(lambda c: c["final_answer"])
    ann["answer_type"] = ann["probe_answer_normalized"].apply(answer_type)
    ann["local_share"] = ann["case"].apply(local_share)
    ann["probe_matches_final"] = ann.apply(
        lambda r: eq(r["probe_answer_normalized"], r["final_answer"]), axis=1
    )
    ann["position_bin"] = pd.cut(ann["token_position"], POSITION_BINS, labels=POSITION_LABELS, right=False)
    ann["share_bin"] = pd.cut(ann["local_share"], SHARE_BINS, labels=SHARE_LABELS)

    for col in ["valid_as_current_answer", "ready_to_stop", "answer_complete",
                "prefix_contains_support", "requires_more_reasoning"]:
        ann[col] = ann[col].astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y"])

    n = len(ann)
    label_counts = ann["label"].value_counts().reindex(LABELS, fill_value=0)

    overall_rate = ann["valid_as_current_answer"].mean()
    overall_ci = bootstrap_ci(ann["valid_as_current_answer"].astype(float).values)

    by_position = rate_table(ann, "position_bin")
    by_answer_type = rate_table(ann, "answer_type")
    by_share = rate_table(ann, "share_bin")
    by_correctness = rate_table(ann, "final_correct")

    forced_guess_rate = (ann["label"] == "tentative_guess").mean()
    artifact_rate = (ann["label"] == "format_artifact").mean()

    wrong = ann[ann["label"] == "supported_wrong"]
    p_correct_given_wrong = wrong["final_correct"].mean() if len(wrong) else np.nan
    tentative = ann[ann["label"] == "tentative_guess"]
    p_correct_given_tentative = tentative["final_correct"].mean() if len(tentative) else np.nan

    # SS4.7 decision criteria, restricted to cases where the probe *disagreed*
    # with the final answer (the "early wrong probe" population the plan's
    # A/B/C framing is about) -- labeling the whole annotated set would dilute
    # the signal with cases where the probe was already correct.
    early_wrong = ann[~ann["probe_matches_final"]]
    n_early_wrong = len(early_wrong)
    if n_early_wrong:
        share_tentative = (early_wrong["label"] == "tentative_guess").mean()
        share_supported_wrong = (early_wrong["label"] == "supported_wrong").mean()
        share_supported_wrong_then_correct = (
            (early_wrong["label"] == "supported_wrong") & early_wrong["final_correct"]
        ).mean()
        share_artifact = (early_wrong["label"] == "format_artifact").mean()
    else:
        share_tentative = share_supported_wrong = share_supported_wrong_then_correct = share_artifact = np.nan

    ann_out = ann.drop(columns=["case"])
    ann_out.to_csv(os.path.join(args.output, "annotations_enriched.csv"), index=False)

    lines = []
    lines.append("# Stage 6 -- Probe Validity Audit report (Round 1, n={})\n".format(n))
    lines.append(
        "**标注方法说明**：plan.md SS4.5 的 Round 1 设计假设两名独立标注者以计算 "
        "Cohen's kappa；实际只有用户一人标注（见 log.md 说明），因此本报告不含 "
        "kappa/raw agreement 指标（不编造第二人的数据），仅报告单一标注者结果。"
        "已标注 {}/296 个案例，覆盖全部 6 个抽样组（每组 10-23 例，非均匀，"
        "因为标注是按案例文件顺序做到 100 个就停止，而不是按组配额精确切分）。\n".format(n)
    )

    lines.append("## 主标签分布\n")
    lines.append(label_counts.to_string())
    lines.append("")

    lines.append("\n## 1. Probe validity rate（整体）\n")
    lines.append(f"- `valid_as_current_answer` = True 的比例：**{overall_rate:.1%}** "
                 f"(95% CI [{overall_ci[0]:.1%}, {overall_ci[1]:.1%}], n={n})")

    lines.append("\n## 2. Validity by token position\n")
    lines.append(by_position.to_string(index=False))

    lines.append("\n\n## 3. Validity by answer type\n")
    lines.append(by_answer_type.to_string(index=False))

    lines.append("\n\n## 4. Validity by local consensus strength\n")
    lines.append(
        "(local_share = 当前 probe 前后 context_probes 中与当前答案一致的比例，"
        "作为逐案例 consensus strength 的代理指标，因为原始 case 记录没有直接存 "
        "cumulative/window share 字段)\n"
    )
    lines.append(by_share.to_string(index=False))

    lines.append("\n\n## 5. Validity by final correctness\n")
    lines.append(by_correctness.to_string(index=False))

    lines.append("\n\n## 6. Forced-guess rate（tentative_guess 占比）\n")
    lines.append(f"- {forced_guess_rate:.1%} (n={n})")

    lines.append("\n## 7. Artifact rate（format_artifact 占比）\n")
    lines.append(f"- {artifact_rate:.1%} (n={n})")

    lines.append("\n## 8. P(final correct | supported_wrong)\n")
    lines.append(f"- {p_correct_given_wrong:.1%} (n={len(wrong)})" if len(wrong) else "- n=0，无法计算")

    lines.append("\n## 9. P(final correct | tentative_guess)\n")
    lines.append(f"- {p_correct_given_tentative:.1%} (n={len(tentative)})" if len(tentative) else "- n=0，无法计算")

    lines.append("\n## SS4.7 关键判断标准（限定在 probe 与 final 不一致的案例，n={}）\n".format(n_early_wrong))
    if n_early_wrong:
        lines.append(f"- 情况 A 相关（tentative_guess 占比）：{share_tentative:.1%}")
        lines.append(f"- 情况 B 相关（supported_wrong 占比）：{share_supported_wrong:.1%}，"
                     f"其中最终 recover 到正确答案的：{share_supported_wrong_then_correct:.1%}")
        lines.append(f"- 情况 C 相关（format_artifact 占比）：{share_artifact:.1%}")
        dominant = max(
            [("A", share_tentative), ("B", share_supported_wrong), ("C", share_artifact)],
            key=lambda kv: kv[1],
        )
        lines.append(f"\n**初步结论**：三者中 情况{dominant[0]} 占比最高（{dominant[1]:.1%}），"
                     "但 n 较小（尤其在再细分到某个 answer_type/position 时），"
                     "结论应视为方向性而非最终定论，建议 Stage 6 Round 3 扩大样本后复核。")
    else:
        lines.append("- 无 probe!=final 的已标注案例，无法评估")

    report = "\n".join(lines)
    with open(os.path.join(args.output, "audit_report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\nWrote {os.path.join(args.output, 'audit_report.md')} and annotations_enriched.csv")


if __name__ == "__main__":
    main()
