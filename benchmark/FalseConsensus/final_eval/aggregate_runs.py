#!/usr/bin/env python3
"""Aggregate completed frozen evaluations across models and seeds."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
PRIMARY = {
    "full_generation",
    "naive_agreement",
    "dynasor_stop_logic_on_simple32",
    "certaindex_adapted_simple32",
    "certaindex_faithful_mid",
    "conservative",
    "balanced_math",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260725)
    return parser.parse_args()


def load_runs(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries = []
    details = []
    run_ids = set()
    for manifest_path in sorted(root.rglob("evaluation_manifest.json")):
        result_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("evaluation_scope") == "partial_smoke_test":
            continue
        model = manifest.get("model")
        seed = manifest.get("base_seed")
        dataset = manifest.get("dataset")
        probe_style = manifest.get("probe_suffix_style", "simple")
        probe_interval = manifest.get("probe_interval")
        probe_tokens = manifest.get("probe_tokens")
        if model is None or seed is None:
            raise ValueError(
                f"{manifest_path} lacks model/base_seed; rerun evaluate_run.py"
            )
        run_id = (
            f"{model}__{dataset}__{probe_style}{probe_interval}x"
            f"{probe_tokens}__seed_{seed}"
        )
        if run_id in run_ids:
            raise ValueError(f"Duplicate registered run: {run_id}")
        run_ids.add(run_id)
        summary = pd.read_csv(result_dir / "methods_summary.csv")
        detail = pd.read_csv(result_dir / "methods_per_problem.csv")
        for frame in [summary, detail]:
            frame["model"] = model
            frame["dataset"] = dataset
            frame["probe_suffix_style"] = probe_style
            frame["probe_interval"] = probe_interval
            frame["probe_tokens_setting"] = probe_tokens
            frame["seed"] = int(seed)
            frame["run_id"] = run_id
        summaries.append(summary)
        details.append(detail)
    if not summaries:
        raise ValueError(f"No evaluation_manifest.json files under {root}")
    return (
        pd.concat(summaries, ignore_index=True),
        pd.concat(details, ignore_index=True),
    )


def hierarchical_interval(
    frame: pd.DataFrame,
    method: str,
    bootstrap: int,
    rng: np.random.Generator,
) -> dict:
    diffs = []
    savings = []
    seeds = sorted(frame["seed"].unique())
    by_seed = {}
    for seed in seeds:
        seed_frame = frame[frame["seed"] == seed]
        full = (
            seed_frame[seed_frame["method"] == "full_generation"]
            .sort_values("problem_id")
            .reset_index(drop=True)
        )
        candidate = (
            seed_frame[seed_frame["method"] == method]
            .sort_values("problem_id")
            .reset_index(drop=True)
        )
        if not np.array_equal(
            full["problem_id"].to_numpy(),
            candidate["problem_id"].to_numpy(),
        ):
            raise ValueError(f"Unpaired rows for seed={seed}, method={method}")
        by_seed[seed] = (
            full["delivered_correct"].astype(float).to_numpy(),
            full["total_tokens"].astype(float).to_numpy(),
            candidate["delivered_correct"].astype(float).to_numpy(),
            candidate["total_tokens"].astype(float).to_numpy(),
        )

    for _ in range(bootstrap):
        sampled_seeds = rng.choice(seeds, size=len(seeds), replace=True)
        base_acc, base_tokens, method_acc, method_tokens = [], [], [], []
        for seed in sampled_seeds:
            arrays = by_seed[int(seed)]
            indices = rng.integers(0, len(arrays[0]), size=len(arrays[0]))
            base_acc.append(arrays[0][indices])
            base_tokens.append(arrays[1][indices])
            method_acc.append(arrays[2][indices])
            method_tokens.append(arrays[3][indices])
        base_acc_array = np.concatenate(base_acc)
        base_token_array = np.concatenate(base_tokens)
        method_acc_array = np.concatenate(method_acc)
        method_token_array = np.concatenate(method_tokens)
        diffs.append(method_acc_array.mean() - base_acc_array.mean())
        savings.append(
            1 - method_token_array.mean() / base_token_array.mean()
        )
    return {
        "accuracy_diff_ci_lo": float(np.quantile(diffs, 0.025)),
        "accuracy_diff_ci_hi": float(np.quantile(diffs, 0.975)),
        "token_saving_ci_lo": float(np.quantile(savings, 0.025)),
        "token_saving_ci_hi": float(np.quantile(savings, 0.975)),
    }


def model_summary(
    summaries: pd.DataFrame,
    details: pd.DataFrame,
    bootstrap: int,
    seed: int,
) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(seed)
    for (
        dataset,
        model,
        probe_style,
        probe_interval,
        probe_tokens,
    ), model_summary_frame in summaries.groupby(
        [
            "dataset",
            "model",
            "probe_suffix_style",
            "probe_interval",
            "probe_tokens_setting",
        ],
        dropna=False,
    ):
        model_details = details[
            (details["model"] == model)
            & (details["dataset"] == dataset)
            & (details["probe_suffix_style"] == probe_style)
            & (
                pd.to_numeric(
                    details["probe_interval"], errors="coerce"
                ).fillna(-1)
                == (-1 if pd.isna(probe_interval) else probe_interval)
            )
            & (
                pd.to_numeric(
                    details["probe_tokens_setting"], errors="coerce"
                ).fillna(-1)
                == (-1 if pd.isna(probe_tokens) else probe_tokens)
            )
        ]
        for method, group in model_summary_frame.groupby("method"):
            accuracy_diff = group["accuracy_diff_vs_full"]
            token_saving = group["total_token_saving_vs_full"]
            row = {
                "model": model,
                "dataset": dataset,
                "probe_suffix_style": probe_style,
                "probe_interval": probe_interval,
                "probe_tokens_setting": probe_tokens,
                "method": method,
                "n_seeds": int(group["seed"].nunique()),
                "seeds": ",".join(
                    str(value) for value in sorted(group["seed"].unique())
                ),
                "accuracy_mean": float(group["accuracy"].mean()),
                "accuracy_sd_across_seeds": float(
                    group["accuracy"].std(ddof=1)
                ),
                "accuracy_diff_vs_full_mean": float(accuracy_diff.mean()),
                "accuracy_diff_vs_full_sd": float(
                    accuracy_diff.std(ddof=1)
                ),
                "total_token_saving_mean": float(token_saving.mean()),
                "total_token_saving_sd": float(token_saving.std(ddof=1)),
                "false_stop_rate_mean": float(
                    group["false_stop_rate"].mean()
                ),
                "stop_coverage_mean": float(group["stop_coverage"].mean()),
                "recovery_killed_total": int(group["recovery_killed"].sum()),
                "overthinking_prevented_total": int(
                    group["overthinking_prevented"].sum()
                ),
                "seeds_with_positive_token_saving": int(
                    (token_saving > 0).sum()
                ),
            }
            if method in PRIMARY or method.startswith("fixed_budget_"):
                row.update(
                    hierarchical_interval(
                        model_details,
                        method,
                        bootstrap,
                        rng,
                    )
                )
            else:
                row.update(
                    {
                        "accuracy_diff_ci_lo": math.nan,
                        "accuracy_diff_ci_hi": math.nan,
                        "token_saving_ci_lo": math.nan,
                        "token_saving_ci_hi": math.nan,
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def mechanism_summary(root: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(root.rglob("transition_summary.json")):
        result = json.loads(path.read_text())
        manifest = json.loads(
            (path.parent / "evaluation_manifest.json").read_text()
        )
        if manifest.get("probe_suffix_style", "simple") != "simple":
            continue
        rows.append(
            {
                "model": manifest["model"],
                "dataset": manifest.get("dataset"),
                "seed": manifest["base_seed"],
                "reached": result["reached"],
                "not_reached": result["not_reached"],
                **result["counts"],
                "recovery_overthinking_ratio_haldane": result[
                    "recovery_overthinking_ratio_haldane"
                ],
                "ratio_ci_lo": result[
                    "recovery_overthinking_ratio_ci_haldane"
                ][0],
                "ratio_ci_hi": result[
                    "recovery_overthinking_ratio_ci_haldane"
                ][1],
            }
        )
    return pd.DataFrame(rows)


def submission_gate(
    model_results: pd.DataFrame, protocol: dict
) -> dict:
    primary = model_results[
        (model_results["dataset"] == protocol["dataset"])
        & (model_results["probe_suffix_style"] == "simple")
        & model_results["method"].isin(PRIMARY)
    ]
    required_models = set(protocol["models"])
    observed_models = set(primary["model"])
    complete_models = required_models <= observed_models
    required_simple_methods = {
        "full_generation",
        "naive_agreement",
        "dynasor_stop_logic_on_simple32",
        "conservative",
        "balanced_math",
    }
    observed_simple_pairs = set(
        primary[["model", "method"]].itertuples(index=False, name=None)
    )
    required_simple_pairs = {
        (model, method)
        for model in required_models
        for method in required_simple_methods
    }
    simple_methods_complete = required_simple_pairs <= observed_simple_pairs
    seed_complete = bool(
        simple_methods_complete
        and (
            primary[
                primary.apply(
                    lambda row: (row["model"], row["method"])
                    in required_simple_pairs,
                    axis=1,
                )
            ]["n_seeds"]
            >= len(protocol["generation"]["seeds"])
        ).all()
    )
    conservative = primary[primary["method"] == "conservative"]
    balanced = primary[primary["method"] == "balanced_math"]
    conservative_drop_ok = bool(
        len(conservative)
        and -conservative["accuracy_diff_vs_full_mean"].mean()
        <= protocol["success_thresholds"]["conservative"][
            "mean_accuracy_drop_pp_max"
        ]
        / 100
    )
    conservative_saving_ok = bool(
        len(conservative)
        and conservative["total_token_saving_mean"].mean()
        >= protocol["success_thresholds"]["conservative"][
            "total_generated_token_saving_fraction_target"
        ][0]
    )
    conservative_pareto_left_seed_ok = bool(
        len(conservative)
        and (
            conservative["seeds_with_positive_token_saving"]
            >= protocol["success_thresholds"]["conservative"][
                "pareto_left_seeds_minimum"
            ]
        ).all()
    )
    balanced_drop_ok = bool(
        len(balanced)
        and -balanced["accuracy_diff_vs_full_mean"].mean()
        <= protocol["success_thresholds"]["balanced_math"][
            "mean_accuracy_drop_pp_max"
        ]
        / 100
    )
    balanced_saving_ok = bool(
        len(balanced)
        and balanced["total_token_saving_mean"].mean()
        >= protocol["success_thresholds"]["balanced_math"][
            "total_generated_token_saving_fraction_target"
        ][0]
    )
    balanced_model_floor_ok = bool(
        len(balanced)
        and (
            balanced["accuracy_diff_vs_full_mean"]
            >= -protocol["success_thresholds"]["balanced_math"][
                "stable_model_accuracy_drop_pp_max"
            ]
            / 100
        ).all()
    )
    formal_methods = set(protocol["formal_baselines"])
    formal = model_results[
        (model_results["dataset"] == protocol["dataset"])
        & model_results["method"].isin(formal_methods)
    ]
    formal_pairs = set(
        formal[["model", "method"]].itertuples(index=False, name=None)
    )
    required_formal_pairs = {
        (model, method)
        for model in required_models
        for method in formal_methods
    }
    formal_baselines_present = required_formal_pairs <= formal_pairs
    formal_baselines_three_seed = bool(
        formal_baselines_present
        and (
            formal[
                formal.apply(
                    lambda row: (row["model"], row["method"])
                    in required_formal_pairs,
                    axis=1,
                )
            ]["n_seeds"]
            >= len(protocol["generation"]["seeds"])
        ).all()
    )
    return {
        "complete_models": complete_models,
        "complete_simple_method_set": simple_methods_complete,
        "three_seeds_per_model_method": seed_complete,
        "conservative_accuracy_gate": conservative_drop_ok,
        "conservative_token_gate": conservative_saving_ok,
        "conservative_pareto_left_seed_gate": (
            conservative_pareto_left_seed_ok
        ),
        "balanced_accuracy_gate": balanced_drop_ok,
        "balanced_token_gate": balanced_saving_ok,
        "balanced_per_model_floor_gate": balanced_model_floor_ok,
        "formal_baselines_present": formal_baselines_present,
        "formal_baselines_three_seed": formal_baselines_three_seed,
        "primary_gate_pass": bool(
            complete_models
            and simple_methods_complete
            and seed_complete
            and conservative_drop_ok
            and conservative_saving_ok
            and conservative_pareto_left_seed_ok
            and balanced_drop_ok
            and balanced_saving_ok
            and balanced_model_floor_ok
        ),
    }


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text())
    out_dir = args.out_dir or args.root / "aggregate"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries, details = load_runs(args.root)
    model_results = model_summary(
        summaries, details, args.bootstrap, args.bootstrap_seed
    )
    mechanisms = mechanism_summary(args.root)
    gate = submission_gate(model_results, protocol)
    summaries.to_csv(out_dir / "per_seed_summary.csv", index=False)
    model_results.to_csv(out_dir / "model_seed_aggregate.csv", index=False)
    mechanisms.to_csv(out_dir / "mechanism_per_seed.csv", index=False)
    (out_dir / "submission_gate.json").write_text(
        json.dumps(gate, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "runs": int(summaries["run_id"].nunique()),
                "models": sorted(summaries["model"].unique()),
                "gate": gate,
                "output": str(out_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
