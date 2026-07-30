#!/usr/bin/env python3
"""Validate and summarize the two double-annotated human-evaluation tasks."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_OUTPUT = REPO / "benchmark/FalseConsensus/results/human_eval"
DEFAULT_FIGURE = (
    REPO / "paper/figures/finding_map_appendix/a17_human_evaluation.png"
)

TAXONOMY_LABELS = ["A", "B", "C", "D", "E"]
TAXONOMY_NAMES = {
    "A": "Numeric collapse",
    "B": "Expression collapse",
    "C": "Sign error",
    "D": "Reasoning gap",
    "E": "Format hallucination",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--taxonomy",
        type=Path,
        nargs=2,
        default=[REPO / "taxonomy_review_1.csv", REPO / "taxonomy_review_2.csv"],
    )
    parser.add_argument(
        "--grader",
        type=Path,
        nargs=2,
        default=[
            REPO / "grader_check_review_1.csv",
            REPO / "grader_check_review_2.csv",
        ],
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"unsupported CSV encoding: {path}")
    return [
        {str(key): str(value or "").strip() for key, value in row.items()}
        for row in csv.DictReader(text.splitlines())
    ]


def display_path(path: Path) -> str:
    """Use stable repository-relative paths in committed audit artifacts."""

    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path)


def html_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="data">(.*?)</script>',
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError(f"embedded task data not found: {path}")
    return json.loads(match.group(1))


def cohen_kappa(left: Iterable[str], right: Iterable[str]) -> dict[str, float]:
    pairs = list(zip(left, right))
    if not pairs:
        raise ValueError("cannot compute agreement on empty inputs")
    labels = sorted({value for pair in pairs for value in pair})
    observed = sum(a == b for a, b in pairs) / len(pairs)
    left_counts = Counter(a for a, _ in pairs)
    right_counts = Counter(b for _, b in pairs)
    expected = sum(
        left_counts[label] * right_counts[label] for label in labels
    ) / (len(pairs) ** 2)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0
    return {
        "n": len(pairs),
        "raw_agreement": observed,
        "expected_agreement": expected,
        "cohen_kappa": kappa,
    }


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [float("nan"), float("nan")]
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return [center - margin, center + margin]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_taxonomy(
    paths: list[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frozen = json.loads(
        (
            REPO
            / "benchmark/FalseConsensus/results/stage1_logging/analysis/"
            "false_consensus_cases.json"
        ).read_text(encoding="utf-8")
    )
    expected_ids = {str(row["problem_id"]) for row in frozen}
    by_rater = []
    rater_summaries = []
    for index, path in enumerate(paths, start=1):
        rows = read_csv(path)
        keys = [row["problem_id"] for row in rows]
        observed = set(keys)
        duplicate = sorted(key for key, count in Counter(keys).items() if count > 1)
        missing = sorted(expected_ids - observed, key=int)
        extra = sorted(observed - expected_ids, key=int)
        invalid_types = [
            row["problem_id"]
            for row in rows
            if row["HUMAN_type[A-E]"] not in TAXONOMY_LABELS
        ]
        invalid_confidence = [
            row["problem_id"]
            for row in rows
            if row["HUMAN_confident[y/n]"] not in {"y", "n"}
        ]
        if duplicate or missing or extra or invalid_types or invalid_confidence:
            raise ValueError(
                f"incomplete taxonomy export {path}: duplicates={duplicate} "
                f"missing={missing} extra={extra} invalid_types={invalid_types} "
                f"invalid_confidence={invalid_confidence}"
            )
        indexed = {row["problem_id"]: row for row in rows}
        by_rater.append(indexed)
        counts = Counter(row["HUMAN_type[A-E]"] for row in rows)
        rater_summaries.append(
            {
                "rater": index,
                "file": display_path(path),
                "rows": len(rows),
                "label_counts": {
                    label: counts[label] for label in TAXONOMY_LABELS
                },
                "confident_y": sum(
                    row["HUMAN_confident[y/n]"] == "y" for row in rows
                ),
                "notes_nonempty": sum(bool(row["HUMAN_notes"]) for row in rows),
            }
        )

    common = sorted(expected_ids, key=int)
    labels_left = [by_rater[0][key]["HUMAN_type[A-E]"] for key in common]
    labels_right = [by_rater[1][key]["HUMAN_type[A-E]"] for key in common]
    agreement = cohen_kappa(labels_left, labels_right)
    conflicts = []
    for key in common:
        left = by_rater[0][key]
        right = by_rater[1][key]
        if left["HUMAN_type[A-E]"] != right["HUMAN_type[A-E]"]:
            conflicts.append(
                {
                    "problem_id": key,
                    "rater_1_type": left["HUMAN_type[A-E]"],
                    "rater_2_type": right["HUMAN_type[A-E]"],
                    "rater_1_confident": left["HUMAN_confident[y/n]"],
                    "rater_2_confident": right["HUMAN_confident[y/n]"],
                    "rater_1_notes": left["HUMAN_notes"],
                    "rater_2_notes": right["HUMAN_notes"],
                }
            )
    matrix = {
        left: {
            right: sum(
                a == left and b == right
                for a, b in zip(labels_left, labels_right)
            )
            for right in TAXONOMY_LABELS
        }
        for left in TAXONOMY_LABELS
    }
    return (
        {
            "expected_rows": len(expected_ids),
            "raters": rater_summaries,
            "agreement": agreement,
            "agreement_count": len(common) - len(conflicts),
            "disagreement_count": len(conflicts),
            "confusion_matrix_rater1_by_rater2": matrix,
            "adjudication_required": bool(conflicts),
        },
        conflicts,
    )


def true_verdict(row: dict[str, str]) -> str:
    if row["HUMAN_grader_correct?[y/n]"] == "y":
        return row["grader_verdict"]
    stated = row["HUMAN_true_verdict[correct/incorrect]"]
    if stated:
        return stated
    # The task is binary, so a missing follow-up after marking the grader wrong
    # can be reconstructed, but it remains a schema-completeness issue.
    return "incorrect" if row["grader_verdict"] == "correct" else "correct"


def validate_grader(
    paths: list[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = {
        str(row["row"]): row
        for row in html_records(HERE / "taskB_grader.html")
    }
    expected_rows = set(expected)
    by_rater = []
    rater_summaries = []
    for index, path in enumerate(paths, start=1):
        rows = read_csv(path)
        keys = [row["row"] for row in rows]
        observed = set(keys)
        duplicate = sorted(key for key, count in Counter(keys).items() if count > 1)
        missing = sorted(expected_rows - observed, key=int)
        extra = sorted(observed - expected_rows, key=int)
        invalid_correct = [
            row["row"]
            for row in rows
            if row["HUMAN_grader_correct?[y/n]"] not in {"y", "n"}
        ]
        invalid_true = [
            row["row"]
            for row in rows
            if row["HUMAN_grader_correct?[y/n]"] == "n"
            and row["HUMAN_true_verdict[correct/incorrect]"]
            not in {"correct", "incorrect"}
        ]
        identity_mismatch = []
        for row in rows:
            record = expected.get(row["row"])
            if record is None:
                continue
            if (
                row["model"] != str(record["model"])
                or row["benchmark"] != str(record["benchmark"])
                or row["problem_id"] != str(record["pid"])
                or row["grader_verdict"]
                != ("correct" if record["correct"] else "incorrect")
            ):
                identity_mismatch.append(row["row"])
        if (
            duplicate
            or missing
            or extra
            or invalid_correct
            or identity_mismatch
        ):
            raise ValueError(
                f"incomplete grader export {path}: duplicates={duplicate} "
                f"missing={missing} extra={extra} invalid_correct={invalid_correct} "
                f"invalid_true={invalid_true} identity_mismatch={identity_mismatch}"
            )
        indexed = {row["row"]: row for row in rows}
        by_rater.append(indexed)
        errors = sum(row["HUMAN_grader_correct?[y/n]"] == "n" for row in rows)
        rater_summaries.append(
            {
                "rater": index,
                "file": display_path(path),
                "rows": len(rows),
                "grader_errors": errors,
                "sample_error_rate": errors / len(rows),
                "sample_error_rate_wilson_95": wilson(errors, len(rows)),
                "missing_required_true_verdict_rows": invalid_true,
                "notes_nonempty": sum(bool(row["HUMAN_notes"]) for row in rows),
            }
        )

    common = sorted(expected_rows, key=int)
    decisions_left = [
        by_rater[0][key]["HUMAN_grader_correct?[y/n]"] for key in common
    ]
    decisions_right = [
        by_rater[1][key]["HUMAN_grader_correct?[y/n]"] for key in common
    ]
    agreement = cohen_kappa(decisions_left, decisions_right)
    conflicts = []
    for key in common:
        left = by_rater[0][key]
        right = by_rater[1][key]
        if true_verdict(left) != true_verdict(right):
            conflicts.append(
                {
                    "row": key,
                    "model": left["model"],
                    "benchmark": left["benchmark"],
                    "problem_id": left["problem_id"],
                    "grader_verdict": left["grader_verdict"],
                    "rater_1_grader_correct": left[
                        "HUMAN_grader_correct?[y/n]"
                    ],
                    "rater_2_grader_correct": right[
                        "HUMAN_grader_correct?[y/n]"
                    ],
                    "rater_1_true_verdict": true_verdict(left),
                    "rater_2_true_verdict": true_verdict(right),
                    "rater_1_notes": left["HUMAN_notes"],
                    "rater_2_notes": right["HUMAN_notes"],
                }
            )
    both_error = sum(
        by_rater[0][key]["HUMAN_grader_correct?[y/n]"] == "n"
        and by_rater[1][key]["HUMAN_grader_correct?[y/n]"] == "n"
        for key in common
    )
    both_correct = sum(
        by_rater[0][key]["HUMAN_grader_correct?[y/n]"] == "y"
        and by_rater[1][key]["HUMAN_grader_correct?[y/n]"] == "y"
        for key in common
    )
    consensus_total = both_error + both_correct
    strata = Counter(
        (
            by_rater[0][key]["model"],
            by_rater[0][key]["benchmark"],
            by_rater[0][key]["grader_verdict"],
        )
        for key in common
    )
    return (
        {
            "expected_rows": len(expected_rows),
            "raters": rater_summaries,
            "agreement": agreement,
            "true_verdict_agreement_count": len(common) - len(conflicts),
            "true_verdict_disagreement_count": len(conflicts),
            "both_say_grader_correct": both_correct,
            "both_say_grader_wrong": both_error,
            "consensus_rows_before_adjudication": consensus_total,
            "consensus_sample_error_rate": (
                both_error / consensus_total if consensus_total else None
            ),
            "consensus_sample_error_rate_wilson_95": (
                wilson(both_error, consensus_total) if consensus_total else None
            ),
            "sample_composition": {
                " | ".join(key): value for key, value in sorted(strata.items())
            },
            "stratified_sample_warning": (
                "The sample oversamples risky equivalence/near-match cases. "
                "Its raw error rate is not a population-wide grader error rate."
            ),
            "schema_complete": not any(
                row["missing_required_true_verdict_rows"]
                for row in rater_summaries
            ),
            "adjudication_required": bool(conflicts),
        },
        conflicts,
    )


def make_figure(
    taxonomy: dict[str, Any],
    grader: dict[str, Any],
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.65))

    x = np.arange(len(TAXONOMY_LABELS))
    width = 0.36
    counts_1 = [
        taxonomy["raters"][0]["label_counts"][label]
        for label in TAXONOMY_LABELS
    ]
    counts_2 = [
        taxonomy["raters"][1]["label_counts"][label]
        for label in TAXONOMY_LABELS
    ]
    bars_1 = axes[0].bar(
        x - width / 2, counts_1, width, label="Rater 1", color="#2878B5"
    )
    bars_2 = axes[0].bar(
        x + width / 2, counts_2, width, label="Rater 2", color="#F28E2B"
    )
    axes[0].bar_label(bars_1, padding=2, fontsize=8)
    axes[0].bar_label(bars_2, padding=2, fontsize=8)
    axes[0].set_xticks(
        x,
        TAXONOMY_LABELS,
    )
    axes[0].set_ylabel("Cases")
    axes[0].set_title(
        "Task A: false-consensus taxonomy\n"
        f"agreement={100 * taxonomy['agreement']['raw_agreement']:.1f}%, "
        f"kappa={taxonomy['agreement']['cohen_kappa']:.3f}"
    )
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].grid(axis="y", alpha=0.22)

    rater_errors = [
        grader["raters"][0]["grader_errors"],
        grader["raters"][1]["grader_errors"],
    ]
    rates = [
        100 * grader["raters"][0]["sample_error_rate"],
        100 * grader["raters"][1]["sample_error_rate"],
    ]
    intervals = [
        grader["raters"][0]["sample_error_rate_wilson_95"],
        grader["raters"][1]["sample_error_rate_wilson_95"],
    ]
    lower = [rate - 100 * interval[0] for rate, interval in zip(rates, intervals)]
    upper = [100 * interval[1] - rate for rate, interval in zip(rates, intervals)]
    bars = axes[1].bar(
        [0, 1],
        rates,
        width=0.56,
        color=["#2A9D8F", "#7E57C2"],
        yerr=np.array([lower, upper]),
        capsize=5,
    )
    axes[1].bar_label(
        bars,
        labels=[
            f"{errors}/89\n({rate:.1f}%)"
            for errors, rate in zip(rater_errors, rates)
        ],
        padding=4,
        fontsize=8.5,
    )
    axes[1].set_xticks([0, 1], ["Rater 1", "Rater 2"])
    axes[1].set_ylabel("Flagged grader errors in stratified sample (%)")
    axes[1].set_title(
        "Task B: grader audit\n"
        f"agreement={100 * grader['agreement']['raw_agreement']:.1f}%, "
        f"kappa={grader['agreement']['cohen_kappa']:.3f}"
    )
    axes[1].grid(axis="y", alpha=0.22)
    axes[1].set_ylim(0, max(upper[index] + rates[index] for index in range(2)) + 3)
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def make_report(
    taxonomy: dict[str, Any],
    grader: dict[str, Any],
    output: Path,
) -> None:
    tax = taxonomy["agreement"]
    grade = grader["agreement"]
    lines = [
        "# Human-evaluation acceptance report",
        "",
        "## Task A: false-consensus taxonomy",
        "",
        f"- Coverage: 134/134 rows for each rater; no duplicates or invalid labels.",
        (
            f"- Exact label agreement: {taxonomy['agreement_count']}/134 "
            f"({100 * tax['raw_agreement']:.2f}%); Cohen's kappa "
            f"{tax['cohen_kappa']:.3f}."
        ),
        (
            f"- Disagreements requiring adjudication: "
            f"{taxonomy['disagreement_count']}."
        ),
        (
            "- Per-rater label counts: "
            + "; ".join(
                f"R{row['rater']}="
                + "/".join(
                    f"{label}:{row['label_counts'][label]}"
                    for label in TAXONOMY_LABELS
                )
                for row in taxonomy["raters"]
            )
            + "."
        ),
        "",
        "## Task B: grader audit",
        "",
        "- Coverage: 89/89 rows for each rater; frozen row identities match the HTML package.",
        (
            f"- Correct/wrong agreement: {100 * grade['raw_agreement']:.2f}%; "
            f"Cohen's kappa {grade['cohen_kappa']:.3f}."
        ),
        (
            f"- Rater-1 flagged {grader['raters'][0]['grader_errors']}/89 "
            f"({100 * grader['raters'][0]['sample_error_rate']:.2f}%); "
            f"Rater-2 flagged {grader['raters'][1]['grader_errors']}/89 "
            f"({100 * grader['raters'][1]['sample_error_rate']:.2f}%)."
        ),
        (
            f"- True-verdict disagreements requiring adjudication: "
            f"{grader['true_verdict_disagreement_count']}."
        ),
        "",
        "**Interpretation boundary:** Task B is deliberately risk-enriched. Raw sample "
        "error rates must not be reported as an unbiased population-wide grader error rate.",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    taxonomy, taxonomy_conflicts = validate_taxonomy(list(args.taxonomy))
    grader, grader_conflicts = validate_grader(list(args.grader))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "taxonomy_disagreements.csv",
        taxonomy_conflicts,
        [
            "problem_id",
            "rater_1_type",
            "rater_2_type",
            "rater_1_confident",
            "rater_2_confident",
            "rater_1_notes",
            "rater_2_notes",
        ],
    )
    write_csv(
        args.output_dir / "grader_disagreements.csv",
        grader_conflicts,
        [
            "row",
            "model",
            "benchmark",
            "problem_id",
            "grader_verdict",
            "rater_1_grader_correct",
            "rater_2_grader_correct",
            "rater_1_true_verdict",
            "rater_2_true_verdict",
            "rater_1_notes",
            "rater_2_notes",
        ],
    )
    summary = {
        "taxonomy": taxonomy,
        "grader": grader,
        "source_files": {
            "taxonomy": [display_path(path) for path in args.taxonomy],
            "grader": [display_path(path) for path in args.grader],
        },
        "annotator_identity_note": (
            "The export schema does not contain annotator names; rater identity "
            "is inferred only from the review_1/review_2 filenames."
        ),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    make_report(taxonomy, grader, args.output_dir / "report.md")
    make_figure(taxonomy, grader, args.figure)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
