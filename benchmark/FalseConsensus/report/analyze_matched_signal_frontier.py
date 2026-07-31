#!/usr/bin/env python3
"""Signal-only comparison on a strictly matched DEER/TJE Wait bank.

Every operating point uses the same DEER trial answer, validity gate,
direct-submit action, trigger position, and generated-token accounting.  TJE
confidence is joined only at an identical trajectory identity and exact
``trigger_char_position``; unmatched events are never interpolated.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from benchmark.FalseConsensus.governor_v2.replay_rules import (
    answers_equal,
    load_split_map,
    normalize_answer,
)
from benchmark.FalseConsensus.related_work import model_map
from benchmark.FalseConsensus.related_work.tje import TJE_LABEL_NAMES


REPO = Path(__file__).resolve().parents[3]
DEER = REPO / "benchmark/FalseConsensus/results/related_work/deer_confidence_bank_cap30"
TJE = REPO / "benchmark/FalseConsensus/results/related_work/tje_threshold_readout_bank_top1_6"
SPLITS = REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
RESULTS = REPO / "benchmark/FalseConsensus/results/related_work/matched_signal_cpu"
FIGURES = REPO / "benchmark/FalseConsensus/report/figures"
SCOPE_PREFIX = {"full": "development", "test": "confirmation"}
DEER_THRESHOLDS = (
    0.90, 0.925, 0.95, 0.96, 0.97, 0.975, 0.98, 0.985, 0.99,
    0.9925, 0.995, 0.996, 0.997, 0.998, 0.999, 0.9995,
    0.9999, 0.99995, 0.99999, 0.999995, 0.999999, 0.9999995,
    0.9999999, 0.99999999,
)
CONSENSUS_WINDOWS = tuple(range(2, 31))
TJE_TOP_K = tuple(range(1, 7))


def iter_gzip(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=250_000)
def equivalent(left: str, right: str) -> bool:
    if left == right:
        return True
    return bool(answers_equal(left, right))


def tje_by_problem(path: Path) -> dict[int, dict[str, Any]]:
    return {int(row["problem_id"]): row for row in iter_gzip(path)}


def load_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    split_map = load_split_map(SPLITS)
    rows: list[dict[str, Any]] = []
    audit = defaultdict(int)
    source_hashes: dict[str, str] = {}
    for scope in ("full", "test"):
        for deer_path in sorted((DEER / scope).glob("*/trials.jsonl.gz")):
            environment = deer_path.parent.name
            tje_path = TJE / scope / environment / "readouts.jsonl.gz"
            if not tje_path.exists():
                raise FileNotFoundError(f"missing matched TJE archive: {tje_path}")
            source_hashes[str(deer_path.relative_to(REPO))] = sha256(deer_path)
            source_hashes[str(tje_path.relative_to(REPO))] = sha256(tje_path)
            tje_rows = tje_by_problem(tje_path)
            model_key, benchmark, seed_text = environment.split("__")
            seed = int(seed_text.removeprefix("seed_"))
            info = model_map.model_info(model_key)
            main_root = (
                REPO
                / "benchmark/FalseConsensus/results/governor_v2"
                / f"{SCOPE_PREFIX[scope]}__{info['slug']}__{benchmark}__seed_{seed}"
                / "main/traj"
            )
            for deer_row in iter_gzip(deer_path):
                problem_id = int(deer_row["problem_id"])
                tje_row = tje_rows.get(problem_id)
                if tje_row is None:
                    raise ValueError(f"TJE identity missing: {environment}/{problem_id}")
                trajectory = json.loads(
                    (main_root / f"problem_{problem_id}.json").read_text(encoding="utf-8")
                )
                label_at = {
                    int(trigger["trigger_char_position"]): str(trigger["confidence_label"])
                    for trigger in tje_row.get("confidence_triggers", [])
                    if trigger.get("trigger_type") == "wait"
                }
                common: list[dict[str, Any]] = []
                require_close = bool(deer_row.get("require_think_close"))
                for trial in sorted(deer_row.get("trials", []), key=lambda x: int(x["candidate_id"])):
                    audit["deer_trials"] += 1
                    char_position = int(trial["trigger_char_position"])
                    if char_position not in label_at:
                        continue
                    audit["exact_trigger_matches"] += 1
                    answer = normalize_answer(trial.get("trial_answer"))
                    valid = bool(answer) and (
                        not require_close or bool(trial.get("think_close_emitted"))
                    )
                    common.append(
                        {
                            "candidate_id": int(trial["candidate_id"]),
                            "token_position": int(trial["token_position"]),
                            "trigger_char_position": char_position,
                            "trial_answer": answer,
                            "trial_valid": valid,
                            "trial_out_tokens": int(trial.get("trial_out_tokens", 0)),
                            "deer_confidence": float(trial["confidence"]),
                            "tje_label": label_at[char_position],
                        }
                    )
                audit["trajectories"] += 1
                audit["trajectories_with_match"] += bool(common)
                split = "test" if scope == "test" else split_map[(benchmark, problem_id)]
                baseline_answer = normalize_answer(trajectory.get("final_answer"))
                baseline_correct = bool(
                    trajectory.get("finished_naturally")
                    and answers_equal(baseline_answer, trajectory["target"])
                )
                rows.append(
                    {
                        "scope": scope,
                        "split": split,
                        "model_key": model_key,
                        "model": str(deer_row["model"]),
                        "benchmark": benchmark,
                        "seed": seed,
                        "problem_id": problem_id,
                        "target": normalize_answer(trajectory["target"]),
                        "baseline_correct": baseline_correct,
                        "baseline_tokens": int(deer_row["main_token_count_recorded"]),
                        "common_trials": common,
                    }
                )
    if len(rows) != 3420:
        raise ValueError(f"expected 3420 trajectories, found {len(rows)}")
    audit["tje_wait_triggers"] = sum(
        1
        for scope in ("full", "test")
        for path in sorted((TJE / scope).glob("*/readouts.jsonl.gz"))
        for row in iter_gzip(path)
        for trigger in row.get("confidence_triggers", [])
        if trigger.get("trigger_type") == "wait"
    )
    audit["trial_match_fraction"] = (
        audit["exact_trigger_matches"] / audit["deer_trials"]
        if audit["deer_trials"] else 0.0
    )
    audit["trajectory_match_fraction"] = audit["trajectories_with_match"] / len(rows)
    audit["join_key"] = [
        "model", "benchmark", "seed", "problem_id", "trigger_char_position"
    ]
    audit["unmatched_policy"] = "exclude trigger; never interpolate"
    audit["source_sha256"] = source_hashes
    return rows, dict(audit)


def add_run_lengths(row: dict[str, Any]) -> None:
    streak = 0
    previous = ""
    for trial in row["common_trials"]:
        answer = str(trial["trial_answer"])
        if not trial["trial_valid"]:
            streak, previous = 0, ""
        elif previous and equivalent(answer, previous):
            streak += 1
        else:
            streak, previous = 1, answer
        trial["equivalent_run_length"] = streak


def first_accept(
    row: Mapping[str, Any], family: str, parameter: float | int
) -> tuple[dict[str, Any] | None, int, int]:
    consumed = 0
    attempts = 0
    for trial in row["common_trials"]:
        attempts += 1
        consumed += int(trial["trial_out_tokens"])
        if not trial["trial_valid"]:
            continue
        accepted = False
        if family == "deer_confidence":
            accepted = float(trial["deer_confidence"]) > float(parameter)
        elif family == "answer_persistence":
            accepted = int(trial["equivalent_run_length"]) >= int(parameter)
        elif family == "tje_confidence":
            label = str(trial["tje_label"])
            accepted = TJE_LABEL_NAMES.index(label) < int(parameter)
        else:
            raise ValueError(family)
        if accepted:
            return dict(trial), consumed, attempts
    return None, consumed, attempts


def evaluate(row: Mapping[str, Any], family: str, parameter: float | int) -> dict[str, Any]:
    accepted, probe_tokens, attempts = first_accept(row, family, parameter)
    if accepted is None:
        method_correct = bool(row["baseline_correct"])
        method_tokens = int(row["baseline_tokens"]) + probe_tokens
        stopped = False
    else:
        method_correct = bool(answers_equal(accepted["trial_answer"], row["target"]))
        method_tokens = int(accepted["token_position"]) + probe_tokens
        stopped = True
    return {
        **{key: row[key] for key in (
            "split", "model_key", "model", "benchmark", "seed", "problem_id",
            "baseline_correct", "baseline_tokens",
        )},
        "family": family,
        "parameter": parameter,
        "method_correct": method_correct,
        "method_tokens": method_tokens,
        "stopped": stopped,
        "stop_correct": method_correct if stopped else None,
        "harm": bool(row["baseline_correct"] and not method_correct),
        "rescue": bool(not row["baseline_correct"] and method_correct),
        "attempts": attempts,
    }


def summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(records)
    stopped = [row for row in records if row["stopped"]]
    baseline_correct = sum(bool(row["baseline_correct"]) for row in records)
    correct_count = sum(bool(row["method_correct"]) for row in records)
    baseline_tokens = sum(int(row["baseline_tokens"]) for row in records)
    tokens = sum(int(row["method_tokens"]) for row in records)
    harms = sum(bool(row["harm"]) for row in records)
    rescues = sum(bool(row["rescue"]) for row in records)
    stop_correct = sum(bool(row["stop_correct"]) for row in stopped)
    return {
        "n": n,
        "accuracy_pct": 100 * correct_count / n,
        "baseline_accuracy_pct": 100 * baseline_correct / n,
        "accuracy_drop_pp": 100 * (baseline_correct - correct_count) / n,
        "all_generated_token_saving_pct": (
            100 * (baseline_tokens - tokens) / baseline_tokens if baseline_tokens else 0.0
        ),
        "stop_rate_pct": 100 * len(stopped) / n,
        "stop_accuracy_pct": 100 * stop_correct / len(stopped) if stopped else math.nan,
        "false_stop_ratio_pct": (
            100 * (len(stopped) - stop_correct) / len(stopped) if stopped else math.nan
        ),
        "harm_count": harms,
        "rescue_count": rescues,
        "harm_rescue_ratio": harms / rescues if rescues else math.inf,
        "avg_attempts": sum(int(row["attempts"]) for row in records) / n,
        "total_baseline_tokens": baseline_tokens,
        "total_method_tokens": tokens,
    }


def group(records: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        groups[tuple(row[key] for key in keys)].append(row)
    return [
        {**dict(zip(keys, key)), **summarize(values)}
        for key, values in sorted(groups.items(), key=lambda item: tuple(map(str, item[0])))
    ]


def macro(environment_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = (
        "accuracy_pct", "baseline_accuracy_pct", "accuracy_drop_pp",
        "all_generated_token_saving_pct", "stop_rate_pct", "stop_accuracy_pct",
        "false_stop_ratio_pct", "avg_attempts",
    )
    output: dict[str, Any] = {"environment_count": len(environment_rows)}
    for field in fields:
        values = [float(row[field]) for row in environment_rows if math.isfinite(float(row[field]))]
        output[field] = math.fsum(values) / len(values) if values else math.nan
    harms = math.fsum(float(row["harm_count"]) / int(row["n"]) for row in environment_rows)
    rescues = math.fsum(float(row["rescue_count"]) / int(row["n"]) for row in environment_rows)
    output["harm_rate_pct"] = 100 * harms / len(environment_rows)
    output["rescue_rate_pct"] = 100 * rescues / len(environment_rows)
    output["harm_rescue_ratio"] = harms / rescues if rescues else math.inf
    return output


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


def analyze(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for row in rows:
        add_run_lengths(row)
    settings = (
        [("deer_confidence", value) for value in DEER_THRESHOLDS]
        + [("answer_persistence", value) for value in CONSENSUS_WINDOWS]
        + [("tje_confidence", value) for value in TJE_TOP_K]
    )
    frontier: list[dict[str, Any]] = []
    grouped_output: list[dict[str, Any]] = []
    for family, parameter in settings:
        evaluated = [evaluate(row, family, parameter) for row in rows]
        for split in ("train", "dev", "test"):
            subset = [row for row in evaluated if row["split"] == split]
            environments = group(subset, ("model_key", "benchmark", "seed"))
            pooled = summarize(subset)
            macro_summary = macro(environments)
            frontier.extend(
                [
                    {"split": split, "aggregation": "pooled", "family": family,
                     "parameter": parameter, **pooled},
                    {"split": split, "aggregation": "environment_macro", "family": family,
                     "parameter": parameter, **macro_summary},
                ]
            )
            for keys, label in (
                (("model_key",), "per_model"),
                (("benchmark",), "per_benchmark"),
                (("seed",), "per_seed"),
                (("model_key", "benchmark", "seed"), "per_environment"),
            ):
                for summary in group(subset, keys):
                    grouped_output.append(
                        {"split": split, "aggregation": label, "family": family,
                         "parameter": parameter, **summary}
                    )
    return frontier, grouped_output


def make_figure(frontier: Sequence[Mapping[str, Any]]) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    colors = {
        "deer_confidence": "#009E73",
        "answer_persistence": "#2878B5",
        "tje_confidence": "#E66101",
    }
    labels = {
        "deer_confidence": "DEER confidence",
        "answer_persistence": "Answer persistence",
        "tje_confidence": "TJE confidence (matched proxy)",
    }
    fig, axes = plt.subplots(2, 3, figsize=(14.2, 8.0), sharex=False, sharey=False)
    for col, split in enumerate(("train", "dev", "test")):
        for row_index, aggregation in enumerate(("pooled", "environment_macro")):
            ax = axes[row_index, col]
            for family in colors:
                points = [
                    row for row in frontier
                    if row["split"] == split
                    and row["aggregation"] == aggregation
                    and row["family"] == family
                ]
                points.sort(key=lambda row: float(row["accuracy_drop_pp"]))
                ax.plot(
                    [float(row["accuracy_drop_pp"]) for row in points],
                    [float(row["all_generated_token_saving_pct"]) for row in points],
                    marker="o", markersize=3, linewidth=1.5,
                    color=colors[family], label=labels[family], alpha=0.88,
                )
            ax.axvline(0, color="#6B7280", linewidth=0.8)
            ax.axhline(0, color="#6B7280", linewidth=0.8)
            ax.grid(alpha=0.22)
            ax.set_title(f"{split.title()} — {aggregation.replace('_', ' ')}")
            ax.set_xlabel("Accuracy drop vs full (pp; lower is better)")
            if col == 0:
                ax.set_ylabel("All-generated token saving (%)")
    axes[0, 0].legend(frameon=False, fontsize=8, loc="best")
    fig.suptitle("Strictly matched stopping-signal frontier", fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    for suffix in ("png", "pdf"):
        fig.savefig(
            FIGURES / f"matched_signal_frontier.{suffix}", dpi=220, bbox_inches="tight"
        )
    plt.close(fig)


def report(frontier: Sequence[Mapping[str, Any]], audit: Mapping[str, Any]) -> str:
    lines = [
        "# Matched stopping-signal CPU contrast",
        "",
        "This is a signal-only counterfactual, not a faithful end-to-end TJE run. "
        "All policies directly submit the same DEER trial answer and are charged "
        "the same main-prefix plus DEER trial-output tokens.",
        "",
        "## Exact matching",
        "",
        f"- Trajectories: {audit['trajectories']:,}",
        f"- DEER trials: {audit['deer_trials']:,}",
        f"- Exact DEER-Wait/TJE-Wait matches: {audit['exact_trigger_matches']:,} "
        f"({100 * audit['trial_match_fraction']:.2f}%)",
        f"- Trajectories with at least one match: {audit['trajectories_with_match']:,} "
        f"({100 * audit['trajectory_match_fraction']:.2f}%)",
        "- Join is exact on trajectory identity plus trigger_char_position; unmatched "
        "events are excluded and never interpolated.",
        "",
        "## Representative Test operating points",
        "",
        "| Aggregation | Signal | Parameter | Accuracy drop | Saving | Stop accuracy | False-stop | Harm/rescue | Coverage |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    representatives = {
        "deer_confidence": {0.95, 0.99, 0.995, 0.999},
        "answer_persistence": {3, 5, 8, 12, 20, 30},
        "tje_confidence": {1, 2, 3},
    }
    for row in frontier:
        if row["split"] != "test" or row["aggregation"] not in {"pooled", "environment_macro"}:
            continue
        if row["parameter"] not in representatives[row["family"]]:
            continue
        lines.append(
            f"| {row['aggregation']} | {row['family']} | {row['parameter']} | "
            f"{float(row['accuracy_drop_pp']):.2f} pp | "
            f"{float(row['all_generated_token_saving_pct']):.2f}% | "
            f"{float(row['stop_accuracy_pct']):.2f}% | "
            f"{float(row['false_stop_ratio_pct']):.2f}% | "
            f"{float(row['harm_rescue_ratio']):.2f} | "
            f"{float(row['stop_rate_pct']):.2f}% |"
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- TJE labels are real model outputs but only exact Wait-position matches "
            "are retained; this reduces opportunity coverage.",
            "- TJE confidence-query output tokens are intentionally not charged because "
            "the experiment holds action/cost fixed to isolate the stopping signal.",
            "- The comparison therefore supports a signal-level claim only; it does not "
            "replace the separately reported faithful/frozen baseline costs.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "MPLCONFIGDIR=/tmp/governor-mpl python -m "
            "benchmark.FalseConsensus.report.analyze_matched_signal_frontier",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows, audit = load_rows()
    frontier, grouped = analyze(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_csv(RESULTS / "frontier.csv", frontier)
    write_csv(RESULTS / "grouped_metrics.csv", grouped)
    manifest = {
        "schema_version": "matched-stopping-signal-cpu-1",
        "scope": "2 models x 3 benchmarks x seeds 42-47; train/dev/test",
        "deer_thresholds": list(DEER_THRESHOLDS),
        "consensus_windows": list(CONSENSUS_WINDOWS),
        "tje_top_k": list(TJE_TOP_K),
        "cost_numerator": "main tokens through matched stop + cumulative DEER trial output tokens",
        "cost_denominator": "observed frozen full main output tokens",
        "tje_query_tokens_charged": False,
        "audit": audit,
        "split_manifest_sha256": sha256(SPLITS),
    }
    (RESULTS / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (RESULTS / "report.md").write_text(report(frontier, audit), encoding="utf-8")
    make_figure(frontier)
    print(json.dumps({
        "trajectories": len(rows),
        "frontier_rows": len(frontier),
        "exact_matches": audit["exact_trigger_matches"],
        "match_fraction": audit["trial_match_fraction"],
    }, indent=2))


if __name__ == "__main__":
    main()
