#!/usr/bin/env python3
"""Audit DEER-Pro C_cali feasibility and run a CPU-only token-MAD surrogate.

DEER-Pro defines, at a *single reasoning transition*, four confidence values
from four distinct answer-inducing prompts and then computes

    C_cali = mean(C_i) - alpha * mean(abs(C_i - mean(C_i))).

The frozen DEER bank in this repository contains one answer-inducing prompt per
transition.  Consequently a faithful C_cali replay is mathematically
unidentifiable from the saved data.  This script makes that limitation
machine-checkable and, as a separate diagnostic, evaluates a conservative
surrogate that applies MAD to token probabilities within the one saved trial.
The surrogate is never labelled as C_cali in its output.

No model calls are made.  Only the existing DEER trial files and their robustly
graded replay rows are read.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


THRESHOLD = 0.95
ALPHAS = (0.0, 0.25, 0.5, 1.0, 2.0)
PAPER_N = 4
PAPER_ALPHA = 1.0


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            rows.append(payload)
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def token_probabilities(trial: Mapping[str, Any]) -> list[float]:
    """Return DEER's usable token probabilities (first token is skipped)."""
    logprobs = trial.get("logprobs")
    if not isinstance(logprobs, list) or len(logprobs) <= 1:
        return []
    values: list[float] = []
    for item in logprobs[1:]:
        if not isinstance(item, Mapping):
            return []
        value = item.get("logprob")
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return []
        values.append(math.exp(float(value)))
    return values


def mean_absolute_deviation(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = statistics.fmean(values)
    return statistics.fmean(abs(value - center) for value in values)


def geometric_mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.exp(statistics.fmean(math.log(max(value, 1e-10)) for value in values))


def first_official_stop(trials: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for trial in trials:
        if float(trial.get("confidence", 0.0)) > THRESHOLD:
            return trial
    return None


def parse_replay_identity(path: Path) -> tuple[str, str, int]:
    # <model>__<bench>__seed_<seed>__deer
    name = path.parent.name
    suffix = "__deer"
    if not name.endswith(suffix):
        raise ValueError(f"unexpected replay directory: {path.parent}")
    stem = name[: -len(suffix)]
    model, benchmark, seed_text = stem.split("__", 2)
    if not seed_text.startswith("seed_"):
        raise ValueError(f"unexpected replay directory: {path.parent}")
    return model, benchmark, int(seed_text.removeprefix("seed_"))


def discover_records(results_root: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    replay_paths = sorted(
        (results_root / "_replay").glob("*__deer/replay_rows.jsonl")
    )
    if not replay_paths:
        raise FileNotFoundError(f"no DEER replay rows under {results_root / '_replay'}")

    records: list[dict[str, Any]] = []
    sources: list[Path] = []
    for replay_path in replay_paths:
        model, benchmark, seed = parse_replay_identity(replay_path)
        sources.append(replay_path)
        for row in read_jsonl(replay_path):
            problem_id = int(row["problem_id"])
            trial_path = (
                results_root
                / f"{model}__{benchmark}__seed_{seed}"
                / "deer"
                / "trials"
                / f"problem_{problem_id}.json"
            )
            payload = read_json(trial_path)
            sources.append(trial_path)
            trials = payload.get("trials")
            if not isinstance(trials, list):
                raise ValueError(f"missing trials list: {trial_path}")

            official = first_official_stop(trials)
            observed_stop = bool(row.get("stopped", False))
            if observed_stop != (official is not None):
                raise ValueError(
                    f"stop mismatch {trial_path}: replay={observed_stop}, "
                    f"trials={official is not None}"
                )

            probs = token_probabilities(official or {})
            official_confidence = (
                float((official or {}).get("confidence", 0.0)) if official else 0.0
            )
            token_mad = mean_absolute_deviation(probs)
            token_geometric = geometric_mean(probs)
            # Preserve Qwen's mandatory </think> validity gate.  A zero official
            # confidence means the saved trial cannot be eligible regardless of
            # its raw geometric token probability.
            if official is not None and bool(payload.get("require_think_close", False)):
                if not bool(official.get("think_close_emitted", False)):
                    token_geometric = 0.0

            trial_output_tokens = sum(
                int(trial.get("trial_out_tokens", 0))
                for trial in trials
                if isinstance(trial, Mapping)
            )
            trial_prompt_tokens = sum(
                int(trial.get("trial_prompt_tokens", 0))
                for trial in trials
                if isinstance(trial, Mapping)
            )

            base = {
                "model_key": model,
                "model": str(row["model"]),
                "benchmark": benchmark,
                "seed": seed,
                "split": str(row["split"]),
                "problem_id": problem_id,
                "n_saved_inducers_per_transition": 1,
                "n_trials": len(trials),
                "official_stopped": int(observed_stop),
                "official_confidence": official_confidence,
                "token_probability_mad": token_mad,
                "token_geometric_mean": token_geometric,
                "baseline_correct": int(row["baseline_correct"]),
                "deer_correct": int(row["correct"]),
                "baseline_tokens": int(row["baseline_all_generated_tokens"]),
                "deer_all_generated_tokens": int(row["all_generated_tokens"]),
                "trial_output_tokens": trial_output_tokens,
                "trial_prompt_tokens": trial_prompt_tokens,
            }
            for alpha in ALPHAS:
                # This is deliberately named token_mad_surrogate, not C_cali.
                score = max(0.0, official_confidence - alpha * token_mad)
                accept = bool(observed_stop and score > THRESHOLD)
                correct = int(row["correct"]) if accept else int(row["baseline_correct"])
                if accept:
                    generated_tokens = int(row["all_generated_tokens"])
                else:
                    # Conservative-replay lower bound: the already observed
                    # trials are charged before falling back to the full answer.
                    # Later trials that a live controller might issue are absent.
                    generated_tokens = (
                        int(row["baseline_all_generated_tokens"]) + trial_output_tokens
                    )
                record = dict(base)
                record.update(
                    {
                        "variant": f"token_mad_alpha_{alpha:g}",
                        "alpha": alpha,
                        "surrogate_score": score,
                        "accepted": int(accept),
                        "correct": correct,
                        "all_generated_tokens_lower_bound": generated_tokens,
                    }
                )
                records.append(record)
    return records, sources


def aggregate(records: Iterable[Mapping[str, Any]], group_fields: Sequence[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[tuple(record[field] for field in group_fields)].append(record)

    rows: list[dict[str, Any]] = []
    for key, group in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        n = len(group)
        baseline_tokens = sum(int(row["baseline_tokens"]) for row in group)
        generated_tokens = sum(
            int(row["all_generated_tokens_lower_bound"]) for row in group
        )
        baseline_accuracy = statistics.fmean(
            int(row["baseline_correct"]) for row in group
        )
        accuracy = statistics.fmean(int(row["correct"]) for row in group)
        accepted = [row for row in group if int(row["accepted"])]
        result = {field: value for field, value in zip(group_fields, key)}
        result.update(
            {
                "n": n,
                "baseline_accuracy": baseline_accuracy,
                "accuracy": accuracy,
                "accuracy_delta_pp": 100.0 * (accuracy - baseline_accuracy),
                "accepted": len(accepted),
                "accept_rate": len(accepted) / n,
                "accepted_accuracy": (
                    statistics.fmean(int(row["correct"]) for row in accepted)
                    if accepted
                    else None
                ),
                "weighted_token_saving_lower_bound": (
                    1.0 - generated_tokens / baseline_tokens
                    if baseline_tokens
                    else 0.0
                ),
                "mean_token_mad": statistics.fmean(
                    float(row["token_probability_mad"]) for row in group
                ),
            }
        )
        rows.append(result)
    return rows


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def format_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{100.0 * float(value):.2f}%"


def build_report(
    records: Sequence[Mapping[str, Any]],
    pooled: Sequence[Mapping[str, Any]],
    environment: Sequence[Mapping[str, Any]],
) -> str:
    base_records = [row for row in records if float(row["alpha"]) == 0.0]
    n_trajectories = len(base_records)
    n_trials = sum(int(row["n_trials"]) for row in base_records)
    n_stops = sum(int(row["official_stopped"]) for row in base_records)
    max_inducers = max(
        int(row["n_saved_inducers_per_transition"]) for row in base_records
    )

    lines = [
        "# DEER-Pro `C_cali` 本地回溯：可行性审计与 token-MAD 诊断",
        "",
        "## 结论",
        "",
        f"- 审计覆盖 **{n_trajectories:,}** 条 train/dev trajectory、"
        f"**{n_trials:,}** 次已保存 DEER trial；原 DEER 在 "
        f"**{n_stops:,}** 条 trajectory 上早停。",
        f"- 每个 transition 最多只有 **{max_inducers}** 个 answer-inducing "
        f"prompt，而 DEER-Pro 的 `C_cali` 需要同一 transition 上 "
        f"`N={PAPER_N}` 个不同 inducer。因此，现有日志**不能 faithful 地计算 "
        "`C_cali`**；这不是 CPU 算力问题，而是缺少三次反事实模型输出。",
        "- 下表的 `token-MAD` 只是在单次 trial 内对 token probability 做 "
        "MAD 惩罚的诊断 surrogate。它回答“单次答案内部概率波动是否有筛选价值”，"
        "不能作为 DEER-Pro 复现结果。",
        "",
        "DEER-Pro 论文定义：",
        "",
        r"$$C_{\mathrm{cali}}=C_{\mathrm{avg}}-\alpha C_{\mathrm{MAD}},"
        r"\quad C_{\mathrm{MAD}}=\frac1N\sum_i|C_i-C_{\mathrm{avg}}|,$$",
        "",
        f"其中每个 $C_i$ 来自不同 answer-inducing prompt；论文设置 "
        f"$N={PAPER_N}$、$\\alpha={PAPER_ALPHA:g}$、阈值 $\\lambda={THRESHOLD}$。",
        "",
        "## CPU-only token-MAD surrogate",
        "",
        "若 surrogate 拒绝原 DEER 的首个 stop，本回溯让它退回完整答案，并只计入"
        "已经实际观测到的 trial output；由于没有继续生成后续 transition，这个 "
        "token saving 是**乐观上界/额外成本下界**。",
        "",
        "| Split | α | Accuracy | ΔAcc vs full | Accept rate | Accepted acc. | Token saving* |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in pooled:
        if row.get("model_key") != "ALL" or row.get("benchmark") != "ALL":
            continue
        lines.append(
            f"| {row['split']} | {float(row['alpha']):g} | "
            f"{format_pct(row['accuracy'])} | {float(row['accuracy_delta_pp']):+.2f} pp | "
            f"{format_pct(row['accept_rate'])} | "
            f"{format_pct(row['accepted_accuracy'])} | "
            f"{format_pct(row['weighted_token_saving_lower_bound'])} |"
        )
    lines.extend(
        [
            "",
            "\\* surrogate 拒绝后的后续 probe 未观测，故不是可部署成本的精确估计。",
            "",
            "## 解释边界",
            "",
            "- `α=0` 精确还原当前 model-specific DEER threshold 决策，是一致性检查。",
            "- `α>0` 只会比原 DEER 更保守；它不能发现原 collector 在首次拒绝后本应"
            "出现的更晚 stop。",
            "- faithful `C_cali` 需要 GPU 为每个 transition 补齐另外 3 个 varied "
            "inducers；应另立 preregistered probe-only 实验，不能从本表外推。",
            "",
            "## 产物",
            "",
            "- `decision_rows.csv`：逐 trajectory、逐 α 的 paired 决策。",
            "- `pooled_summary.csv`：split × model × benchmark 的 pooled 指标。",
            "- `environment_summary.csv`：split × model × benchmark × seed 指标。",
            "- `manifest.json`：输入覆盖、公式边界和输入 SHA-256。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-root",
        type=Path,
        default=repo_root / "benchmark" / "FalseConsensus" / "results" / "related_work" / "full",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root
        / "benchmark"
        / "FalseConsensus"
        / "results"
        / "related_work"
        / "c_cali_retrospective",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records, sources = discover_records(args.results_root)
    if not records:
        raise RuntimeError("no retrospective records produced")

    # Add explicit ALL views without duplicating the detailed decision artifact.
    pooled_input: list[dict[str, Any]] = []
    for record in records:
        pooled_input.append(dict(record))
        overall = dict(record)
        overall["model_key"] = "ALL"
        overall["benchmark"] = "ALL"
        pooled_input.append(overall)

    pooled = aggregate(
        pooled_input,
        ("split", "model_key", "benchmark", "variant", "alpha"),
    )
    environment = aggregate(
        records,
        ("split", "model_key", "benchmark", "seed", "variant", "alpha"),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "decision_rows.csv", records)
    write_csv(args.output_dir / "pooled_summary.csv", pooled)
    write_csv(args.output_dir / "environment_summary.csv", environment)
    report = build_report(records, pooled, environment)
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")

    unique_sources = sorted(set(sources))
    manifest = {
        "schema_version": "deer-c-cali-retrospective-audit-1",
        "faithful_c_cali_computable": False,
        "reason": (
            "saved bank has one answer-inducing prompt per transition; "
            "DEER-Pro requires N=4 varied inducing prompts at the same transition"
        ),
        "paper_definition": {
            "formula": "C_cali = C_avg - alpha * C_MAD",
            "N": PAPER_N,
            "alpha": PAPER_ALPHA,
            "threshold": THRESHOLD,
            "dispersion_axis": "confidence values across varied answer-inducing prompts",
        },
        "diagnostic_only": {
            "name": "within-trial token-probability MAD surrogate",
            "alphas": list(ALPHAS),
            "faithful_deer_pro": False,
            "fallback_cost_is_lower_bound": True,
        },
        "coverage": {
            "trajectory_alpha_rows": len(records),
            "unique_trajectories": len(records) // len(ALPHAS),
            "source_files": len(unique_sources),
        },
        "inputs": [
            {"path": str(path), "sha256": sha256(path)} for path in unique_sources
        ],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
