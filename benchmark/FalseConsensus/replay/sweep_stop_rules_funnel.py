#!/usr/bin/env python3
"""Multi-candidate funnel for the Stage 10 simple@32 stop-rule sweep.

Unlike sweep_stop_rules_v2.py, which selects one configuration per operating
point after train+validation, this script deliberately carries a larger and
family-diverse candidate set through three DeepSeek rounds:

  train:        up to 40 per risk band
  validation:   up to 15 per risk band
  validation-2: up to 10 per risk band (the former 99-problem test split)

The matched Qwen simple@32 stream is then used as an external final gate. Since
multiple finalists are evaluated on Qwen, a later seed is still required for an
unbiased final performance estimate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import sweep_stop_rules_v2 as base


FC_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STAGE10 = FC_DIR / "results/stage10_rule_sweep"

BANDS = {
    "conservative": {"lower": float("-inf"), "upper": 0.01},
    "balanced": {"lower": 0.01, "upper": 0.03},
    "exploratory": {"lower": 0.03, "upper": 0.06},
}

FROZEN_BASELINES = {
    "naive": "consec_p3_fixed0_cert0_validnonempty",
    "stage7_conservative_v0": "consec_p8_fixed1024_cert1_validschema",
    "stage7_balanced_v0": "consec_p6_fixed1024_cert0_validschema",
}


def config_metadata(configs: list[dict]) -> pd.DataFrame:
    rows = []
    for config in configs:
        row = dict(config)
        for key, value in list(row.items()):
            if value is None:
                row[key] = ""
        rows.append(row)
    return pd.DataFrame(rows)


def assign_band(drop: float) -> str | None:
    for name, bounds in BANDS.items():
        if bounds["lower"] < drop <= bounds["upper"]:
            return name
    return None


def diverse_take(
    frame: pd.DataFrame,
    n: int,
    token_column: str,
    accuracy_column: str,
    *,
    dedupe_certainty_twins: bool = False,
) -> pd.DataFrame:
    """Take low-cost candidates while reserving equal quotas per rule family."""
    if dedupe_certainty_twins:
        frame = frame.copy()
        frame["_core_config"] = frame["config_id"].str.replace(
            r"_cert[01]_", "_certX_", regex=True
        )
        # On DeepSeek simple@32, cert0/cert1 are frequently behaviorally
        # identical because nearly every probe is marked certain. Keep the
        # safer cert1 twin for the external Qwen gate, then use the freed slots
        # for structurally different rules.
        frame["_prefer_cert1"] = frame["config_id"].str.contains("_cert1_")
        frame = (
            frame.sort_values(
                [
                    "_core_config",
                    "_prefer_cert1",
                    token_column,
                    accuracy_column,
                ],
                ascending=[True, False, True, False],
            )
            .drop_duplicates("_core_config", keep="first")
            .drop(columns=["_core_config", "_prefer_cert1"])
        )
    if len(frame) <= n:
        return frame.sort_values(
            [token_column, accuracy_column],
            ascending=[True, False],
        ).copy()

    families = sorted(frame["family"].unique())
    quota = max(1, n // len(families))
    pieces = []
    for family in families:
        group = frame[frame["family"] == family].sort_values(
            [token_column, accuracy_column],
            ascending=[True, False],
        )
        pieces.append(group.head(quota))
    selected = pd.concat(pieces).drop_duplicates("config_id")

    remaining = frame[~frame["config_id"].isin(selected["config_id"])].sort_values(
        [token_column, accuracy_column],
        ascending=[True, False],
    )
    selected = pd.concat([selected, remaining.head(max(0, n - len(selected)))])
    return selected.head(n).copy()


def add_rank(frame: pd.DataFrame, round_name: str) -> pd.DataFrame:
    out = []
    for band, group in frame.groupby("risk_band", sort=False):
        group = group.copy()
        group[f"{round_name}_rank"] = np.arange(1, len(group) + 1)
        out.append(group)
    return pd.concat(out, ignore_index=True) if out else frame.copy()


def evaluate_config_set(
    candidates: pd.DataFrame,
    configs: dict[str, dict],
    problems: dict[int, dict],
    problem_ids: set[int],
    dataset: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries = []
    detail = []
    for _, candidate in candidates.iterrows():
        config_id = str(candidate["config_id"])
        rows = base.evaluate_rows(
            configs[config_id],
            problems,
            problem_ids,
            method=dataset,
        )
        rows["risk_band"] = candidate["risk_band"]
        rows["source_config_id"] = config_id
        detail.append(rows)
        summary = base.aggregate(rows)
        summary.update(
            {
                "risk_band": candidate["risk_band"],
                "family": configs[config_id]["family"],
                "floor_kind": configs[config_id]["floor_kind"],
            }
        )
        summaries.append(summary)
    return pd.DataFrame(summaries), pd.concat(detail, ignore_index=True)


def evaluate_baselines(
    configs: dict[str, dict],
    problems: dict[int, dict],
    problem_ids: set[int],
    dataset: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries = []
    details = []
    vanilla = base.evaluate_rows(None, problems, problem_ids, method=dataset)
    vanilla["operating_point"] = "vanilla"
    details.append(vanilla)
    row = base.aggregate(vanilla)
    row["operating_point"] = "vanilla"
    summaries.append(row)
    for name, config_id in FROZEN_BASELINES.items():
        result = base.evaluate_rows(
            configs[config_id], problems, problem_ids, method=dataset
        )
        result["operating_point"] = name
        details.append(result)
        row = base.aggregate(result)
        row["operating_point"] = name
        summaries.append(row)
    return pd.DataFrame(summaries), pd.concat(details, ignore_index=True)


def write_report(
    path: Path,
    train_round: pd.DataFrame,
    validation_round: pd.DataFrame,
    test_round: pd.DataFrame,
    finalists: pd.DataFrame,
    qwen: pd.DataFrame | None,
) -> None:
    def counts(frame: pd.DataFrame) -> str:
        values = frame["risk_band"].value_counts()
        return ", ".join(
            f"{name}={int(values.get(name, 0))}" for name in BANDS
        )

    lines = [
        "# Stage 10 v2 - multi-candidate rule funnel",
        "",
        "## Frozen protocol",
        "",
        "- risk bands are exclusive on DeepSeek train accuracy drop: "
        "conservative <=1pp, balanced (1,3]pp, exploratory (3,6]pp",
        "- train carries up to 40 candidates per band",
        "- validation carries up to 15 per band and must satisfy the same "
        "band upper bound on both train and validation",
        "- the former 99-problem test split is explicitly renamed "
        "validation-2 because it now participates in selection; it carries "
        "up to 10 per band",
        "- validation-2 promotion allows a +2pp point-estimate buffer because "
        "n=99 is discrete/noisy; Qwen simple@32 is the external final gate",
        "- every round reserves equal quota for consecutive and history "
        "families before filling remaining slots by token cost",
        "",
        "## Funnel counts",
        "",
        f"- train: {len(train_round)} ({counts(train_round)})",
        f"- validation: {len(validation_round)} ({counts(validation_round)})",
        f"- validation-2 evaluated: {len(test_round)} "
        f"({counts(test_round)})",
        f"- finalists: {len(finalists)} ({counts(finalists)})",
        "",
        "## Finalists after DeepSeek validation-2",
        "",
    ]
    columns = [
        "risk_band",
        "config_id",
        "family",
        "overall_accuracy",
        "avg_total_generated_tokens",
        "stop_coverage",
        "false_stop_rate",
        "drop_test",
    ]
    lines.extend(
        [
            "| Band | Config | Family | Accuracy | Tokens | Coverage | False-stop | Drop |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in finalists[columns].iterrows():
        lines.append(
            f"| {row['risk_band']} | `{row['config_id']}` | "
            f"{row['family']} | {row['overall_accuracy']:.1%} | "
            f"{row['avg_total_generated_tokens']:.0f} | "
            f"{row['stop_coverage']:.1%} | "
            f"{row['false_stop_rate']:.1%} | "
            f"{row['drop_test'] * 100:+.1f}pp |"
        )

    if qwen is None:
        lines.extend(
            [
                "",
                "## Qwen gate",
                "",
                "Pending matched Qwen simple@32 re-probe.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Matched Qwen simple@32 external gate",
                "",
                "| Band | Config | Family | Accuracy | Tokens | Coverage | False-stop | Drop |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for _, row in qwen.sort_values(
            ["risk_band", "avg_total_generated_tokens"]
        ).iterrows():
            lines.append(
                f"| {row['risk_band']} | `{row['config_id']}` | "
                f"{row['family']} | {row['overall_accuracy']:.1%} | "
                f"{row['avg_total_generated_tokens']:.0f} | "
                f"{row['stop_coverage']:.1%} | "
                f"{row['false_stop_rate']:.1%} | "
                f"{row['drop_qwen'] * 100:+.1f}pp |"
            )
        lines.extend(
            [
                "",
                "Qwen is a final gate over multiple predeclared finalists, not "
                "an untouched estimator after choosing the winner. A new seed "
                "is required for the final unbiased performance estimate.",
            ]
        )
        recommended_id = (
            "hist_w5_mv5_s1.0_level768-2048_swany_span0_"
            "cert1_validschema"
        )
        ds_row = finalists.loc[
            finalists["config_id"] == recommended_id
        ].iloc[0]
        qwen_row = qwen.loc[qwen["config_id"] == recommended_id].iloc[0]
        lines.extend(
            [
                "",
                "## Provisional recommendation",
                "",
                f"`{recommended_id}`",
                "",
                "Selection rule: first require <=1pp point-estimate accuracy "
                "drop on both DeepSeek validation-2 and matched Qwen; among "
                "the passing conservative candidates, balance token cost and "
                "false-stop rather than minimizing tokens alone.",
                "",
                "- Plain-language rule: five valid, certain, schema-valid "
                "probes must agree; level 1-3 may stop after 768 tokens and "
                "level 4-5 after 2,048.",
                f"- DeepSeek validation-2: accuracy "
                f"{ds_row['overall_accuracy']:.1%}, total tokens "
                f"{ds_row['avg_total_generated_tokens']:.0f}, false-stop "
                f"{ds_row['false_stop_rate']:.1%}.",
                f"- Matched Qwen simple@32: accuracy "
                f"{qwen_row['overall_accuracy']:.1%}, total tokens "
                f"{qwen_row['avg_total_generated_tokens']:.0f}, false-stop "
                f"{qwen_row['false_stop_rate']:.1%}.",
                "- Stage-7 Conservative v0 remains the lower-false-stop "
                "fallback; a new seed is required before deployment.",
            ]
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage10-dir", type=Path, default=DEFAULT_STAGE10
    )
    parser.add_argument(
        "--paired-csv",
        type=Path,
        default=FC_DIR / "results/probe_paired_2x2/reprobe_paired.csv",
    )
    parser.add_argument(
        "--stage1-traj",
        type=Path,
        default=FC_DIR / "results/stage1_logging/traj",
    )
    parser.add_argument(
        "--difficulty-csv",
        type=Path,
        default=FC_DIR
        / "results/stage9_difficulty/per_problem_with_difficulty.csv",
    )
    parser.add_argument(
        "--qwen-paired-csv",
        type=Path,
        default=FC_DIR
        / "results/stage11_cross_model/qwen3_8b_math500_simple32/reprobe_paired.csv",
    )
    parser.add_argument(
        "--qwen-traj",
        type=Path,
        default=FC_DIR / "results/stage11_cross_model/qwen3_8b_math500/traj",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=FC_DIR / "results/stage10_rule_funnel_v2",
    )
    parser.add_argument("--split-seed", type=int, default=42)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    configs_list = base.build_configs()
    configs = {config["config_id"]: config for config in configs_list}
    metadata = config_metadata(configs_list)

    train = pd.read_csv(args.stage10_dir / "sweep_train.csv")
    validation = pd.read_csv(args.stage10_dir / "sweep_validation.csv")
    train = train.merge(metadata, on="config_id", validate="one_to_one")
    validation = validation.merge(
        metadata, on="config_id", validate="one_to_one"
    )

    deepseek = base.load_deepseek_problems(
        args.paired_csv, args.stage1_traj, args.difficulty_csv
    )
    split = base.build_split(deepseek, args.split_seed)
    split_ids = {
        name: set(split.loc[split["split"] == name, "problem_id"].astype(int))
        for name in ["train", "validation", "test"]
    }
    vanilla_accuracy = {}
    for name in ["train", "validation", "test"]:
        vanilla_accuracy[name] = base.aggregate(
            base.evaluate_rows(
                None, deepseek, split_ids[name], method=f"deepseek_{name}"
            )
        )["overall_accuracy"]

    train["drop_train"] = (
        vanilla_accuracy["train"] - train["overall_accuracy"]
    )
    train["risk_band"] = train["drop_train"].map(assign_band)
    train_pool = train[train["risk_band"].notna()].copy()
    round1_parts = []
    for band in BANDS:
        group = train_pool[train_pool["risk_band"] == band]
        round1_parts.append(
            diverse_take(
                group,
                40,
                "avg_total_generated_tokens",
                "overall_accuracy",
            )
        )
    round1 = add_rank(pd.concat(round1_parts, ignore_index=True), "train")
    round1.to_csv(args.out_dir / "round1_train_candidates.csv", index=False)

    validation_metrics = validation.rename(
        columns={
            column: f"{column}_validation"
            for column in validation.columns
            if column != "config_id"
        }
    )
    round2_pool = round1.merge(
        validation_metrics, on="config_id", validate="one_to_one"
    )
    round2_pool["drop_validation"] = (
        vanilla_accuracy["validation"]
        - round2_pool["overall_accuracy_validation"]
    )
    n_train = len(split_ids["train"])
    n_validation = len(split_ids["validation"])
    round2_pool["dev_tokens"] = (
        round2_pool["avg_total_generated_tokens"] * n_train
        + round2_pool["avg_total_generated_tokens_validation"] * n_validation
    ) / (n_train + n_validation)
    round2_pool["dev_accuracy"] = (
        round2_pool["overall_accuracy"] * n_train
        + round2_pool["overall_accuracy_validation"] * n_validation
    ) / (n_train + n_validation)

    round2_parts = []
    for band, bounds in BANDS.items():
        group = round2_pool[
            (round2_pool["risk_band"] == band)
            & (round2_pool["drop_validation"] <= bounds["upper"])
        ]
        round2_parts.append(
            diverse_take(group, 15, "dev_tokens", "dev_accuracy")
        )
    round2 = add_rank(pd.concat(round2_parts, ignore_index=True), "validation")
    round2.to_csv(
        args.out_dir / "round2_validation_candidates.csv", index=False
    )

    test_summary, test_detail = evaluate_config_set(
        round2,
        configs,
        deepseek,
        split_ids["test"],
        "deepseek_validation2",
    )
    test_summary["drop_test"] = (
        vanilla_accuracy["test"] - test_summary["overall_accuracy"]
    )
    test_summary.to_csv(
        args.out_dir / "round3_validation2_results.csv", index=False
    )
    test_detail.to_csv(
        args.out_dir / "round3_validation2_per_problem.csv", index=False
    )

    finalists_parts = []
    for band, bounds in BANDS.items():
        group = test_summary[
            (test_summary["risk_band"] == band)
            & (test_summary["drop_test"] <= bounds["upper"] + 0.02)
        ]
        finalists_parts.append(
            diverse_take(
                group,
                10,
                "avg_total_generated_tokens",
                "overall_accuracy",
                dedupe_certainty_twins=True,
            )
        )
    finalists = add_rank(
        pd.concat(finalists_parts, ignore_index=True), "validation2"
    )
    finalists.to_csv(args.out_dir / "round3_finalists.csv", index=False)

    baseline_summary, baseline_detail = evaluate_baselines(
        configs,
        deepseek,
        split_ids["test"],
        "deepseek_validation2",
    )
    baseline_summary.to_csv(
        args.out_dir / "deepseek_validation2_baselines.csv", index=False
    )
    baseline_detail.to_csv(
        args.out_dir / "deepseek_validation2_baselines_per_problem.csv",
        index=False,
    )

    qwen_summary = None
    if args.qwen_paired_csv.exists():
        qwen = base.load_deepseek_problems(
            args.qwen_paired_csv, args.qwen_traj, args.difficulty_csv
        )
        qwen_ids = set(qwen)
        qwen_vanilla_accuracy = base.aggregate(
            base.evaluate_rows(
                None, qwen, qwen_ids, method="qwen_simple32"
            )
        )["overall_accuracy"]
        qwen_summary, qwen_detail = evaluate_config_set(
            finalists,
            configs,
            qwen,
            qwen_ids,
            "qwen_simple32",
        )
        qwen_summary["drop_qwen"] = (
            qwen_vanilla_accuracy - qwen_summary["overall_accuracy"]
        )
        qwen_summary.to_csv(
            args.out_dir / "round4_qwen_simple32_results.csv", index=False
        )
        qwen_detail.to_csv(
            args.out_dir / "round4_qwen_simple32_per_problem.csv",
            index=False,
        )
        qwen_baseline_summary, qwen_baseline_detail = evaluate_baselines(
            configs, qwen, qwen_ids, "qwen_simple32"
        )
        qwen_baseline_summary.to_csv(
            args.out_dir / "qwen_simple32_baselines.csv", index=False
        )
        qwen_baseline_detail.to_csv(
            args.out_dir / "qwen_simple32_baselines_per_problem.csv",
            index=False,
        )

    protocol = {
        "risk_bands": BANDS,
        "round1_train_per_band": 40,
        "round2_validation_per_band": 15,
        "round3_validation2_per_band": 10,
        "validation2_buffer_pp": 2,
        "family_quota": "equal consecutive/history quota before global fill",
        "split_seed": args.split_seed,
        "qwen_matched_simple32": bool(args.qwen_paired_csv.exists()),
    }
    (args.out_dir / "protocol.json").write_text(
        json.dumps(protocol, indent=2) + "\n"
    )
    write_report(
        args.out_dir / "report.md",
        round1,
        round2,
        test_summary,
        finalists,
        qwen_summary,
    )
    print(
        json.dumps(
            {
                "train_candidates": len(round1),
                "validation_candidates": len(round2),
                "validation2_evaluated": len(test_summary),
                "finalists": len(finalists),
                "qwen_complete": qwen_summary is not None,
                "output": str(args.out_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
