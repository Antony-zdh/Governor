#!/usr/bin/env python3
"""Leakage-safe freeze and Test evaluation for the expanded Governor pool.

Run ``freeze`` first.  It reads only development Train/Dev sweep rows and
writes immutable selected rule IDs plus source hashes.  The separate
``evaluate`` command verifies that manifest before opening confirmation/Test
trajectories.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from benchmark.FalseConsensus.governor_v2.replay_rules import (
    discover_runs,
    expected_development_environment_keys,
    load_jsonl,
    load_probes,
    load_split_map,
    pareto_frontier,
    protocol_benchmark,
    replay_one,
    scheduled_probes,
    selection_candidates,
)
from benchmark.FalseConsensus.governor_v2.rule_schema import RuleSpec


HERE = Path(__file__).resolve().parent
GOVERNOR = HERE.parent
REPO = GOVERNOR.parents[2]
PROTOCOL = GOVERNOR / "protocol.json"
SPLITS = GOVERNOR / "generated/split_manifest.json"
ORIGINAL_RULES = GOVERNOR / "generated/candidate_rules.jsonl"
ORIGINAL_SWEEPS = [GOVERNOR / f"generated/sweep_{index}.jsonl.gz" for index in range(8)]
LONG_ROOT = GOVERNOR / "generated/long_persistence_sensitivity"
LONG_RULES = LONG_ROOT / "candidate_rules_incremental.jsonl"
LONG_SWEEPS = [LONG_ROOT / f"sweep_{index}.jsonl.gz" for index in range(8)]
RESULTS_ROOT = REPO / "benchmark/FalseConsensus/results/governor_v2"
OUTPUT = RESULTS_ROOT / "extended_frozen_selection"
FIGURES = REPO / "benchmark/FalseConsensus/report/figures"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_sweeps(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def load_pool() -> tuple[dict[str, RuleSpec], list[dict[str, Any]]]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    original = {
        rule.rule_id: rule
        for rule in (RuleSpec.from_dict(row) for row in load_jsonl(ORIGINAL_RULES))
    }
    incremental = {
        rule.rule_id: rule
        for rule in (RuleSpec.from_dict(row) for row in load_jsonl(LONG_RULES))
    }
    if set(original) & set(incremental):
        raise ValueError("original and post-hoc rule IDs overlap")
    rules = {**original, **incremental}
    candidates = selection_candidates(
        read_sweeps(ORIGINAL_SWEEPS + LONG_SWEEPS),
        rules,
        expected_environments=expected_development_environment_keys(protocol),
    )
    if len(original) != 17_712 or len(incremental) != 15_552 or len(candidates) != 33_264:
        raise ValueError(
            f"candidate coverage mismatch: {len(original)}/{len(incremental)}/{len(candidates)}"
        )
    return rules, candidates


def practical_frontier(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest = [
        dict(row)
        for row in candidates
        if str(row["rule_id"]).startswith("latest_persistence_fixed_maturity__")
        and float(row["dev_q20_saving_fraction"]) > 0
        and float(row["positive_saving_fraction"]) >= 0.8
    ]
    frontier = pareto_frontier(latest)
    if len(frontier) < 3:
        raise ValueError("fewer than three practical strict-persistence frontier points")
    return frontier


def risk(row: Mapping[str, Any]) -> float:
    return max(
        float(row["max_model_accuracy_drop_pp"]),
        float(row["max_benchmark_accuracy_drop_pp"]),
    )


def choose_points(frontier: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    safe = min(
        frontier,
        key=lambda row: (
            risk(row),
            float(row["max_model_accuracy_drop_pp"])
            + float(row["max_benchmark_accuracy_drop_pp"]),
            -float(row["dev_q20_saving_fraction"]),
            int(row["complexity"]),
        ),
    )
    efficient_pool = [row for row in frontier if risk(row) <= 10.0]
    efficient = max(
        efficient_pool,
        key=lambda row: (
            float(row["dev_q20_saving_fraction"]),
            -risk(row),
            -int(row["complexity"]),
        ),
    )
    remaining = [
        row for row in efficient_pool
        if row["rule_id"] not in {safe["rule_id"], efficient["rule_id"]}
    ]
    r_min, r_max = min(map(risk, efficient_pool)), max(map(risk, efficient_pool))
    s_min = min(float(row["dev_q20_saving_fraction"]) for row in efficient_pool)
    s_max = max(float(row["dev_q20_saving_fraction"]) for row in efficient_pool)

    def knee_distance(row: Mapping[str, Any]) -> tuple[float, float, int]:
        normalized_risk = (risk(row) - r_min) / (r_max - r_min or 1.0)
        saving_loss = (s_max - float(row["dev_q20_saving_fraction"])) / (
            s_max - s_min or 1.0
        )
        return (
            math.hypot(normalized_risk, saving_loss),
            risk(row),
            int(row["complexity"]),
        )

    balanced = min(remaining, key=knee_distance)
    selected = {
        "safe": dict(safe),
        "balanced_knee": dict(balanced),
        "token_efficient": dict(efficient),
    }
    if len({row["rule_id"] for row in selected.values()}) != 3:
        raise AssertionError("selection did not produce three distinct rules")
    return selected


def freeze() -> None:
    rules, candidates = load_pool()
    full_frontier = pareto_frontier(candidates)
    practical = practical_frontier(candidates)
    selected = choose_points(practical)
    candidate_by_id = {str(row["rule_id"]): dict(row) for row in candidates}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "train_dev_candidates.csv", candidates)
    manifest = {
        "schema_version": "governor-v2-extended-freeze-1",
        "status": "frozen_before_test_evaluation",
        "selection_scope": "development Train/Dev only",
        "test_data_read": False,
        "candidate_counts": {
            "preregistered": 17_712,
            "post_hoc_long_persistence": 15_552,
            "combined": len(candidates),
            "combined_frontier": len(full_frontier),
            "practical_strict_persistence_frontier": len(practical),
        },
        "selection_rule": {
            "common_filter": (
                "latest_persistence_fixed_maturity; dev q20 saving > 0; "
                "positive-saving fraction >= 0.8; non-dominated on frozen axes"
            ),
            "safe": "minimum max(worst-model drop, worst-benchmark drop)",
            "balanced_knee": (
                "minimum normalized Euclidean distance to ideal risk=minimum, "
                "dev-q20-saving=maximum among practical points with risk <=10pp"
            ),
            "token_efficient": "maximum dev q20 saving among practical risk <=10pp",
        },
        "selected": {
            name: {
                "metrics": row,
                "rule": rules[str(row["rule_id"])].to_dict(),
                "source": (
                    "post_hoc_long_persistence"
                    if str(row["rule_id"]) in {
                        rule.rule_id for rule in rules.values()
                        if rule.persistence.minimum_consistent_accepts in {10, 12, 16, 20, 25, 30}
                    }
                    else "preregistered"
                ),
            }
            for name, row in selected.items()
        },
        "source_sha256": {
            str(path.relative_to(REPO)): sha256(path)
            for path in [PROTOCOL, SPLITS, ORIGINAL_RULES, LONG_RULES]
            + ORIGINAL_SWEEPS + LONG_SWEEPS
        },
        "integrity": {
            "selected_distinct": True,
            "all_selected_present_in_train_dev_candidates": all(
                str(row["rule_id"]) in candidate_by_id for row in selected.values()
            ),
        },
    }
    atomic_json(OUTPUT / "selection_manifest.json", manifest)
    print(json.dumps({name: row["rule_id"] for name, row in selected.items()}, indent=2))


def test_runs() -> list[Path]:
    runs = []
    for main_run in discover_runs(RESULTS_ROOT, "confirmation"):
        manifest = json.loads((main_run / "run_manifest.json").read_text(encoding="utf-8"))
        settings = manifest["run_settings"]
        if settings.get("model_role") != "development":
            continue
        if int(settings.get("base_seed")) not in {45, 46, 47}:
            continue
        runs.append(main_run)
    if len(runs) != 18:
        raise ValueError(f"expected 18 seen-model Test environments, found {len(runs)}")
    return sorted(runs)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    stopped = [row for row in rows if row["stopped"]]
    baseline_correct = sum(bool(row["baseline_correct"]) for row in rows)
    correct = sum(bool(row["correct"]) for row in rows)
    baseline_tokens = sum(int(row["baseline_decode_tokens"]) for row in rows)
    total_tokens = sum(int(row["total_decode_tokens"]) for row in rows)
    harms = sum(bool(row["baseline_correct"] and not row["correct"]) for row in rows)
    rescues = sum(bool(not row["baseline_correct"] and row["correct"]) for row in rows)
    return {
        "n": n,
        "accuracy_pct": 100 * correct / n,
        "baseline_accuracy_pct": 100 * baseline_correct / n,
        "accuracy_drop_pp": 100 * (baseline_correct - correct) / n,
        "all_generated_token_saving_pct": 100 * (baseline_tokens - total_tokens) / baseline_tokens,
        "stop_rate_pct": 100 * len(stopped) / n,
        "stop_accuracy_pct": (
            100 * sum(bool(row["correct"]) for row in stopped) / len(stopped)
            if stopped else math.nan
        ),
        "false_stop_ratio_pct": (
            100 * sum(not bool(row["correct"]) for row in stopped) / len(stopped)
            if stopped else math.nan
        ),
        "harm_count": harms,
        "rescue_count": rescues,
        "harm_rescue_ratio": harms / rescues if rescues else math.inf,
        "total_baseline_tokens": baseline_tokens,
        "total_method_tokens": total_tokens,
    }


def group(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return [
        {**dict(zip(keys, key)), **summarize(values)}
        for key, values in sorted(groups.items(), key=lambda item: tuple(map(str, item[0])))
    ]


def macro(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = (
        "accuracy_pct", "baseline_accuracy_pct", "accuracy_drop_pp",
        "all_generated_token_saving_pct", "stop_rate_pct", "stop_accuracy_pct",
        "false_stop_ratio_pct",
    )
    output = {"environment_count": len(rows)}
    for field in fields:
        values = [float(row[field]) for row in rows if math.isfinite(float(row[field]))]
        output[field] = math.fsum(values) / len(values) if values else math.nan
    harm_rate = math.fsum(float(row["harm_count"]) / int(row["n"]) for row in rows)
    rescue_rate = math.fsum(float(row["rescue_count"]) / int(row["n"]) for row in rows)
    output["harm_rate_pct"] = 100 * harm_rate / len(rows)
    output["rescue_rate_pct"] = 100 * rescue_rate / len(rows)
    output["harm_rescue_ratio"] = harm_rate / rescue_rate if rescue_rate else math.inf
    return output


def evaluate() -> None:
    manifest_path = OUTPUT / "selection_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("run freeze before evaluate")
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    if frozen.get("test_data_read") is not False:
        raise ValueError("selection manifest is not a pre-Test freeze")
    for relative, expected in frozen["source_sha256"].items():
        if sha256(REPO / relative) != expected:
            raise ValueError(f"frozen selection source changed: {relative}")
    rules = {
        name: RuleSpec.from_dict(payload["rule"])
        for name, payload in frozen["selected"].items()
    }
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    split_map = load_split_map(SPLITS)
    rows: list[dict[str, Any]] = []
    for main_run in test_runs():
        run_manifest = json.loads((main_run / "run_manifest.json").read_text(encoding="utf-8"))
        settings = run_manifest["run_settings"]
        benchmark = str(settings["dataset"])
        budget = int(protocol_benchmark(protocol, benchmark)["selection_budget"])
        environment_n = 0
        for trajectory_path in sorted((main_run / "traj").glob("problem_*.json")):
            trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
            problem_id = int(trajectory["problem_id"])
            if split_map[(benchmark, problem_id)] != "test":
                raise ValueError(f"confirmation contains non-Test problem: {benchmark}/{problem_id}")
            probes = load_probes(main_run, problem_id)
            environment_n += 1
            schedule_cache: dict[Any, list[dict[str, Any]]] = {}
            for name, rule in rules.items():
                schedule = rule.probe.schedule
                key = (
                    schedule.kind, schedule.start_token, schedule.interval_tokens,
                    schedule.phases, schedule.agreement_trigger_count,
                    schedule.agreement_interval_tokens, schedule.event, budget,
                )
                if key not in schedule_cache:
                    schedule_cache[key] = scheduled_probes(probes, rule, budget)
                outcome = replay_one(
                    trajectory,
                    schedule_cache[key],
                    rule,
                    benchmark,
                    budget,
                    probes_are_scheduled=True,
                )
                rows.append(
                    {
                        "profile": name,
                        "rule_id": rule.rule_id,
                        "model": str(settings["model"]),
                        "benchmark": benchmark,
                        "seed": int(settings["base_seed"]),
                        "problem_id": problem_id,
                        "budget": budget,
                        **outcome,
                    }
                )
        expected = {"math500": 100, "amc23": 8, "aime24": 6}[benchmark]
        if environment_n != expected:
            raise ValueError(f"{main_run.parent.name}: {environment_n} != {expected}")
    if len(rows) != 3 * 684:
        raise ValueError(f"expected 2052 selected Test rows, found {len(rows)}")
    write_csv(OUTPUT / "test_per_problem.csv", rows)
    environments = group(rows, ("profile", "rule_id", "model", "benchmark", "seed"))
    write_csv(OUTPUT / "test_per_environment.csv", environments)
    summary_rows: list[dict[str, Any]] = []
    for name, rule in rules.items():
        subset = [row for row in rows if row["profile"] == name]
        env = [row for row in environments if row["profile"] == name]
        summary_rows.append(
            {"profile": name, "rule_id": rule.rule_id, "aggregation": "pooled", **summarize(subset)}
        )
        summary_rows.append(
            {"profile": name, "rule_id": rule.rule_id, "aggregation": "environment_macro", **macro(env)}
        )
        for keys, label in (
            (("model",), "per_model"),
            (("benchmark",), "per_benchmark"),
            (("seed",), "per_seed"),
        ):
            for item in group(subset, keys):
                summary_rows.append(
                    {"profile": name, "rule_id": rule.rule_id, "aggregation": label, **item}
                )
    write_csv(OUTPUT / "test_summary.csv", summary_rows)
    evaluated_manifest = {
        **frozen,
        "test_evaluation": {
            "complete": True,
            "rows": len(rows),
            "environments": len(environments) // len(rules),
            "scope": "2 seen models x 3 benchmarks x seeds 45/46/47; Test only",
            "selection_budget_by_benchmark": {
                name: int(protocol_benchmark(protocol, name)["selection_budget"])
                for name in ("math500", "amc23", "aime24")
            },
            "token_accounting": (
                "all-generated = main tokens through stop/fallback + cumulative "
                "probe completion tokens; prompt/prefill reported separately"
            ),
        },
    }
    atomic_json(OUTPUT / "evaluated_manifest.json", evaluated_manifest)
    make_figure(summary_rows)
    (OUTPUT / "report.md").write_text(
        make_report(frozen, summary_rows), encoding="utf-8"
    )
    print(json.dumps({
        "rows": len(rows), "environments": len(environments),
        "selected": {name: rule.rule_id for name, rule in rules.items()},
    }, indent=2))


def related_points() -> list[dict[str, Any]]:
    output = []
    sources = [
        ("DEER", REPO / "benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30/aggregate/frontier.csv", "threshold"),
        ("TJE", REPO / "benchmark/FalseConsensus/results/related_work/tje_threshold_readout_bank_top1_6/aggregate/frontier.csv", "top_k"),
        ("CertaIndex", REPO / "benchmark/FalseConsensus/results/related_work/certaindex_effort_bank/aggregate/frontier.csv", "effort"),
    ]
    for method, path, parameter in sources:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("scope") != "test" or row.get("aggregation") != "model_benchmark_macro":
                    continue
                output.append(
                    {
                        "method": method,
                        "parameter": row[parameter],
                        "accuracy_drop_pp": float(row["accuracy_drop_pp"]),
                        "saving_pct": float(row["token_saving_pct"]),
                    }
                )
    return output


def make_figure(summary_rows: Sequence[Mapping[str, Any]]) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    for point in related_points():
        ax.scatter(point["accuracy_drop_pp"], point["saving_pct"], s=20, alpha=0.35,
                   label=point["method"] if point["parameter"] in {"0.95", "1", "mild"} else None)
    markers = {"safe": "o", "balanced_knee": "s", "token_efficient": "D"}
    for row in summary_rows:
        if row["aggregation"] != "environment_macro":
            continue
        ax.scatter(float(row["accuracy_drop_pp"]), float(row["all_generated_token_saving_pct"]),
                   marker=markers[str(row["profile"])], s=90, edgecolor="black",
                   label=f"Governor {row['profile']}", zorder=5)
        ax.annotate(str(row["profile"]),
                    (float(row["accuracy_drop_pp"]), float(row["all_generated_token_saving_pct"])),
                    xytext=(5, 5), textcoords="offset points", fontsize=8)
    oracle_path = RESULTS_ROOT / "simple32_oracle/per_environment.csv"
    if oracle_path.exists():
        with oracle_path.open(encoding="utf-8") as handle:
            oracle_rows = [row for row in csv.DictReader(handle) if row["split"] == "test"]
        if len(oracle_rows) != 18:
            raise ValueError(f"expected 18 Test oracle environments, found {len(oracle_rows)}")
        oracle_drop = sum(
            float(row["full_accuracy_strict_pct"])
            - float(row["oracle_accuracy_strict_pct"])
            for row in oracle_rows
        ) / len(oracle_rows)
        oracle_saving = sum(float(row["token_saving_micro_pct"]) for row in oracle_rows) / len(oracle_rows)
        ax.scatter(oracle_drop, oracle_saving, marker="*", s=190, color="#111827",
                   edgecolor="white", linewidth=0.8,
                   label="Oracle upper bound (uses labels)", zorder=7)
        ax.annotate("non-deployable oracle", (oracle_drop, oracle_saving),
                    xytext=(6, 5), textcoords="offset points", fontsize=8)
    ax.axvline(0, color="#6B7280", linewidth=0.8)
    ax.axhline(0, color="#6B7280", linewidth=0.8)
    ax.set_xlabel("Test accuracy drop vs full (pp; lower is better)")
    ax.set_ylabel("Test all-generated token saving (%)")
    ax.set_title("Frozen expanded Governor rules and related-work frontiers")
    ax.grid(alpha=0.22)
    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax.legend(unique.values(), unique.keys(), frameon=False, fontsize=8)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(FIGURES / f"governor_extended_frozen_test.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def make_report(frozen: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Expanded Governor freeze and Test evaluation",
        "",
        "Selection was frozen from Train/Dev before this command read Test. The "
        "15,552 long-window rules are explicitly post-hoc sensitivity candidates.",
        "",
        "| Profile | Rule | Source | Aggregation | Accuracy drop | Saving | Stop accuracy | False-stop | Harm/rescue |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["aggregation"] not in {"pooled", "environment_macro"}:
            continue
        source = frozen["selected"][str(row["profile"])]["source"]
        lines.append(
            f"| {row['profile']} | `{row['rule_id']}` | {source} | {row['aggregation']} | "
            f"{float(row['accuracy_drop_pp']):.2f} pp | "
            f"{float(row['all_generated_token_saving_pct']):.2f}% | "
            f"{float(row['stop_accuracy_pct']):.2f}% | "
            f"{float(row['false_stop_ratio_pct']):.2f}% | "
            f"{float(row['harm_rescue_ratio']):.2f} |"
        )
    lines.extend([
        "",
        "No selected point passed the original conservative preregistered gates; "
        "these three points are transparent representative operating points, not "
        "a claim that the original selection protocol succeeded.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python -m benchmark.FalseConsensus.governor_v2.analysis.freeze_extended_candidates freeze",
        "python -m benchmark.FalseConsensus.governor_v2.analysis.freeze_extended_candidates evaluate",
        "```",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "evaluate"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "freeze":
        freeze()
    else:
        evaluate()


if __name__ == "__main__":
    main()
