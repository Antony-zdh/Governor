#!/usr/bin/env python3
"""CPU-only false-stop audit for existing related-work replay artifacts.

The analysis intentionally pools every available replay row across split labels.
It never selects a threshold or rewrites a replay.  Split is retained only in
the row identity and is not emitted as a reporting dimension.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
DEFAULT_REPLAY_ROOT = (
    REPO / "benchmark/FalseConsensus/results/related_work/full/_replay"
)
DEFAULT_OUTPUT = (
    REPO / "benchmark/FalseConsensus/results/related_work/false_stop_audit"
)
DEFAULT_METHODS = ("deer_frozen", "tje_frozen")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            yield row


def load_replay_rows(
    replay_root: Path,
    methods: Sequence[str] = DEFAULT_METHODS,
) -> list[dict[str, Any]]:
    wanted = set(methods)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for path in sorted(replay_root.glob("*/replay_rows.jsonl")):
        for row in read_jsonl(path):
            method = str(row.get("method", ""))
            if method not in wanted:
                continue
            key = (
                method,
                row.get("model"),
                row.get("dataset"),
                row.get("base_seed"),
                row.get("problem_id"),
            )
            if key in seen:
                raise ValueError(f"duplicate replay identity: {key}")
            seen.add(key)
            for field in (
                "model",
                "dataset",
                "base_seed",
                "problem_id",
                "correct",
                "baseline_correct",
                "stopped",
                "all_generated_tokens",
                "baseline_all_generated_tokens",
            ):
                if row.get(field) is None:
                    raise ValueError(f"{path}: missing {field} for {key}")
            rows.append(row)
    missing = wanted - {str(row["method"]) for row in rows}
    if missing:
        raise ValueError(f"no replay rows found for methods: {sorted(missing)}")
    return rows


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty rows")
    stopped_rows = [row for row in rows if bool(row["stopped"])]
    false_stops = [row for row in stopped_rows if not bool(row["correct"])]
    harm = [
        row
        for row in stopped_rows
        if bool(row["baseline_correct"]) and not bool(row["correct"])
    ]
    rescue = [
        row
        for row in stopped_rows
        if not bool(row["baseline_correct"]) and bool(row["correct"])
    ]
    both_correct = [
        row
        for row in stopped_rows
        if bool(row["baseline_correct"]) and bool(row["correct"])
    ]
    both_wrong = [
        row
        for row in stopped_rows
        if not bool(row["baseline_correct"]) and not bool(row["correct"])
    ]
    n = len(rows)
    n_stop = len(stopped_rows)
    correct = sum(bool(row["correct"]) for row in rows)
    baseline_correct = sum(bool(row["baseline_correct"]) for row in rows)
    method_tokens = sum(int(row["all_generated_tokens"]) for row in rows)
    main_tokens = sum(
        int(row.get("main_tokens_through_stop", row["all_generated_tokens"]))
        for row in rows
    )
    baseline_tokens = sum(int(row["baseline_all_generated_tokens"]) for row in rows)
    raw_ratio = len(harm) / len(rescue) if rescue else math.inf
    main_saving = 1.0 - main_tokens / baseline_tokens if baseline_tokens else 0.0
    output_saving = (
        1.0 - method_tokens / baseline_tokens if baseline_tokens else 0.0
    )
    return {
        "n": n,
        "stopped": n_stop,
        "stop_rate": n_stop / n,
        "accuracy": correct / n,
        "baseline_accuracy": baseline_correct / n,
        "accuracy_delta_pp": 100.0 * (correct - baseline_correct) / n,
        "main_only_token_saving": main_saving,
        "all_generated_token_saving": output_saving,
        "probe_output_tax": main_saving - output_saving,
        "false_stops": len(false_stops),
        "false_stop_rate_given_stop": len(false_stops) / n_stop if n_stop else 0.0,
        "harm": len(harm),
        "harm_rate_given_stop": len(harm) / n_stop if n_stop else 0.0,
        "rescue": len(rescue),
        "rescue_rate_given_stop": len(rescue) / n_stop if n_stop else 0.0,
        "harm_rescue_ratio": raw_ratio,
        "harm_rescue_haldane_ratio": (len(harm) + 0.5) / (len(rescue) + 0.5),
        "both_correct": len(both_correct),
        "both_wrong": len(both_wrong),
    }


def environment_macro(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[
            (
                row["model"],
                row["dataset"],
                row["base_seed"],
            )
        ].append(row)
    summaries = [summarize(group) for group in groups.values()]
    fields = (
        "stop_rate",
        "accuracy",
        "baseline_accuracy",
        "accuracy_delta_pp",
        "all_generated_token_saving",
        "false_stop_rate_given_stop",
        "harm_rate_given_stop",
        "rescue_rate_given_stop",
    )
    return {
        field: sum(float(summary[field]) for summary in summaries) / len(summaries)
        for field in fields
    } | {"n_environments": len(summaries)}


def analyze(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    methods = sorted({str(row["method"]) for row in rows})
    result: dict[str, Any] = {
        "schema_version": "related-work-false-stop-audit-1",
        "scope": {
            "split_policy": "pool every available replay row; do not report by split",
            "methods": methods,
            "rows": len(rows),
        },
        "methods": {},
    }
    for method in methods:
        method_rows = [row for row in rows if row["method"] == method]
        by_model: dict[str, Any] = {}
        for model in sorted({str(row["model"]) for row in method_rows}):
            model_rows = [row for row in method_rows if row["model"] == model]
            by_model[model] = {
                "pooled": summarize(model_rows),
                "environment_macro": environment_macro(model_rows),
            }
        result["methods"][method] = {
            "pooled": summarize(method_rows),
            "environment_macro": environment_macro(method_rows),
            "by_model": by_model,
        }
    return result


def fmt_pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def fmt_ratio(value: float) -> str:
    return "inf" if math.isinf(value) else f"{value:.2f}"


def write_report(result: Mapping[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    csv_rows: list[dict[str, Any]] = []
    lines = [
        "# Related-work false-stop audit",
        "",
        "All available replay rows are pooled across split labels. "
        "No threshold is selected and no split-specific result is reported.",
        "",
        "## Overall pooled outcomes",
        "",
        "| Method | N | Stop | Accuracy delta | Token saving | Wrong / stop | Harm | Rescue | Harm / rescue |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, payload in result["methods"].items():
        summary = payload["pooled"]
        lines.append(
            f"| {method} | {summary['n']:,} | {fmt_pct(summary['stop_rate'])} | "
            f"{summary['accuracy_delta_pp']:+.2f} pp | "
            f"{fmt_pct(summary['all_generated_token_saving'])} | "
            f"{summary['false_stops']}/{summary['stopped']} "
            f"({fmt_pct(summary['false_stop_rate_given_stop'])}) | "
            f"{summary['harm']} | {summary['rescue']} | "
            f"{fmt_ratio(summary['harm_rescue_ratio'])} |"
        )
        csv_rows.append({"method": method, "view": "overall", **summary})
    lines += [
        "",
        "Harm means full generation is correct but the stopped delivery is wrong. "
        "Rescue means full generation is wrong but the stopped delivery is correct. "
        "`Wrong / stop` is a reference-answer false-stop rate and includes persistent "
        "wrong cases where full generation is also wrong.",
        "",
        "## Model diagnostics",
        "",
        "| Method | Model | N | Stop | Accuracy delta | Token saving | Wrong / stop | Harm | Rescue |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, payload in result["methods"].items():
        for model, model_payload in payload["by_model"].items():
            summary = model_payload["pooled"]
            lines.append(
                f"| {method} | {model} | {summary['n']:,} | "
                f"{fmt_pct(summary['stop_rate'])} | "
                f"{summary['accuracy_delta_pp']:+.2f} pp | "
                f"{fmt_pct(summary['all_generated_token_saving'])} | "
                f"{fmt_pct(summary['false_stop_rate_given_stop'])} | "
                f"{summary['harm']} | {summary['rescue']} |"
            )
            csv_rows.append(
                {"method": method, "view": f"model:{model}", **summary}
            )
    lines += [
        "",
        "## Interpretation boundary",
        "",
        "- These are false stops, not false consensus: DEER and TJE do not require repeated answer agreement.",
        "- The audit uses the existing frozen-trajectory adaptations and therefore does not claim end-to-end paper fidelity.",
        "- The primary table is problem-pooled; `summary.json` also stores equal-weight environment-macro rates.",
        "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    fieldnames = sorted({key for row in csv_rows for key in row})
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--methods", nargs="+", default=list(DEFAULT_METHODS))
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_replay_rows(args.replay_root, args.methods)
    result = analyze(rows)
    if args.check_only:
        print(
            json.dumps(
                {
                    "rows": len(rows),
                    "methods": sorted(result["methods"]),
                    "status": "ready",
                },
                sort_keys=True,
            )
        )
        return 0
    write_report(result, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
