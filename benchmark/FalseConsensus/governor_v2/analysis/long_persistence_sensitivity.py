#!/usr/bin/env python3
"""Post-hoc long-persistence sensitivity for the Governor-v2 Pareto sweep.

This analysis deliberately leaves the preregistered 17,712-rule protocol and
its frozen sweep untouched.  It expands only the
``latest_persistence_fixed_maturity`` template at six additional strict
consensus lengths, replays those incremental rules, and then compares the
expanded Pareto frontier with the original one.
"""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


HERE = Path(__file__).resolve().parent
GOVERNOR = HERE.parent
REPO_ROOT = GOVERNOR.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.governor_v2.replay_rules import (  # noqa: E402
    expected_development_environment_keys,
    pareto_frontier,
    selection_candidates,
    sha256_file,
    write_jsonl,
)
from benchmark.FalseConsensus.governor_v2.rule_schema import (  # noqa: E402
    RuleSpec,
    expand_template,
)


PROTOCOL = GOVERNOR / "protocol.json"
ORIGINAL_RULES = GOVERNOR / "generated/candidate_rules.jsonl"
ORIGINAL_SWEEPS = [
    GOVERNOR / f"generated/sweep_{index}.jsonl.gz" for index in range(8)
]
GENERATED = GOVERNOR / "generated/long_persistence_sensitivity"
INCREMENTAL_RULES = GENERATED / "candidate_rules_incremental.jsonl"
METADATA = GENERATED / "protocol_addendum.json"
ANALYSIS = HERE / "long_persistence_sensitivity"

ORIGINAL_PERSISTENCE = (2, 3, 5, 8)
ADDED_PERSISTENCE = (10, 12, 16, 20, 25, 30)
EXPECTED_INCREMENTAL_RULES = 15_552
EXPECTED_ENVIRONMENTS_PER_RULE = 36


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def prepare() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    templates = protocol["rule_search"]["templates"]
    source = next(
        template
        for template in templates
        if template["name"] == "latest_persistence_fixed_maturity"
    )
    observed = tuple(
        source["axes"]["persistence.minimum_consistent_accepts"]
    )
    if observed != ORIGINAL_PERSISTENCE:
        raise ValueError(
            f"frozen persistence axis changed: {observed} != "
            f"{ORIGINAL_PERSISTENCE}"
        )
    incremental_template = copy.deepcopy(source)
    incremental_template["axes"][
        "persistence.minimum_consistent_accepts"
    ] = list(ADDED_PERSISTENCE)
    rules = expand_template(incremental_template)
    if len(rules) != EXPECTED_INCREMENTAL_RULES:
        raise ValueError(
            f"expected {EXPECTED_INCREMENTAL_RULES} incremental rules, "
            f"got {len(rules)}"
        )
    original_ids = {
        json.loads(line)["rule_id"]
        for line in ORIGINAL_RULES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    overlap = original_ids.intersection(rule.rule_id for rule in rules)
    if overlap:
        raise ValueError(f"incremental rules overlap frozen rules: {len(overlap)}")
    count = write_jsonl(INCREMENTAL_RULES, (rule.to_dict() for rule in rules))
    atomic_json(
        METADATA,
        {
            "schema_version": "governor-v2-long-persistence-sensitivity-1",
            "status": "post_hoc_sensitivity_not_preregistered",
            "source_protocol": str(PROTOCOL.relative_to(REPO_ROOT)),
            "source_protocol_sha256": sha256_file(PROTOCOL),
            "source_candidate_rules": str(ORIGINAL_RULES.relative_to(REPO_ROOT)),
            "source_candidate_rules_sha256": sha256_file(ORIGINAL_RULES),
            "template": "latest_persistence_fixed_maturity",
            "dimension": "persistence.minimum_consistent_accepts",
            "frozen_values": list(ORIGINAL_PERSISTENCE),
            "added_values": list(ADDED_PERSISTENCE),
            "incremental_rule_count": count,
            "incremental_rules_sha256": sha256_file(INCREMENTAL_RULES),
            "expected_environment_rows_per_rule": EXPECTED_ENVIRONMENTS_PER_RULE,
            "selection_scope": "development train+dev only",
            "confirmation_and_test_used_for_selection": False,
        },
    )
    print(
        json.dumps(
            {
                "incremental_rules": count,
                "rules": str(INCREMENTAL_RULES),
                "metadata": str(METADATA),
            }
        )
    )


def load_rule_specs(path: Path) -> list[RuleSpec]:
    return [RuleSpec.from_dict(row) for row in load_jsonl(path)]


def metric_paths() -> list[Path]:
    paths = []
    for index in range(8):
        compressed = GENERATED / f"sweep_{index}.jsonl.gz"
        plain = GENERATED / f"sweep_{index}.jsonl"
        if compressed.exists():
            paths.append(compressed)
        elif plain.exists():
            paths.append(plain)
        else:
            raise FileNotFoundError(f"missing sensitivity shard {index}")
    return paths


def aggregate_candidates(
    paths: Iterable[Path],
    rules: Mapping[str, RuleSpec],
    protocol: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(load_jsonl(path))
    candidates = selection_candidates(
        rows,
        rules,
        expected_environments=expected_development_environment_keys(protocol),
    )
    return candidates, len(rows)


def operating_point_counts(
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    gates = {
        "conservative": (1.5, 2.0, 0.8),
        "balanced": (2.5, 3.0, 0.8),
        "token_efficient": (4.0, 5.0, 0.7),
    }
    return {
        name: sum(
            float(row["max_model_accuracy_drop_pp"]) <= model_cap
            and float(row["max_benchmark_accuracy_drop_pp"]) <= benchmark_cap
            and float(row["positive_saving_fraction"]) >= psf
            for row in candidates
        )
        for name, (model_cap, benchmark_cap, psf) in gates.items()
    }


def candidate_view(
    candidate: Mapping[str, Any], rules: Mapping[str, RuleSpec]
) -> dict[str, Any]:
    rule = rules[str(candidate["rule_id"])]
    return {
        "rule_id": candidate["rule_id"],
        "window": rule.persistence.minimum_consistent_accepts,
        "max_model_accuracy_drop_pp": candidate["max_model_accuracy_drop_pp"],
        "max_benchmark_accuracy_drop_pp": candidate[
            "max_benchmark_accuracy_drop_pp"
        ],
        "dev_q20_saving_fraction": candidate["dev_q20_saving_fraction"],
        "mean_dev_saving_fraction": candidate["mean_dev_saving_fraction"],
        "positive_saving_fraction": candidate["positive_saving_fraction"],
        "complexity": candidate["complexity"],
    }


def best_by(
    rows: list[dict[str, Any]],
    *,
    key,
    predicate=lambda row: True,
) -> dict[str, Any] | None:
    eligible = [row for row in rows if predicate(row)]
    return min(eligible, key=key) if eligible else None


def summarize_window(
    window: int, rows: list[dict[str, Any]], frontier_ids: set[str]
) -> dict[str, Any]:
    minimum_drop = best_by(
        rows,
        key=lambda row: (
            row["max_model_accuracy_drop_pp"],
            -row["dev_q20_saving_fraction"],
        ),
    )
    positive_q20 = best_by(
        rows,
        predicate=lambda row: row["dev_q20_saving_fraction"] > 0,
        key=lambda row: (
            row["max_model_accuracy_drop_pp"],
            -row["dev_q20_saving_fraction"],
        ),
    )
    return {
        "window": window,
        "rule_count": len(rows),
        "combined_frontier_count": sum(
            row["rule_id"] in frontier_ids for row in rows
        ),
        "minimum_drop_point": minimum_drop,
        "minimum_drop_with_positive_q20_saving": positive_q20,
        "best_q20_saving_under_model_drop": {
            str(cap): (
                max(
                    (
                        row
                        for row in rows
                        if row["max_model_accuracy_drop_pp"] <= cap
                    ),
                    key=lambda row: row["dev_q20_saving_fraction"],
                    default=None,
                )
            )
            for cap in (1.5, 2.5, 4.0, 5.0, 10.0)
        },
    }


def fmt_pp(value: float | None) -> str:
    return "---" if value is None else f"{value:.2f}"


def fmt_pct(value: float | None) -> str:
    return "---" if value is None else f"{100 * value:.2f}%"


def analyze() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    original_specs = load_rule_specs(ORIGINAL_RULES)
    incremental_specs = load_rule_specs(INCREMENTAL_RULES)
    original_rules = {rule.rule_id: rule for rule in original_specs}
    incremental_rules = {rule.rule_id: rule for rule in incremental_specs}
    if len(incremental_rules) != EXPECTED_INCREMENTAL_RULES:
        raise ValueError("incremental rule count changed before analysis")

    original_candidates, original_metric_rows = aggregate_candidates(
        ORIGINAL_SWEEPS, original_rules, protocol
    )
    incremental_candidates, incremental_metric_rows = aggregate_candidates(
        metric_paths(), incremental_rules, protocol
    )
    expected_incremental_rows = (
        EXPECTED_INCREMENTAL_RULES * EXPECTED_ENVIRONMENTS_PER_RULE
    )
    if incremental_metric_rows != expected_incremental_rows:
        raise ValueError(
            f"expected {expected_incremental_rows} incremental metric rows, "
            f"got {incremental_metric_rows}"
        )

    all_rules = {**original_rules, **incremental_rules}
    all_candidates = original_candidates + incremental_candidates
    original_frontier = pareto_frontier(original_candidates)
    combined_frontier = pareto_frontier(all_candidates)
    original_frontier_ids = {str(row["rule_id"]) for row in original_frontier}
    combined_frontier_ids = {str(row["rule_id"]) for row in combined_frontier}
    new_frontier_ids = combined_frontier_ids.intersection(incremental_rules)

    incremental_views = [
        candidate_view(candidate, incremental_rules)
        for candidate in incremental_candidates
    ]
    by_window: dict[int, list[dict[str, Any]]] = {
        window: [] for window in ADDED_PERSISTENCE
    }
    for row in incremental_views:
        by_window[int(row["window"])].append(row)
    window_summaries = [
        summarize_window(window, by_window[window], combined_frontier_ids)
        for window in ADDED_PERSISTENCE
    ]

    ANALYSIS.mkdir(parents=True, exist_ok=True)
    with (ANALYSIS / "incremental_candidates.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(incremental_views[0]),
        )
        writer.writeheader()
        writer.writerows(incremental_views)
    with (ANALYSIS / "combined_frontier.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fields = [
            "rule_id",
            "source",
            "window",
            "max_model_accuracy_drop_pp",
            "max_benchmark_accuracy_drop_pp",
            "dev_q20_saving_fraction",
            "mean_dev_saving_fraction",
            "positive_saving_fraction",
            "complexity",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate in combined_frontier:
            rule_id = str(candidate["rule_id"])
            rule = all_rules[rule_id]
            writer.writerow(
                {
                    "rule_id": rule_id,
                    "source": (
                        "long_window_incremental"
                        if rule_id in incremental_rules
                        else "preregistered_original"
                    ),
                    "window": rule.persistence.minimum_consistent_accepts,
                    **{field: candidate[field] for field in fields[3:]},
                }
            )

    summary = {
        "schema_version": "governor-v2-long-persistence-sensitivity-summary-1",
        "status": "post_hoc_sensitivity_not_preregistered",
        "added_windows": list(ADDED_PERSISTENCE),
        "counts": {
            "original_rules": len(original_candidates),
            "incremental_rules": len(incremental_candidates),
            "combined_rules": len(all_candidates),
            "original_metric_rows": original_metric_rows,
            "incremental_metric_rows": incremental_metric_rows,
            "original_frontier": len(original_frontier),
            "combined_frontier": len(combined_frontier),
            "new_rules_on_combined_frontier": len(new_frontier_ids),
            "original_frontier_rules_retained": len(
                original_frontier_ids.intersection(combined_frontier_ids)
            ),
        },
        "operating_point_eligible": {
            "incremental_only": operating_point_counts(incremental_candidates),
            "combined": operating_point_counts(all_candidates),
        },
        "new_frontier_rule_ids": sorted(new_frontier_ids),
        "windows": window_summaries,
        "integrity": {
            "incremental_rules_sha256": sha256_file(INCREMENTAL_RULES),
            "sensitivity_metric_sha256": {
                path.name: sha256_file(path) for path in metric_paths()
            },
            "metric_rows_complete": (
                incremental_metric_rows == expected_incremental_rows
            ),
            "window_rule_counts": dict(
                sorted(Counter(row["window"] for row in incremental_views).items())
            ),
        },
    }
    atomic_json(ANALYSIS / "summary.json", summary)

    lines = [
        "# Long strict-consensus persistence sensitivity",
        "",
        "Post-hoc sensitivity only; the preregistered 17,712-rule sweep is "
        "unchanged. Added strict latest-answer persistence windows "
        "`10/12/16/20/25/30` and replayed them on the same development "
        "train+dev environments.",
        "",
        "## Integrity",
        "",
        f"- Incremental rules: **{len(incremental_candidates):,}**",
        f"- Incremental metric rows: **{incremental_metric_rows:,}**",
        f"- Combined rules: **{len(all_candidates):,}**",
        f"- Original / expanded frontier size: "
        f"**{len(original_frontier)} / {len(combined_frontier)}**",
        f"- New long-window rules on expanded frontier: "
        f"**{len(new_frontier_ids)}**",
        "",
        "## Window summary",
        "",
        "| w | rules | new frontier | min worst-model drop | q20 saving there | "
        "min drop with q20 saving > 0 | q20 saving |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in window_summaries:
        minimum = row["minimum_drop_point"]
        positive = row["minimum_drop_with_positive_q20_saving"]
        lines.append(
            f"| {row['window']} | {row['rule_count']:,} | "
            f"{row['combined_frontier_count']} | "
            f"{fmt_pp(minimum['max_model_accuracy_drop_pp'])} pp | "
            f"{fmt_pct(minimum['dev_q20_saving_fraction'])} | "
            f"{fmt_pp(positive['max_model_accuracy_drop_pp']) if positive else '---'}"
            f"{' pp' if positive else ''} | "
            f"{fmt_pct(positive['dev_q20_saving_fraction']) if positive else '---'} |"
        )
    lines.extend(
        [
            "",
            "## Frozen gate check",
            "",
            "| scope | conservative | balanced | token-efficient |",
            "|---|---:|---:|---:|",
            (
                "| incremental long-window rules | "
                f"{summary['operating_point_eligible']['incremental_only']['conservative']} | "
                f"{summary['operating_point_eligible']['incremental_only']['balanced']} | "
                f"{summary['operating_point_eligible']['incremental_only']['token_efficient']} |"
            ),
            (
                "| combined sweep | "
                f"{summary['operating_point_eligible']['combined']['conservative']} | "
                f"{summary['operating_point_eligible']['combined']['balanced']} | "
                f"{summary['operating_point_eligible']['combined']['token_efficient']} |"
            ),
            "",
            "Primary Pareto axes follow the frozen selector: minimize worst "
            "train/dev per-model and per-benchmark accuracy drop while "
            "maximizing dev q20 token saving.",
        ]
    )
    (ANALYSIS / "report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["counts"], indent=2))
    print(json.dumps(summary["operating_point_eligible"], indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "analyze"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "prepare":
        prepare()
    else:
        analyze()


if __name__ == "__main__":
    main()
