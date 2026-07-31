#!/usr/bin/env python3
"""Create immutable, auditable adjudication derivatives for Tasks A and B.

The two raw rater exports and the embedded HTML task records are read-only.
This script writes a separate adjudication layer under
``results/human_eval/adjudicated``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from benchmark.FalseConsensus.human_eval.analyze_reviews import (
    HERE,
    REPO,
    TAXONOMY_LABELS,
    TAXONOMY_NAMES,
    html_records,
    read_csv,
    true_verdict,
    validate_grader,
    validate_taxonomy,
    wilson,
    write_csv,
)


OUTPUT = REPO / "benchmark/FalseConsensus/results/human_eval/adjudicated"
FIGURE = REPO / "paper/figures/finding_map_appendix/a17_human_adjudicated.png"
TAXONOMY_FILES = [REPO / "taxonomy_review_1.csv", REPO / "taxonomy_review_2.csv"]
GRADER_FILES = [REPO / "grader_check_review_1.csv", REPO / "grader_check_review_2.csv"]


# User-specified operation of record: every A/D conflict is a reasoning gap.
AD_CONFLICT_RULE = (
    "A/D conflict -> D: an intermediate quantity, placeholder, or answer emitted "
    "before a final candidate was formed is a reasoning gap"
)

# The nine non-A/D disagreements are resolved directly from the frozen stop
# answer / probe stream under the task's published definitions.
NON_AD_TAXONOMY: dict[str, tuple[str, str]] = {
    "74": ("A", "wrong numeric stop answer 0"),
    "103": ("A", "wrong numeric stop answer 2"),
    "157": ("E", "non-choice problem converged to option letters"),
    "224": ("E", "non-choice problem converged to option letters"),
    "320": ("A", "wrong numeric stop answer 0"),
    "323": ("A", "wrong numeric stop answer 0.5"),
    "393": ("E", "non-choice problem stopped on option letter B"),
    "416": ("A", "wrong numeric stop answer 1"),
    "439": ("A", "wrong numeric persistence answer 1"),
}

# Five Task-B conflicts, adjudicated against the problem request and frozen
# gold/model answers.  RHS-only line equations and context-explicit base-9
# notation are accepted as semantically complete answers.
GRADER_ADJUDICATION: dict[str, tuple[str, str]] = {
    "5": ("correct", "2x+3 is the requested line's unambiguous RHS"),
    "7": ("correct", "40 is unambiguously base 9 in the requested answer context"),
    "9": ("correct", "2x+3 is the requested line's unambiguous RHS"),
    "51": ("correct", "-2x is the requested line's unambiguous RHS"),
    "57": ("incorrect", "15 is not equivalent to the reference count 315"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def taxonomy_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pre, conflicts = validate_taxonomy(TAXONOMY_FILES)
    left = {row["problem_id"]: row for row in read_csv(TAXONOMY_FILES[0])}
    right = {row["problem_id"]: row for row in read_csv(TAXONOMY_FILES[1])}
    conflict_ids = {row["problem_id"] for row in conflicts}
    output: list[dict[str, Any]] = []
    for problem_id in sorted(left, key=int):
        a = left[problem_id]["HUMAN_type[A-E]"]
        b = right[problem_id]["HUMAN_type[A-E]"]
        if a == b:
            final, basis = a, "rater agreement"
        elif {a, b} == {"A", "D"}:
            final, basis = "D", AD_CONFLICT_RULE
        else:
            if problem_id not in NON_AD_TAXONOMY:
                raise ValueError(f"unresolved non-A/D taxonomy conflict: {problem_id}")
            final, basis = NON_AD_TAXONOMY[problem_id]
        output.append(
            {
                "problem_id": problem_id,
                "rater_1_type": a,
                "rater_2_type": b,
                "adjudicated_type": final,
                "adjudicated_name": TAXONOMY_NAMES[final],
                "status": "adjudicated" if problem_id in conflict_ids else "agreed",
                "basis": basis,
            }
        )
    counts = Counter(row["adjudicated_type"] for row in output)
    summary = {
        "n": len(output),
        "pre_adjudication_agreement": pre["agreement"],
        "pre_adjudication_disagreements": pre["disagreement_count"],
        "ad_conflicts_resolved_to_d": sum(
            {row["rater_1_type"], row["rater_2_type"]} == {"A", "D"}
            for row in output
        ),
        "non_ad_conflicts_individually_resolved": len(NON_AD_TAXONOMY),
        "unresolved": 0,
        "final_label_counts": {label: counts[label] for label in TAXONOMY_LABELS},
        "final_label_fractions": {
            label: counts[label] / len(output) for label in TAXONOMY_LABELS
        },
        "interpretation": (
            "Adjudication produces labels of record; it does not retroactively "
            "increase the two-rater kappa."
        ),
    }
    return output, summary


def grader_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pre, conflicts = validate_grader(GRADER_FILES)
    expected = {str(row["row"]): row for row in html_records(HERE / "taskB_grader.html")}
    left = {row["row"]: row for row in read_csv(GRADER_FILES[0])}
    right = {row["row"]: row for row in read_csv(GRADER_FILES[1])}
    conflict_ids = {row["row"] for row in conflicts}
    output: list[dict[str, Any]] = []
    for row_id in sorted(expected, key=int):
        left_verdict = true_verdict(left[row_id])
        right_verdict = true_verdict(right[row_id])
        if left_verdict == right_verdict:
            final, basis = left_verdict, "rater agreement"
        else:
            if row_id not in GRADER_ADJUDICATION:
                raise ValueError(f"unresolved grader conflict: {row_id}")
            final, basis = GRADER_ADJUDICATION[row_id]
        grader_verdict = left[row_id]["grader_verdict"]
        grader_correct = final == grader_verdict
        output.append(
            {
                "row": row_id,
                "model": left[row_id]["model"],
                "benchmark": left[row_id]["benchmark"],
                "problem_id": left[row_id]["problem_id"],
                "gold_target": left[row_id]["gold_target"],
                "model_final_answer": left[row_id]["model_final_answer"],
                "grader_verdict": grader_verdict,
                "rater_1_true_verdict": left_verdict,
                "rater_2_true_verdict": right_verdict,
                "adjudicated_true_verdict": final,
                "grader_correct_after_adjudication": "y" if grader_correct else "n",
                "status": "adjudicated" if row_id in conflict_ids else "agreed",
                "basis": basis,
            }
        )
    errors = sum(row["grader_correct_after_adjudication"] == "n" for row in output)
    summary = {
        "n": len(output),
        "pre_adjudication_agreement": pre["agreement"],
        "conflicts_adjudicated": len(conflict_ids),
        "unresolved": 0,
        "grader_errors": errors,
        "risk_enriched_sample_error_rate": errors / len(output),
        "risk_enriched_sample_error_rate_wilson_95": wilson(errors, len(output)),
        "warning": (
            "This is a deliberately risk-enriched equivalence/near-match sample; "
            "the raw rate is not a population-wide grader error estimate."
        ),
    }
    return output, summary


def make_figure(taxonomy: dict[str, Any], grader: dict[str, Any]) -> None:
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.8))
    labels = TAXONOMY_LABELS
    counts = [taxonomy["final_label_counts"][label] for label in labels]
    bars = axes[0].bar(labels, counts, color="#2878B5")
    axes[0].bar_label(bars, padding=2)
    axes[0].set_title("Task A: adjudicated taxonomy")
    axes[0].set_ylabel("Cases")
    axes[0].grid(axis="y", alpha=0.2)

    correct = grader["n"] - grader["grader_errors"]
    values = [correct, grader["grader_errors"]]
    bars = axes[1].bar(
        ["Grader correct", "Grader wrong"], values, color=["#2A9D8F", "#D95F59"]
    )
    axes[1].bar_label(bars, padding=2)
    axes[1].set_title("Task B: adjudicated risk-enriched audit")
    axes[1].set_ylabel("Cases")
    axes[1].grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(FIGURE, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    taxonomy, taxonomy_summary = taxonomy_rows()
    grader, grader_summary = grader_rows()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "taxonomy_adjudicated.csv", taxonomy, list(taxonomy[0]))
    write_csv(OUTPUT / "grader_adjudicated.csv", grader, list(grader[0]))
    summary = {
        "schema_version": "false-consensus-human-adjudication-1",
        "taxonomy": taxonomy_summary,
        "grader": grader_summary,
        "source_sha256": {
            str(path.relative_to(REPO)): sha256(path)
            for path in TAXONOMY_FILES + GRADER_FILES
        },
        "raw_sources_modified": False,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    make_figure(taxonomy_summary, grader_summary)
    counts = taxonomy_summary["final_label_counts"]
    lines = [
        "# Human-evaluation adjudication",
        "",
        "Raw rater exports and task HTML were not modified. This directory is a "
        "separate adjudication layer.",
        "",
        "## Task A",
        "",
        f"- 134 cases; 70 pre-adjudication disagreements.",
        f"- 61 A/D conflicts resolved to D under the project operation of record.",
        f"- Final counts: " + ", ".join(f"{k}={v}" for k, v in counts.items()) + ".",
        "- The original two-rater agreement remains 47.76% (kappa 0.286); "
        "adjudication does not change inter-rater reliability.",
        "",
        "## Task B",
        "",
        f"- 89 risk-enriched cases; 5 conflicts adjudicated; "
        f"{grader_summary['grader_errors']} final grader errors.",
        f"- Risk-enriched sample error rate: "
        f"{100 * grader_summary['risk_enriched_sample_error_rate']:.2f}%.",
        "- This rate is not a population-wide grader error estimate.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "MPLCONFIGDIR=/tmp/governor-mpl python -m "
        "benchmark.FalseConsensus.human_eval.adjudicate_reviews",
        "```",
    ]
    (OUTPUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
