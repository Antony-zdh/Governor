"""Audit and aggregate the single-seed online DEER experiment.

Produces the §13 artifact set: ``per_problem.csv``,
``environment_metrics.csv``, ``dev_pooled.csv``, ``dev_macro.csv``,
``paired_comparisons.csv``, ``bootstrap.json``, ``audit.json``,
``summary.json``, ``report.md``, ``report.pdf`` (via ``report.py``) and
``artifact_manifest.json``.

The default aggregate is fail-closed: each method must contain exactly 228
results, all at seed 42, with no recorded infrastructure error. Use
``--allow-incomplete`` only for explicitly labeled progress diagnostics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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
            waits = payload.get("wait_events", [])
            branches = payload.get("branches", [])
            main_segments = payload.get("main_segments", [])
            main_latency = sum(float(s.get("latency_seconds", 0)) for s in main_segments)
            aux_latency = (
                sum(float(w.get("trial", {}).get("latency_seconds", 0)) for w in waits if isinstance(w.get("trial"), Mapping))
                + sum(
                    float(b.get("verification", {}).get("latency_seconds", 0))
                    + float(b.get("stage2", {}).get("latency_seconds", 0))
                    for b in branches
                )
                + float((payload.get("reference_readout") or {}).get("latency_seconds", 0) or 0)
            )
            waits_before_1024 = sum(
                1 for w in waits if int(w.get("native_main_token_position", 0)) < 1024
            )
            dense = sum(1 for w in waits if w.get("schedule_mode") == "dense")
            sparse = sum(1 for w in waits if w.get("schedule_mode") == "sparse")
            gap_skips = sum(
                1
                for w in waits
                if w.get("skip_reason") in ("post_dense_gap_lt_512", "verification_gap_lt_512")
            )
            invalid_trials = sum(
                1
                for w in waits
                if isinstance(w.get("trial"), Mapping) and not w["trial"].get("valid")
            )
            branch_enter = len(branches)
            branch_pass = sum(1 for b in branches if b.get("outcome") == "commit")
            branch_fail = sum(1 for b in branches if b.get("outcome") == "fail_retain_verification")
            confidences = []
            for w in waits:
                trial = w.get("trial")
                if isinstance(trial, Mapping) and trial.get("valid"):
                    confidences.append(float(trial.get("confidence", 0.0)))
            for b in branches:
                s2 = b.get("stage2")
                if isinstance(s2, Mapping) and s2.get("valid"):
                    confidences.append(float(s2.get("confidence", 0.0)))
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
                    "committed_reasoning_context_tokens": accounting[
                        "committed_reasoning_context_tokens"
                    ],
                    "stage1_tokens": accounting["stage1_trial_output_tokens"],
                    "verification_tokens": accounting["verification_output_tokens"],
                    "stage2_tokens": accounting["stage2_trial_output_tokens"],
                    "readout_tokens": accounting["reference_readout_output_tokens"],
                    "controller_cue_tokens": accounting["controller_cue_tokens"],
                    "stage1_attempts": sum(
                        int(event.get("probed", False))
                        for event in waits
                    ),
                    "waits_observed": len(waits),
                    "waits_before_1024": waits_before_1024,
                    "dense_attempts": dense,
                    "sparse_attempts": sparse,
                    "gap_skips": gap_skips,
                    "invalid_trials": invalid_trials,
                    "branches": branch_enter,
                    "branch_commits": branch_pass,
                    "branch_fails": branch_fail,
                    "fast_commit": int(payload["terminal_state"] == "fast_commit"),
                    "main_latency_seconds": main_latency,
                    "aux_latency_seconds": aux_latency,
                    "total_latency_seconds": main_latency + aux_latency,
                    "mean_trial_confidence": (
                        mean(confidences) if confidences else 0.0
                    ),
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
        attempts = [int(r["stage1_attempts"]) for r in values]
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
                "mean_native_main_tokens": mean(
                    row["native_main_tokens"] for row in values
                ),
                "mean_prompt_tokens": mean(row["all_prompt_tokens"] for row in values),
                "mean_committed_reasoning_context_tokens": mean(
                    row["committed_reasoning_context_tokens"] for row in values
                ),
                "mean_total_latency_seconds": mean(
                    row["total_latency_seconds"] for row in values
                ),
                "fast_rate": mean(row["fast_commit"] for row in values),
                "branch_rate": mean(row["branches"] > 0 for row in values),
                "branch_commit_rate": mean(row["branch_commits"] > 0 for row in values),
                "branch_fail_rate": mean(row["branch_fails"] > 0 for row in values),
                "capped_rate": mean(row["capped"] for row in values),
                "invalid_trial_rate": mean(
                    (row["invalid_trials"] / row["stage1_attempts"])
                    if row["stage1_attempts"]
                    else 0.0
                    for row in values
                ),
                "mean_stage1_attempts": mean(attempts),
                "p50_stage1_attempts": percentile(attempts, 0.5),
                "p90_stage1_attempts": percentile(attempts, 0.9),
                "p95_stage1_attempts": percentile(attempts, 0.95),
                "max_stage1_attempts": max(attempts) if attempts else 0,
                "waits_before_1024_rate": mean(
                    row["waits_before_1024"] > 0 for row in values
                ),
                "dense_attempts_sum": sum(row["dense_attempts"] for row in values),
                "sparse_attempts_sum": sum(row["sparse_attempts"] for row in values),
                "gap_skips_sum": sum(row["gap_skips"] for row in values),
            }
        )
    return output


def dev_pooled_metrics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Pooled (all-benchmark) per method × model, plus per-method overall."""
    output = []
    for method in METHODS:
        for model in list(MODELS) + ["all_models"]:
            selected = [r for r in rows if r["method"] == method and (
                model == "all_models" or r["model"] == model
            )]
            if not selected:
                continue
            attempts = [int(r["stage1_attempts"]) for r in selected]
            output.append(
                {
                    "method": method,
                    "model": model,
                    "n": len(selected),
                    "accuracy": mean(r["correct"] for r in selected),
                    "baseline_accuracy": mean(r["baseline_correct"] for r in selected),
                    "fair_token_saving": mean(r["fair_token_saving"] for r in selected),
                    "main_only_token_saving": mean(
                        r["main_only_token_saving"] for r in selected
                    ),
                    "mean_all_generated_tokens": mean(
                        r["all_generated_tokens"] for r in selected
                    ),
                    "mean_native_main_tokens": mean(
                        r["native_main_tokens"] for r in selected
                    ),
                    "fast_rate": mean(r["fast_commit"] for r in selected),
                    "branch_rate": mean(r["branches"] > 0 for r in selected),
                    "branch_commit_rate": mean(r["branch_commits"] > 0 for r in selected),
                    "capped_rate": mean(r["capped"] for r in selected),
                    "mean_stage1_attempts": mean(attempts),
                    "mean_total_latency_seconds": mean(
                        r["total_latency_seconds"] for r in selected
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
                    "benchmark_macro_fast_rate": mean(
                        row["fast_rate"] for row in selected
                    ),
                    "benchmark_macro_branch_rate": mean(
                        row["branch_rate"] for row in selected
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
        "stratification": "per-benchmark paired problem resampling, equal-weight macro over 3 benchmarks",
        "accuracy_delta": {
            "mean": mean(accuracy_deltas),
            "ci95": [percentile(accuracy_deltas, 0.025), percentile(accuracy_deltas, 0.975)],
        },
        "token_saving_advantage": {
            "mean": mean(token_deltas),
            "ci95": [percentile(token_deltas, 0.025), percentile(token_deltas, 0.975)],
        },
    }


def _frozen_deer_summary(baseline_root: Path, model: str, benchmark: str) -> Optional[dict[str, Any]]:
    """Env-level frozen-DEER reproduction summary (read-only related_work)."""
    path = (
        baseline_root.parent / "related_work" / "full" / "_replay"
        / f"{MODELS[model]}__{benchmark}__seed_42__deer" / "summary.json"
    )
    if not path.exists():
        return None
    return load_json(path)


def paired_comparisons(
    rows: Sequence[Mapping[str, Any]], baseline_root: Path
) -> list[dict[str, Any]]:
    """The four §13 comparisons.

    (1) new online vs online reference  — paired per problem, same online engine.
    (2) new online vs existing full      — paired per problem vs governor_v2 baseline.
    (3) online reference vs frozen DEER   — env-level (frozen replay), non-paired.
    (4) new online vs fast-path-only replay — N/A if that replay is absent.
    """
    out: list[dict[str, Any]] = []
    by_key = {(r["method"], r["model"], r["benchmark"], r["problem_id"]): r for r in rows}

    # (1) proposed vs reference (paired, fair all-generated tokens)
    acc_d, tok_d = [], []
    for r in rows:
        if r["method"] != METHOD_PROPOSED:
            continue
        other = by_key.get((METHOD_REFERENCE, r["model"], r["benchmark"], r["problem_id"]))
        if not other:
            continue
        acc_d.append(r["correct"] - other["correct"])
        tok_d.append(r["all_generated_tokens"] - other["all_generated_tokens"])
    out.append({
        "comparison": "new_online_vs_online_reference",
        "path_match": "same online engine, same Dev IDs, seed 42 (paired)",
        "counterfactual": "strict",
        "n_paired": len(acc_d),
        "accuracy_delta_mean": mean(acc_d) if acc_d else 0.0,
        "token_delta_mean": mean(tok_d) if tok_d else 0.0,
    })

    # (2) proposed vs existing full baseline (paired by ID)
    acc_d, tok_d = [], []
    for r in rows:
        if r["method"] != METHOD_PROPOSED:
            continue
        acc_d.append(r["correct"] - r["baseline_correct"])
        tok_d.append(r["native_main_tokens"] - r["baseline_tokens"])
    out.append({
        "comparison": "new_online_vs_existing_full",
        "path_match": "online multi-request path vs single-request frozen main trajectory (paired by ID)",
        "counterfactual": "approximate (sampling path differs)",
        "n_paired": len(acc_d),
        "accuracy_delta_mean": mean(acc_d) if acc_d else 0.0,
        "token_delta_mean": mean(tok_d) if tok_d else 0.0,
    })

    # (3) online reference vs frozen DEER (env-level, non-paired)
    env_rows = []
    for model in MODELS:
        for benchmark in BENCHMARKS:
            ref_rows = [r for r in rows if r["method"] == METHOD_REFERENCE
                        and r["model"] == model and r["benchmark"] == benchmark]
            if not ref_rows:
                continue
            frozen = _frozen_deer_summary(baseline_root, model, benchmark)
            if not frozen:
                continue
            env_rows.append({
                "model": model, "benchmark": benchmark,
                "ref_accuracy": mean(r["correct"] for r in ref_rows),
                "ref_mean_all_generated_tokens": mean(r["all_generated_tokens"] for r in ref_rows),
                "frozen_accuracy": float(frozen.get("accuracy", 0.0)),
                "frozen_mean_all_generated_tokens": float(frozen.get("avg_all_generated_tokens", 0.0)),
            })
    out.append({
        "comparison": "online_reference_vs_frozen_deer",
        "path_match": "online Wait-probe readout vs frozen-trajectory DEER replay (env-level, non-paired)",
        "counterfactual": "non-strict (frozen main text differs from online main)",
        "n_paired": len(env_rows),
        "accuracy_delta_mean": mean(e["ref_accuracy"] - e["frozen_accuracy"] for e in env_rows) if env_rows else 0.0,
        "token_delta_mean": mean(e["ref_mean_all_generated_tokens"] - e["frozen_mean_all_generated_tokens"] for e in env_rows) if env_rows else 0.0,
        "envs": env_rows,
    })

    # (4) new online vs fast-path-only replay
    fast_dir = baseline_root.parent / "deer_inspired" / "fast_path_only_replay"
    out.append({
        "comparison": "new_online_vs_fast_path_only_replay",
        "path_match": "fast-path-only frozen replay",
        "counterfactual": "n/a",
        "n_paired": 0,
        "accuracy_delta_mean": None,
        "token_delta_mean": None,
        "note": "fast_path_only_replay data absent in this checkout; comparison not computable" if not fast_dir.exists() else "present",
    })
    return out


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
    recompute_errors = 0
    for row in rows:
        if "all_generated_tokens" not in row:
            continue
        recomputed = (
            int(row.get("native_main_tokens", 0))
            + int(row.get("stage1_tokens", 0))
            + int(row.get("verification_tokens", 0))
            + int(row.get("stage2_tokens", 0))
            + int(row.get("readout_tokens", 0))
        )
        if recomputed != int(row["all_generated_tokens"]):
            recompute_errors += 1
    if recompute_errors:
        errors.append(f"all_generated_tokens recompute mismatch in {recompute_errors} rows")
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


def artifact_manifest(
    rows: Sequence[Mapping[str, Any]],
    *,
    results_root: Path,
    output: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """SHA-256 manifest of every per-problem result + aggregate artifact."""
    per_problem_hashes = []
    for path in sorted((results_root / METHOD_PROPOSED).glob("*__*__seed_42/problems/problem_*.json")):
        per_problem_hashes.append({"path": str(path.relative_to(results_root.parent)),
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    for path in sorted((results_root / METHOD_REFERENCE).glob("*__*__seed_42/problems/problem_*.json")):
        per_problem_hashes.append({"path": str(path.relative_to(results_root.parent)),
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    artifact_hashes = {}
    for name in ("per_problem.csv", "environment_metrics.csv", "dev_pooled.csv",
                 "dev_macro.csv", "paired_comparisons.csv", "bootstrap.json",
                 "audit.json", "summary.json", "report.md", "report.pdf"):
        p = output / name
        if p.exists():
            artifact_hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "per_problem_count": len(per_problem_hashes),
        "per_problem_hashes": per_problem_hashes,
        "artifact_hashes": artifact_hashes,
        "config_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        "models": {m: cfg["revision"] for m, cfg in config["models"].items()},
        "dtype": "bfloat16",
        "seed": config["formal_seed"],
        "split": config["split"],
    }


def write_report(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    env_rows: Sequence[Mapping[str, Any]],
    pooled_rows: Sequence[Mapping[str, Any]],
    macro_rows: Sequence[Mapping[str, Any]],
    audit_result: Mapping[str, Any],
    bootstrap: Optional[Mapping[str, Any]],
    comparisons: Sequence[Mapping[str, Any]],
    manifest: Optional[Mapping[str, Any]],
) -> None:
    def model_slug(m: str) -> str:
        return "DeepSeek-7B" if "deepseek" in m else "Qwen3-8B"

    lines = [
        "# DEER-inspired Online Dev 实验报告",
        "",
        "本轮为 seed 42 的 exploratory Dev 评估（加分项），不替代、也不回溯修改既有 Governor Pareto sweep。"
        "两个 BF16 模型在单张 RTX 5090 上依次在线服务，主推理从题目 prompt 在线生成，"
        "遇 `Wait` 转换且满足调度条件时现场 probe / 现场 verification branch，不拼接任何 frozen 轨迹的未来 suffix。",
        "",
        "## 1. 方法与部署化定位",
        "",
        "- **主方法 `deer_inspired_online_v1`**：1024 committed-main tokens 前只记录 `Wait` 不 probe；"
        "前 10 次实际 Stage-1 probe 保持 dense；之后进入 sparse（距上次实际 probe ≥512 main tokens 才 probe）。"
        "Stage-1 confidence `>0.995` fast commit；`>0.97` 且距上次 branch ≥512 进入 retained verification branch；"
        "branch 通过（Stage-2 `>0.99` 且两答案数学等价）则 commit，否则保留 verification reasoning、丢弃 Stage-2 并继续。",
        "- **对照 `deer_online_reference`**：官方 DEER 在线 Wait-probe，从首个 `Wait` 起最多 10 次，"
        "confidence `>0.95` 后用 `prefix+\\n\n\n` greedy readout（cap 4096）。无 fast path、无 verification branch。",
        "- 两者共用同一 online engine、prompt、主采样（T=0.6, top_p=0.95）与 seed policy；"
        "**差异仅在触发调度与 branch 控制器**，报告据此区分方法差异。",
        "- DeepSeek 用 `avg1`（算术平均，跳过首 token）；Qwen3 用 `avg2`（几何平均）且 confidence 仅当末 token 为 `</` 时有效（否则强制 0）。"
        "该 Qwen gate 同时适用于 Stage-1/Stage-2/reference。",
        "",
        "## 2. 完整性审计",
        "",
        f"- 状态：`{audit_result['status']}`；总结果数：{audit_result['total']}；"
        f"方法计数：`{json.dumps(audit_result['counts'], ensure_ascii=False)}`。",
        "- 每方法 228（2 模型 × 3 benchmark × seed 42，每模型 114 题），两方法合计 456；"
        "硬校验 seed=42、split=dev、单一 config hash、零 infrastructure error、all_generated_tokens 可逐行重算。",
        "",
        "## 3. Benchmark 等权宏平均",
        "",
        "| 方法 | 模型 | Macro Acc. | ΔAcc(vs full) | 公平 token saving | Main-only saving | Fast | Branch |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in macro_rows:
        lines.append(
            f"| {r['method']} | {r['model']} | {r['benchmark_macro_accuracy']:.4f} | "
            f"{r['benchmark_macro_accuracy_delta']:+.4f} | "
            f"{r['benchmark_macro_fair_token_saving']:.4f} | "
            f"{r['benchmark_macro_main_only_token_saving']:.4f} | "
            f"{r['benchmark_macro_fast_rate']:.4f} | {r['benchmark_macro_branch_rate']:.4f} |"
        )

    lines += [
        "",
        "## 4. 分环境结果（model × benchmark）",
        "",
        "| 方法 | 模型 | Benchmark | n | Acc. | ΔAcc. | Fair saving | Main saving | 均生成token | Fast | Branch | Branch通过 | Capped | 均Stage-1 | P95 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in env_rows:
        lines.append(
            f"| {r['method']} | {model_slug(r['model'])} | {r['benchmark']} | {r['n']} | "
            f"{r['accuracy']:.4f} | {r['accuracy_delta']:+.4f} | {r['fair_token_saving']:.4f} | "
            f"{r['main_only_token_saving']:.4f} | {r['mean_all_generated_tokens']:.0f} | "
            f"{r['fast_rate']:.4f} | {r['branch_rate']:.4f} | {r['branch_commit_rate']:.4f} | "
            f"{r['capped_rate']:.4f} | {r['mean_stage1_attempts']:.2f} | {r['p95_stage1_attempts']:.0f} |"
        )

    lines += [
        "",
        "## 5. Dev 汇总（pooled）",
        "",
        "| 方法 | 模型 | n | Acc. | Fair saving | Main-only saving | Fast | Branch | Capped | 均Stage-1 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in pooled_rows:
        lines.append(
            f"| {r['method']} | {r['model']} | {r['n']} | {r['accuracy']:.4f} | "
            f"{r['fair_token_saving']:.4f} | {r['main_only_token_saving']:.4f} | "
            f"{r['fast_rate']:.4f} | {r['branch_rate']:.4f} | {r['capped_rate']:.4f} | "
            f"{r['mean_stage1_attempts']:.2f} |"
        )

    prop = [r for r in rows if r["method"] == METHOD_PROPOSED]
    if prop:
        lines += [
            "",
            "## 6. Wait 调度器诊断（主方法）",
            "",
            f"- 观测 `Wait` 总数：{sum(r['waits_observed'] for r in prop)}；"
            f"1024 前记录但不 probe 的 `Wait` 涉及题数："
            f"{sum(1 for r in prop if r['waits_before_1024']>0)}/{len(prop)}。",
            f"- dense Stage-1 probe 总数：{sum(r['dense_attempts'] for r in prop)}；"
            f"sparse probe 总数：{sum(r['sparse_attempts'] for r in prop)}；"
            f"512-gap 跳过总数：{sum(r['gap_skips'] for r in prop)}（不排队、不后延）。",
            f"- 平均 Stage-1 attempts：{mean(r['stage1_attempts'] for r in prop):.2f}；"
            f"无隐藏 hard cap（reference 仍严格 ≤10，主方法 sparse 可超过）。",
        ]

    if comparisons:
        lines += [
            "",
            "## 7. 对比",
            "",
            "| 对比 | 配对/路径 | counterfactual | ΔAcc | ΔToken |",
            "|---|---|---|---:|---:|",
        ]
        for c in comparisons:
            acc = c.get("accuracy_delta_mean")
            tok = c.get("token_delta_mean")
            acc_s = f"{acc:+.4f}" if isinstance(acc, (int, float)) else "n/a"
            tok_s = f"{tok:+.1f}" if isinstance(tok, (int, float)) else "n/a"
            lines.append(
                f"| {c['comparison']} | {c['path_match']} | {c['counterfactual']} | {acc_s} | {tok_s} |"
            )

    if bootstrap:
        lines += [
            "",
            "## 8. 配对不确定性",
            "",
            "按 benchmark 分层、方法间逐题配对 10,000 次 bootstrap（seed 20260728），三 benchmark 等权。",
            "",
            f"- Accuracy difference（proposed−reference）mean={bootstrap['accuracy_delta']['mean']:+.4f}，"
            f"95% CI [{bootstrap['accuracy_delta']['ci95'][0]:+.4f}, {bootstrap['accuracy_delta']['ci95'][1]:+.4f}]。",
            f"- Token-saving advantage mean={bootstrap['token_saving_advantage']['mean']:+.4f}，"
            f"95% CI [{bootstrap['token_saving_advantage']['ci95'][0]:+.4f}, {bootstrap['token_saving_advantage']['ci95'][1]:+.4f}]。",
        ]

    lines += [
        "",
        "## 9. 限制与说明",
        "",
        "- 在线 controller 的多请求采样路径与既有 single-request full baseline 不完全相同，"
        "故 vs-existing-full 为近似 counterfactual，已明确标记。",
        "- 本轮仅 1 个 seed，不能估计 seed variance；AMC23(8)/AIME24(6) 样本很小，所有区间与结论均为 exploratory。",
        "- 未读取 Test/confirmation；阈值、verification budget、prompt、采样与 cap 未依本轮结果改动。",
        "- 原 Governor Pareto sweep 未改动；本轮为加分项。",
        "- fast_path_only_replay 数据在当前 checkout 中不存在，对应对比项标记为 n/a。",
    ]
    if prop:
        lines.append(
            f"- capped / invalid trial：主方法 capped 率 {mean(r['capped'] for r in prop):.4f}，"
            f"invalid trial 率 {mean((r['invalid_trials']/r['stage1_attempts']) if r['stage1_attempts'] else 0 for r in prop):.4f}。"
        )
    if manifest:
        lines += [
            "",
            "## 10. 产物清单",
            "",
            f"- per-problem 结果：{manifest['per_problem_count']} 条；"
            f"config_sha256=`{manifest['config_sha256'][:16]}…`；dtype=bfloat16。",
            f"- 各模型 pinned revision：DeepSeek `{manifest['models'].get('deepseek-ai/DeepSeek-R1-Distill-Qwen-7B','')[:12]}…`，"
            f"Qwen3 `{manifest['models'].get('Qwen/Qwen3-8B','')[:12]}…`。",
            "- 各 aggregate 产物 SHA-256 见 `artifact_manifest.json`。",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_comparison_csv(path: Path, comparisons: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = ["comparison", "path_match", "counterfactual",
                  "n_paired", "accuracy_delta_mean", "token_delta_mean", "note"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for c in comparisons:
            row = {k: c.get(k) for k in fieldnames}
            if "n_envs" in c:
                row["n_paired"] = c["n_envs"]
            writer.writerow(row)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument(
        "--baseline-root",
        type=Path,
        default=Path("benchmark/FalseConsensus/results/governor_v2"),
    )
    parser.add_argument("--config", type=Path,
                        default=Path("benchmark/FalseConsensus/deer_inspired/configs/online_dev_v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    from .common import load_config
    config = load_config(args.config)
    rows = discover(args.results_root)
    attach_baseline(rows, args.baseline_root)
    audit_result = audit(rows, args.allow_incomplete)
    env_rows = group_metrics(rows)
    pooled_rows = dev_pooled_metrics(rows)
    macro_rows = macro_metrics(env_rows)
    comparisons = paired_comparisons(rows, args.baseline_root)
    bootstrap = (
        paired_bootstrap(rows)
        if audit_result["complete"]
        else None
    )
    manifest = artifact_manifest(rows, results_root=args.results_root, output=args.output, config=config)
    if rows:
        atomic_write_csv(args.output / "per_problem.csv", rows, list(rows[0]))
    if env_rows:
        atomic_write_csv(args.output / "environment_metrics.csv", env_rows, list(env_rows[0]))
    if pooled_rows:
        atomic_write_csv(args.output / "dev_pooled.csv", pooled_rows, list(pooled_rows[0]))
    if macro_rows:
        atomic_write_csv(args.output / "dev_macro.csv", macro_rows, list(macro_rows[0]))
    if comparisons:
        write_comparison_csv(args.output / "paired_comparisons.csv", comparisons)
    atomic_write_json(args.output / "audit.json", audit_result)
    if bootstrap:
        atomic_write_json(args.output / "bootstrap.json", bootstrap)
    summary = {
        "audit": audit_result,
        "pooled": pooled_rows,
        "macro": macro_rows,
        "comparisons": comparisons,
        "bootstrap": bootstrap,
        "manifest": manifest,
    }
    atomic_write_json(args.output / "summary.json", summary)
    atomic_write_json(args.output / "artifact_manifest.json", manifest)
    write_report(args.output / "report.md", rows, env_rows, pooled_rows, macro_rows,
                 audit_result, bootstrap, comparisons, manifest)
    if not audit_result["complete"] and not args.allow_incomplete:
        raise SystemExit("audit failed: " + "; ".join(audit_result["errors"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
