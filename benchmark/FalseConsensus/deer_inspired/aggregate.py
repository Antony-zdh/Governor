"""Audit and aggregate the single-seed online DEER experiment."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Optional, Sequence

from benchmark.FalseConsensus.related_work.common import atomic_write_csv

from .common import atomic_write_json, load_json, percentile
from .online_controller import METHOD_PROPOSED, METHOD_REFERENCE


MODELS = {
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai-deepseek-r1-distill-qwen-7b",
    "Qwen/Qwen3-8B": "qwen-qwen3-8b",
}
BENCHMARKS = ("math500", "amc23", "aime24")
METHODS = (METHOD_PROPOSED, METHOD_REFERENCE)


def discover(results_root: Path) -> list[dict[str, Any]]:
    rows = []
    for method in METHODS:
        for path in sorted((results_root / method).glob("*__*__seed_42/problems/problem_*.json")):
            payload = load_json(path)
            accounting = payload["accounting"]
            rows.append(
                {
                    "method": payload["method"],
                    "schema_version": payload["schema_version"],
                    "protocol_version": payload["protocol_version"],
                    "config_hash": payload["config_hash"],
                    "model": payload["model"],
                    "model_revision": payload["model_revision"],
                    "benchmark": payload["benchmark"],
                    "seed": payload["base_seed"],
                    "problem_id": payload["problem_id"],
                    "split": payload["split"],
                    "correct": int(bool(payload["correct"])),
                    "terminal_state": payload["terminal_state"],
                    "capped": int(bool(payload["capped"])),
                    "delivered_answer": payload["delivered_answer"],
                    "native_main_tokens": accounting[
                        "native_committed_main_output_tokens"
                    ],
                    "all_generated_tokens": accounting["all_generated_tokens"],
                    "all_prompt_tokens": accounting["all_prompt_tokens"],
                    "stage1_tokens": accounting["stage1_trial_output_tokens"],
                    "verification_tokens": accounting["verification_output_tokens"],
                    "stage2_tokens": accounting["stage2_trial_output_tokens"],
                    "readout_tokens": accounting["reference_readout_output_tokens"],
                    "stage1_attempts": sum(
                        int(event.get("probed", False))
                        for event in payload["wait_events"]
                    ),
                    "waits_observed": len(payload["wait_events"]),
                    "branches": len(payload["branches"]),
                    "branch_commits": sum(
                        branch.get("outcome") == "commit"
                        for branch in payload["branches"]
                    ),
                    "fast_commit": int(payload["terminal_state"] == "fast_commit"),
                    "infrastructure_error_count": len(
                        payload.get("infrastructure_errors", [])
                    ),
                    "path": str(path),
                }
            )
    return rows


def baseline_path(
    baseline_root: Path, model: str, benchmark: str, problem_id: int
) -> Path:
    env = (
        f"development__{MODELS[model]}__{benchmark}__seed_42"
    )
    return baseline_root / env / "main" / "traj" / f"problem_{problem_id}.json"


def attach_baseline(rows: list[dict[str, Any]], baseline_root: Path) -> None:
    cache: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for row in rows:
        key = (row["model"], row["benchmark"], int(row["problem_id"]))
        if key not in cache:
            path = baseline_path(baseline_root, *key)
            cache[key] = load_json(path)
        baseline = cache[key]
        tokens = int(baseline["tokens_used"])
        row["baseline_tokens"] = tokens
        row["baseline_correct"] = int(bool(baseline["final_correct"]))
        row["fair_token_saving"] = (
            (tokens - row["all_generated_tokens"]) / tokens if tokens else 0.0
        )
        row["main_only_token_saving"] = (
            (tokens - row["native_main_tokens"]) / tokens if tokens else 0.0
        )


def group_metrics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["method"], row["model"], row["benchmark"])].append(row)
    output = []
    for (method, model, benchmark), values in sorted(groups.items()):
        output.append(
            {
                "method": method,
                "model": model,
                "benchmark": benchmark,
                "n": len(values),
                "accuracy": mean(row["correct"] for row in values),
                "baseline_accuracy": mean(row["baseline_correct"] for row in values),
                "accuracy_delta": mean(
                    row["correct"] - row["baseline_correct"] for row in values
                ),
                "fair_token_saving": mean(row["fair_token_saving"] for row in values),
                "main_only_token_saving": mean(
                    row["main_only_token_saving"] for row in values
                ),
                "mean_all_generated_tokens": mean(
                    row["all_generated_tokens"] for row in values
                ),
                "mean_prompt_tokens": mean(row["all_prompt_tokens"] for row in values),
                "fast_rate": mean(row["fast_commit"] for row in values),
                "branch_rate": mean(row["branches"] > 0 for row in values),
                "branch_commit_rate": mean(row["branch_commits"] > 0 for row in values),
                "capped_rate": mean(row["capped"] for row in values),
                "mean_stage1_attempts": mean(row["stage1_attempts"] for row in values),
                "p90_stage1_attempts": percentile(
                    (row["stage1_attempts"] for row in values), 0.9
                ),
            }
        )
    return output


def macro_metrics(env_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for method in METHODS:
        rows = [row for row in env_rows if row["method"] == method]
        for model in list(MODELS) + ["all_models"]:
            selected = rows if model == "all_models" else [
                row for row in rows if row["model"] == model
            ]
            if not selected:
                continue
            output.append(
                {
                    "method": method,
                    "model": model,
                    "benchmark_macro_accuracy": mean(row["accuracy"] for row in selected),
                    "benchmark_macro_accuracy_delta": mean(
                        row["accuracy_delta"] for row in selected
                    ),
                    "benchmark_macro_fair_token_saving": mean(
                        row["fair_token_saving"] for row in selected
                    ),
                    "benchmark_macro_main_only_token_saving": mean(
                        row["main_only_token_saving"] for row in selected
                    ),
                }
            )
    return output


def paired_bootstrap(
    rows: Sequence[Mapping[str, Any]], iterations: int = 10_000, seed: int = 20260728
) -> dict[str, Any]:
    index = {
        (row["method"], row["model"], row["benchmark"], row["problem_id"]): row
        for row in rows
    }
    strata: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        if row["method"] == METHOD_PROPOSED:
            strata[(row["model"], row["benchmark"])].append(row["problem_id"])
    rng = random.Random(seed)
    accuracy_deltas: list[float] = []
    token_deltas: list[float] = []
    for _ in range(iterations):
        per_benchmark_acc: dict[str, list[float]] = defaultdict(list)
        per_benchmark_tok: dict[str, list[float]] = defaultdict(list)
        for (model, benchmark), problem_ids in strata.items():
            sampled = [rng.choice(problem_ids) for _ in problem_ids]
            acc = []
            tok = []
            for problem_id in sampled:
                proposed = index[(METHOD_PROPOSED, model, benchmark, problem_id)]
                reference = index[(METHOD_REFERENCE, model, benchmark, problem_id)]
                acc.append(proposed["correct"] - reference["correct"])
                base = proposed["baseline_tokens"]
                tok.append(
                    (reference["all_generated_tokens"] - proposed["all_generated_tokens"])
                    / base
                )
            per_benchmark_acc[benchmark].append(mean(acc))
            per_benchmark_tok[benchmark].append(mean(tok))
        accuracy_deltas.append(
            mean(mean(per_benchmark_acc[benchmark]) for benchmark in BENCHMARKS)
        )
        token_deltas.append(
            mean(mean(per_benchmark_tok[benchmark]) for benchmark in BENCHMARKS)
        )
    return {
        "iterations": iterations,
        "seed": seed,
        "comparison": f"{METHOD_PROPOSED} - {METHOD_REFERENCE}",
        "accuracy_delta": {
            "mean": mean(accuracy_deltas),
            "ci95": [percentile(accuracy_deltas, 0.025), percentile(accuracy_deltas, 0.975)],
        },
        "token_saving_advantage": {
            "mean": mean(token_deltas),
            "ci95": [percentile(token_deltas, 0.025), percentile(token_deltas, 0.975)],
        },
    }


def audit(rows: Sequence[Mapping[str, Any]], allow_incomplete: bool) -> dict[str, Any]:
    identities = [
        (row["method"], row["model"], row["benchmark"], row["seed"], row["problem_id"])
        for row in rows
    ]
    counts = {method: sum(row["method"] == method for row in rows) for method in METHODS}
    errors = []
    if len(identities) != len(set(identities)):
        errors.append("duplicate identity")
    for method in METHODS:
        if counts[method] != 228:
            errors.append(f"{method}: expected 228, observed {counts[method]}")
        for model in MODELS:
            for benchmark, expected in (("math500", 100), ("amc23", 8), ("aime24", 6)):
                observed = sum(
                    row["method"] == method
                    and row["model"] == model
                    and row["benchmark"] == benchmark
                    for row in rows
                )
                if observed != expected:
                    errors.append(
                        f"{method}/{model}/{benchmark}: expected {expected}, observed {observed}"
                    )
    if any(row["seed"] != 42 for row in rows):
        errors.append("non-42 seed")
    if any(row["split"] != "dev" for row in rows):
        errors.append("non-Dev result")
    if len({row["config_hash"] for row in rows}) > 1:
        errors.append("multiple config hashes")
    if any(row["infrastructure_error_count"] for row in rows):
        errors.append("recorded infrastructure errors")
    complete = not errors
    if errors and not allow_incomplete:
        status = "failed"
    else:
        status = "complete" if complete else "exploratory_incomplete"
    return {
        "status": status,
        "complete": complete,
        "counts": counts,
        "total": len(rows),
        "errors": errors,
    }


def write_report(
    path: Path,
    env_rows: Sequence[Mapping[str, Any]],
    macro_rows: Sequence[Mapping[str, Any]],
    audit_result: Mapping[str, Any],
    bootstrap: Optional[Mapping[str, Any]],
) -> None:
    lines = [
        "# DEER-inspired Online Dev 实验报告",
        "",
        "本轮为 seed 42 的 exploratory Dev 实验；不能估计 seed variance，",
        "AMC23/AIME24 小样本结论需谨慎解释。",
        "",
        "## 完整性",
        "",
        f"- 状态：`{audit_result['status']}`",
        f"- 总结果数：{audit_result['total']}",
        f"- 方法计数：`{json.dumps(audit_result['counts'], ensure_ascii=False)}`",
        "",
        "## Benchmark 等权宏平均",
        "",
        "| 方法 | 模型 | Accuracy | ΔAccuracy | 公平 token saving | Main-only saving |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in macro_rows:
        lines.append(
            "| {method} | {model} | {benchmark_macro_accuracy:.4f} | "
            "{benchmark_macro_accuracy_delta:+.4f} | "
            "{benchmark_macro_fair_token_saving:.4f} | "
            "{benchmark_macro_main_only_token_saving:.4f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## 分环境结果",
            "",
            "| 方法 | 模型 | Benchmark | n | Acc. | ΔAcc. | Fair saving | Fast | Branch | Capped |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in env_rows:
        lines.append(
            "| {method} | {model} | {benchmark} | {n} | {accuracy:.4f} | "
            "{accuracy_delta:+.4f} | {fair_token_saving:.4f} | {fast_rate:.4f} | "
            "{branch_rate:.4f} | {capped_rate:.4f} |".format(**row)
        )
    if bootstrap:
        lines.extend(
            [
                "",
                "## 配对不确定性",
                "",
                "按 benchmark 分层、方法间逐题配对进行 10,000 次 bootstrap；三个 benchmark 等权。",
                "",
                f"- Accuracy difference：`{json.dumps(bootstrap['accuracy_delta'])}`",
                f"- Token-saving advantage：`{json.dumps(bootstrap['token_saving_advantage'])}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 限制",
            "",
            "- 在线 controller 与既有 single-request full baseline 的采样路径不完全相同。",
            "- 本轮只运行一个 seed，所有区间和结论均为 exploratory。",
            "- Test/confirmation 未读取，阈值未依据本轮结果改动。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument(
        "--baseline-root",
        type=Path,
        default=Path("benchmark/FalseConsensus/results/governor_v2"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    rows = discover(args.results_root)
    attach_baseline(rows, args.baseline_root)
    audit_result = audit(rows, args.allow_incomplete)
    env_rows = group_metrics(rows)
    macro_rows = macro_metrics(env_rows)
    bootstrap = (
        paired_bootstrap(rows)
        if audit_result["complete"]
        else None
    )
    if rows:
        atomic_write_csv(args.output / "per_problem.csv", rows, list(rows[0]))
    if env_rows:
        atomic_write_csv(args.output / "environment_metrics.csv", env_rows, list(env_rows[0]))
    if macro_rows:
        atomic_write_csv(args.output / "dev_macro.csv", macro_rows, list(macro_rows[0]))
    atomic_write_json(args.output / "audit.json", audit_result)
    if bootstrap:
        atomic_write_json(args.output / "bootstrap.json", bootstrap)
    summary = {
        "audit": audit_result,
        "macro": macro_rows,
        "bootstrap": bootstrap,
    }
    atomic_write_json(args.output / "summary.json", summary)
    write_report(args.output / "report.md", env_rows, macro_rows, audit_result, bootstrap)
    if not audit_result["complete"] and not args.allow_incomplete:
        raise SystemExit("audit failed: " + "; ".join(audit_result["errors"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
