#!/usr/bin/env python3
"""CPU replay for the matched Simple@32 versus CertaIndex@32 timelines."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmark.FalseConsensus.governor_v2.grading import robust_answers_equal
from benchmark.FalseConsensus.related_work import common
from benchmark.FalseConsensus.related_work.analyze_false_stops import (
    environment_macro,
    summarize,
)
from benchmark.FalseConsensus.related_work.certaindex_mid import decide_stop

from .run_certaindex32 import DEFAULT_OUTPUT as DEFAULT_CERTAINDEX_ROOT
from .run_certaindex32 import GOV_RESULTS, MODEL_INFO, environments


REPO = Path(__file__).resolve().parents[3]
DEFAULT_ANALYSIS_OUTPUT = (
    REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/analysis"
)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def replay_arm(
    trajectory: Mapping[str, Any],
    probes: Sequence[Mapping[str, Any]],
    *,
    method: str,
) -> dict[str, Any]:
    run_settings = dict(trajectory.get("run_settings", {}))
    ordered = sorted(probes, key=lambda row: int(row["token_position"]))
    decision = decide_stop(
        ordered,
        patience=3,
        answers_equal_fn=common.real_eqaul_group,
        count_not_empty_fn=common.real_count_not_empty,
    )
    consumed = ordered[: int(decision["stop_index"])] if decision else ordered
    full_tokens = int(trajectory["tokens_used"])
    full_correct = bool(trajectory["final_correct"])
    if decision:
        delivered = decision["delivered_answer"]
        main_tokens = int(decision["stop_position"])
        stopped = True
        correct = bool(robust_answers_equal(delivered, trajectory["target"]))
    else:
        stopped = False
        main_tokens = full_tokens
        if bool(trajectory.get("finished_naturally", False)):
            delivered = str(trajectory.get("final_answer", ""))
            correct = full_correct
        else:
            delivered = ""
            correct = False
    probe_out = sum(int(row.get("probe_out_tokens", 0)) for row in consumed)
    probe_prompt = sum(int(row.get("probe_prompt_tokens", 0)) for row in consumed)
    probe_latency = sum(
        float(row.get("probe_latency_seconds", 0.0)) for row in consumed
    )
    total = main_tokens + probe_out
    return {
        "method": method,
        "model": run_settings["model"],
        "dataset": trajectory["dataset"],
        "base_seed": run_settings["base_seed"],
        "problem_id": trajectory["problem_id"],
        "split": trajectory.get("split"),
        "correct": correct,
        "baseline_correct": full_correct,
        "stopped": stopped,
        "delivered_answer": delivered,
        "stop_position": int(decision["stop_position"]) if decision else None,
        "first_consensus_probe_id": int(decision["stop_probe_id"]) if decision else None,
        "n_aux_calls": len(consumed),
        "full_main_tokens": full_tokens,
        "main_tokens_through_stop": main_tokens,
        "probe_out_tokens": probe_out,
        "probe_prompt_tokens": probe_prompt,
        "probe_latency_seconds": probe_latency,
        "all_generated_tokens": total,
        "baseline_all_generated_tokens": full_tokens,
        "main_only_saving_fraction": (
            1.0 - main_tokens / full_tokens if full_tokens else 0.0
        ),
        "all_generated_saving_fraction": (
            1.0 - total / full_tokens if full_tokens else 0.0
        ),
    }


def load_paired_rows(certa_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    simple_rows: list[dict[str, Any]] = []
    certa_rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for model_key in sorted(MODEL_INFO):
        for env in environments(model_key):
            env_name = env["env_name"]
            main_dir = GOV_RESULTS / env_name / "main" / "traj"
            simple_dir = GOV_RESULTS / env_name / "dense_simple32" / "probes"
            certa_dir = certa_root / env_name / "probes"
            main_paths = sorted(main_dir.glob("problem_*.json"))
            for main_path in main_paths:
                trajectory = load_json(main_path)
                key = (
                    trajectory["run_settings"]["model"],
                    trajectory["dataset"],
                    trajectory["run_settings"]["base_seed"],
                    trajectory["problem_id"],
                )
                if key in seen:
                    raise ValueError(f"duplicate trajectory identity: {key}")
                seen.add(key)
                filename = main_path.name
                simple_path = simple_dir / filename
                certa_path = certa_dir / filename
                if not simple_path.exists() or not certa_path.exists():
                    raise FileNotFoundError(
                        f"unpaired probe timeline for {key}: "
                        f"simple={simple_path.exists()} certa={certa_path.exists()}"
                    )
                simple_payload = load_json(simple_path)
                certa_payload = load_json(certa_path)
                simple_rows.append(
                    replay_arm(
                        trajectory,
                        simple_payload["probes"],
                        method="simple32_consensus3",
                    )
                )
                certa_rows.append(
                    replay_arm(
                        trajectory,
                        certa_payload["probes"],
                        method="certaindex32_consensus3",
                    )
                )
    if len(simple_rows) != 3420 or len(certa_rows) != 3420:
        raise ValueError(
            f"expected 3420 paired trajectories per arm, got "
            f"{len(simple_rows)} and {len(certa_rows)}"
        )
    return simple_rows, certa_rows


def pair_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row["model"],
        row["dataset"],
        row["base_seed"],
        row["problem_id"],
    )


def paired_diagnostics(
    simple_rows: Sequence[Mapping[str, Any]],
    certa_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    simple = {pair_key(row): row for row in simple_rows}
    certa = {pair_key(row): row for row in certa_rows}
    if set(simple) != set(certa):
        raise ValueError("Simple/CertaIndex paired keys differ")
    counts: dict[str, int] = defaultdict(int)
    delays: list[int] = []
    for key in sorted(simple):
        left, right = simple[key], certa[key]
        left_stop, right_stop = bool(left["stopped"]), bool(right["stopped"])
        if left_stop and right_stop:
            delta = int(right["stop_position"]) - int(left["stop_position"])
            delays.append(delta)
            counts["certa_later"] += int(delta > 0)
            counts["certa_earlier"] += int(delta < 0)
            counts["same_position"] += int(delta == 0)
        elif left_stop and not right_stop:
            counts["simple_only_stop"] += 1
        elif right_stop and not left_stop:
            counts["certa_only_stop"] += 1
        else:
            counts["neither_stop"] += 1
        simple_harm = (
            left_stop and bool(left["baseline_correct"]) and not bool(left["correct"])
        )
        certa_harm = (
            right_stop and bool(right["baseline_correct"]) and not bool(right["correct"])
        )
        counts["simple_harms_protected"] += int(simple_harm and not certa_harm)
        counts["new_certa_harms"] += int(certa_harm and not simple_harm)
        counts["certa_corrects_simple"] += int(
            not bool(left["correct"]) and bool(right["correct"])
        )
        counts["certa_breaks_simple"] += int(
            bool(left["correct"]) and not bool(right["correct"])
        )
    return {
        **dict(counts),
        "both_stop": len(delays),
        "mean_delay_tokens_when_both_stop": (
            sum(delays) / len(delays) if delays else None
        ),
        "median_delay_tokens_when_both_stop": (
            statistics.median(delays) if delays else None
        ),
    }


def arm_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stopped_positions = [
        int(row["stop_position"])
        for row in rows
        if row.get("stop_position") is not None
    ]
    probe_prompt_tokens = sum(int(row["probe_prompt_tokens"]) for row in rows)
    probe_latency_seconds = sum(float(row["probe_latency_seconds"]) for row in rows)
    return {
        "pooled": summarize(rows),
        "environment_macro": environment_macro(rows),
        "timing": {
            "mean_first_consensus_position": (
                sum(stopped_positions) / len(stopped_positions)
                if stopped_positions
                else None
            ),
            "median_first_consensus_position": (
                statistics.median(stopped_positions)
                if stopped_positions
                else None
            ),
        },
        "auxiliary_cost": {
            "probe_prompt_tokens": probe_prompt_tokens,
            "probe_latency_seconds": probe_latency_seconds,
            "mean_probe_prompt_tokens_per_trajectory": (
                probe_prompt_tokens / len(rows)
            ),
            "mean_probe_latency_seconds_per_trajectory": (
                probe_latency_seconds / len(rows)
            ),
        },
    }


def fmt_optional(value: Any, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}"


def write_outputs(
    simple_rows: Sequence[Mapping[str, Any]],
    certa_rows: Sequence[Mapping[str, Any]],
    output: Path,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "probe-prompt-timing-analysis-1",
        "scope": {
            "paired_trajectories": len(simple_rows),
            "split_reporting": "pooled; no split-specific table",
        },
        "arms": {
            "simple32": arm_summary(simple_rows),
            "certaindex32": arm_summary(certa_rows),
        },
        "paired": paired_diagnostics(simple_rows, certa_rows),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [*simple_rows, *certa_rows]
    fields = sorted({key for row in rows for key in row})
    with (output / "per_problem.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Simple@32 versus CertaIndex@32 prompt-timing ablation",
        "",
        "All 3,420 trajectories are pooled across split labels. Both arms use the "
        "same interval-64, cap-32, first-three-certain-equivalent consensus rule.",
        "",
        "| Arm | Accuracy delta | Main saving | Output saving | Probe tax | Stop rate | Mean consensus token | Wrong / stop | Harm | Rescue |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, key in (
        ("Simple@32", "simple32"),
        ("CertaIndex@32", "certaindex32"),
    ):
        data = summary["arms"][key]["pooled"]
        timing = summary["arms"][key]["timing"]
        lines.append(
            f"| {label} | {data['accuracy_delta_pp']:+.2f} pp | "
            f"{100*data['main_only_token_saving']:.2f}% | "
            f"{100*data['all_generated_token_saving']:.2f}% | "
            f"{100*data['probe_output_tax']:.2f}% | "
            f"{100*data['stop_rate']:.2f}% | "
            f"{fmt_optional(timing['mean_first_consensus_position'])} | "
            f"{data['false_stops']}/{data['stopped']} "
            f"({100*data['false_stop_rate_given_stop']:.2f}%) | "
            f"{data['harm']} | {data['rescue']} |"
        )
    lines += [
        "",
        "## Equal-environment macro robustness",
        "",
        "| Arm | Accuracy delta | Output saving | Stop rate | Wrong / stop |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in (
        ("Simple@32", "simple32"),
        ("CertaIndex@32", "certaindex32"),
    ):
        data = summary["arms"][key]["environment_macro"]
        lines.append(
            f"| {label} | {data['accuracy_delta_pp']:+.2f} pp | "
            f"{100*data['all_generated_token_saving']:.2f}% | "
            f"{100*data['stop_rate']:.2f}% | "
            f"{100*data['false_stop_rate_given_stop']:.2f}% |"
        )
    paired = summary["paired"]
    lines += [
        "",
        "## Paired timing and outcome changes",
        "",
        f"- CertaIndex later / earlier / same when both stop: "
        f"{paired.get('certa_later', 0)} / {paired.get('certa_earlier', 0)} / "
        f"{paired.get('same_position', 0)}.",
        f"- Simple-only / CertaIndex-only / neither stop: "
        f"{paired.get('simple_only_stop', 0)} / {paired.get('certa_only_stop', 0)} / "
        f"{paired.get('neither_stop', 0)}.",
        f"- Mean CertaIndex delay when both stop: "
        f"{fmt_optional(paired.get('mean_delay_tokens_when_both_stop'))} tokens; "
        f"median: "
        f"{fmt_optional(paired.get('median_delay_tokens_when_both_stop'))} tokens.",
        f"- Simple harms protected / new CertaIndex harms: "
        f"{paired.get('simple_harms_protected', 0)} / "
        f"{paired.get('new_certa_harms', 0)}.",
        f"- CertaIndex corrects / breaks Simple delivery: "
        f"{paired.get('certa_corrects_simple', 0)} / "
        f"{paired.get('certa_breaks_simple', 0)}.",
        "",
        "## Auxiliary costs (not included in primary output-token saving)",
        "",
        "| Arm | Probe prompt tokens | Mean prompt tokens / trajectory | Probe latency | Mean latency / trajectory | Harm / rescue | Haldane ratio |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, key in (
        ("Simple@32", "simple32"),
        ("CertaIndex@32", "certaindex32"),
    ):
        data = summary["arms"][key]["pooled"]
        auxiliary = summary["arms"][key]["auxiliary_cost"]
        raw_ratio = data["harm_rescue_ratio"]
        raw_text = "inf" if math.isinf(raw_ratio) else f"{raw_ratio:.2f}"
        lines.append(
            f"| {label} | {auxiliary['probe_prompt_tokens']:,} | "
            f"{auxiliary['mean_probe_prompt_tokens_per_trajectory']:.1f} | "
            f"{auxiliary['probe_latency_seconds']:.1f}s | "
            f"{auxiliary['mean_probe_latency_seconds_per_trajectory']:.3f}s | "
            f"{raw_text} | {data['harm_rescue_haldane_ratio']:.2f} |"
        )
    lines += [
        "",
        "Primary cost counts generated output tokens only: main-through-stop plus "
        "consumed probe outputs. Probe prompt/prefill tokens and wall time are "
        "reported in per-problem artifacts but excluded from primary saving.",
        "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--certa-root", type=Path, default=DEFAULT_CERTAINDEX_ROOT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_ANALYSIS_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    simple_rows, certa_rows = load_paired_rows(args.certa_root)
    write_outputs(simple_rows, certa_rows, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
